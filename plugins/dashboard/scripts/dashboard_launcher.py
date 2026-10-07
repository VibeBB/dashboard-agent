#!/usr/bin/env python3
"""Resolve the dashboard package and tools image, then execute an entry point.

Launcher-side verification uses DASHBOARD_VERIFY_ATTESTATION=auto|require|off.
It verifies lock provenance before pulls and on every prewarm; normal use
does not re-verify an image that is already present locally.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, TypedDict, cast

_MODULES = {"mcp_server": "dashboard.mcp_server"}
ISOLATED_NETWORK = "dashboard-isolated"
_INSPECT_TIMEOUT_S = 30
_PULL_TIMEOUT_S = 900
_NETWORK_TIMEOUT_S = 30
_ATTEST_TIMEOUT_S = 120
_GH_AUTH_TIMEOUT_S = 15
_DOCKER_INFO_TIMEOUT_S = 10
_VERIFY_ENV = "DASHBOARD_VERIFY_ATTESTATION"
_REPOSITORY = "VibeBB/dashboard-agent"
_PUBLISH_FILE = ".github/workflows/publish-dashboard-images.yml"


class ImagePin(TypedDict):
    ref: str
    image: str | None
    digest: str | None
    attestation: str | None


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _source_candidates(plugin_root: Path) -> list[Path]:
    candidates: list[Path] = []
    if os.environ.get("DASHBOARD_SRC"):
        candidates.append(Path(os.environ["DASHBOARD_SRC"]))
    for home in (Path.home(), Path(os.environ.get("HOME", str(Path.home())))):
        cache = home / ".openhands" / "cache" / "extensions"
        if cache.is_dir():
            candidates.extend(
                sorted(
                    cache.glob("dashboard-agent-*/src"),
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )
            )
    candidates.extend(
        [
            Path("/opt/dashboard/src"),
            plugin_root.parent.parent / "src",
        ]
    )
    return candidates


def resolve_source(plugin_root: Path) -> Path | None:
    for candidate in _source_candidates(plugin_root):
        if (candidate / "dashboard" / "__init__.py").is_file():
            return candidate.resolve()
    return None


def _host_source() -> Path:
    source = os.environ.get("DASHBOARD_SRC")
    if not source:
        raise RuntimeError(
            "DASHBOARD_LAUNCH_MODE=host is developer-only and requires DASHBOARD_SRC"
        )
    path = Path(source).expanduser()
    if not (path / "dashboard" / "__init__.py").is_file():
        raise RuntimeError(f"DASHBOARD_SRC does not contain dashboard/__init__.py: {path}")
    return path.resolve()


def _lock_ref(lock_path: Path) -> ImagePin | None:
    try:
        data: object = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    data = cast(dict[str, object], data)
    entry = data.get("dashboard_tools")
    if not isinstance(entry, dict):
        # Installed plugins ship a flat tools-image.json without the
        # `dashboard_tools` wrapper key used by docker/image-digests.json.
        entry = data
    entry = cast(dict[str, object], entry)
    image = entry.get("image")
    if not isinstance(image, str) or not image:
        return None
    digest = entry.get("digest")
    digest = digest if isinstance(digest, str) and digest else None
    tag = entry.get("tag")
    tag = tag if isinstance(tag, str) and tag else None
    if digest is None and tag is None:
        return None
    attestation = entry.get("attestation")
    return {
        "ref": f"{image}@{digest}" if digest else f"{image}:{tag}",
        "image": image,
        "digest": digest,
        "attestation": attestation if isinstance(attestation, str) and attestation else None,
    }


def image_pin(plugin_root: Path) -> ImagePin | None:
    explicit = os.environ.get("DASHBOARD_TOOLS_IMAGE")
    if explicit:
        return {"ref": explicit, "image": None, "digest": None, "attestation": None}
    plugin_lock = _lock_ref(plugin_root / "tools-image.json")
    return plugin_lock or _lock_ref(plugin_root.parent.parent / "docker" / "image-digests.json")


def image_ref(plugin_root: Path) -> str | None:
    pin = image_pin(plugin_root)
    return pin["ref"] if pin is not None else None


def ensure_isolated_network(docker: str) -> None:
    inspect_command = [
        docker,
        "network",
        "inspect",
        "--format",
        "{{.Internal}}",
        ISOLATED_NETWORK,
    ]
    inspected = _run_timed(
        inspect_command,
        "docker network inspect",
        _NETWORK_TIMEOUT_S,
        capture_output=True,
        text=True,
        check=False,
    )
    if inspected.returncode == 0:
        if inspected.stdout.strip().lower() != "true":
            raise RuntimeError(f"Docker network {ISOLATED_NETWORK} exists but is not internal")
        return

    created = _run_timed(
        [docker, "network", "create", "--internal", ISOLATED_NETWORK],
        "docker network create",
        _NETWORK_TIMEOUT_S,
        capture_output=True,
        text=True,
        check=False,
    )
    if created.returncode == 0:
        return

    inspected = _run_timed(
        inspect_command,
        "docker network inspect",
        _NETWORK_TIMEOUT_S,
        capture_output=True,
        text=True,
        check=False,
    )
    if inspected.returncode == 0:
        if inspected.stdout.strip().lower() == "true":
            return
        raise RuntimeError(f"Docker network {ISOLATED_NETWORK} exists but is not internal")

    detail = created.stderr.strip() or inspected.stderr.strip()
    raise RuntimeError(f"could not create internal Docker network {ISOLATED_NETWORK}: {detail}")


def _docker_info_security_options() -> str | None:
    """Return `docker info` security options, or None when unavailable."""
    docker = shutil.which("docker")
    if docker is None:
        return None
    try:
        result = subprocess.run(
            [docker, "info", "-f", "{{json .SecurityOptions}}"],
            capture_output=True,
            text=True,
            timeout=_DOCKER_INFO_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def _container_user() -> str:
    """uid:gid to run the tools container as.

    On rootless Docker the host uid maps to an unmapped subuid inside the
    container user namespace, so bind-mounted workspace writes fail. There
    container root (0:0) maps back to the daemon's owner — the invoking
    user — so 0:0 keeps writes working without weakening isolation (the
    container stays cap-dropped on an internal network). On rootful Docker
    keep the host uid so artifacts stay user-owned.
    """
    if "name=rootless" in (_docker_info_security_options() or ""):
        return "0:0"
    return f"{os.getuid()}:{os.getgid()}"


def _docker(image: str, source: Path | None, command: list[str]) -> list[str]:
    workspace = Path(os.environ.get("OPENHANDS_PROJECT_DIR") or Path.cwd()).resolve()
    cwd = Path.cwd().resolve()
    workdir = cwd if cwd == workspace or workspace in cwd.parents else workspace
    argv = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        ISOLATED_NETWORK,
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--user",
        _container_user(),
        "-v",
        f"{workspace}:{workspace}",
        "-w",
        str(workdir),
    ]
    if source is not None:
        argv.extend(
            ["-v", f"{source}:/opt/dashboard/src:ro", "-e", "PYTHONPATH=/opt/dashboard/src"]
        )
    for key, value in os.environ.items():
        if key == "TMPDIR" or key.startswith(("OPENHANDS_", "DASHBOARD_")):
            argv.extend(["-e", f"{key}={value}"])
    if "OPENHANDS_PROJECT_DIR" not in os.environ:
        argv.extend(["-e", f"OPENHANDS_PROJECT_DIR={workspace}"])
    return [*argv, image, *command]


def _inner_args(arguments: list[str], python: str) -> list[str]:
    if arguments[0] in _MODULES:
        return [python, "-m", _MODULES[arguments[0]], *arguments[1:]]
    return [python, "-m", "dashboard", *arguments]


def _run_timed(
    command: list[str],
    operation: str,
    timeout: int,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    try:
        return cast(
            subprocess.CompletedProcess[str],
            subprocess.run(command, timeout=timeout, **kwargs),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{operation} timed out after {timeout}s") from exc


def _attestation_mode() -> str:
    mode = os.environ.get(_VERIFY_ENV, "auto")
    if mode not in {"auto", "require", "off"}:
        raise ValueError(
            f"{_VERIFY_ENV} must be auto, require, or off (got {mode!r}); "
            f"usage: {_VERIFY_ENV}=auto|require|off"
        )
    return mode


def _verify_attestation(pin: ImagePin, *, override: bool) -> None:
    mode = _attestation_mode()
    if mode == "off":
        return
    reason: str | None = None
    gh = shutil.which("gh")
    if override:
        reason = "tools image override has no lock attestation context"
    elif not pin["attestation"]:
        reason = "lock entry has no attestation"
    elif not pin["image"] or not pin["digest"]:
        reason = "lock entry has no digest"
    elif gh is None:
        reason = "gh is not on PATH"
    else:
        try:
            auth = _run_timed(
                [gh, "auth", "status"],
                "gh auth status",
                _GH_AUTH_TIMEOUT_S,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except (OSError, RuntimeError):
            reason = "gh auth status failed"
        else:
            if auth.returncode != 0:
                reason = "gh auth status failed"
    if reason is not None:
        if mode == "require":
            raise RuntimeError(f"attestation verification required but {reason}")
        print(f"dashboard_launcher: attestation verification skipped: {reason}", file=sys.stderr)
        return
    assert gh is not None
    assert pin["image"] is not None and pin["digest"] is not None
    result = _run_timed(
        [
            gh,
            "attestation",
            "verify",
            f"oci://{pin['image']}@{pin['digest']}",
            "--repo",
            _REPOSITORY,
            "--signer-workflow",
            f"{_REPOSITORY}/{_PUBLISH_FILE}",
        ],
        "gh attestation verify",
        _ATTEST_TIMEOUT_S,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"attestation verification failed for {pin['image']}@{pin['digest']}")


def _inside_conversation_container() -> bool:
    """True when running inside an OpenHands docker conversation runtime.

    The runtime injects ``OH_PERSISTENCE_DIR``/``OH_RUNTIME_LAUNCHED_PROFILE``
    into each ``agent-server-conversation-*`` container, which carries no
    docker client — dashboard tools then have nowhere to launch the pinned
    tools image. ``OH_CONVERSATION_RUNTIME`` is not usable as the signal:
    the runtime sets it to ``local`` inside the container itself.
    """
    if os.environ.get("OH_PERSISTENCE_DIR") or os.environ.get("OH_RUNTIME_LAUNCHED_PROFILE"):
        return True
    with contextlib.suppress(OSError):
        return Path.home() == Path("/var/openhands/.openhands")
    return False


def _conversation_container_hint() -> str:
    if not _inside_conversation_container():
        return ""
    return (
        " — this appears to be an OpenHands docker conversation "
        "container, which cannot launch tool containers; set the "
        "conversation runtime to local (Agent Canvas -> Settings -> "
        "Application) and start a new conversation"
    )


def _image_ready(
    image: ImagePin | str,
    *,
    pull: bool,
    prewarm: bool = False,
    override: bool = False,
) -> bool:
    if isinstance(image, str):
        pin: ImagePin = {"ref": image, "image": None, "digest": None, "attestation": None}
        override = True
    else:
        pin = image
    ref = pin["ref"]
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("docker is not on PATH" + _conversation_container_hint())
    if prewarm:
        _verify_attestation(pin, override=override)
    inspected = _run_timed(
        [docker, "image", "inspect", ref],
        "docker image inspect",
        _INSPECT_TIMEOUT_S,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if inspected.returncode == 0:
        return True
    if not pull:
        return False
    if not prewarm:
        _verify_attestation(pin, override=override)
    return (
        _run_timed(
            [docker, "pull", ref],
            "docker pull",
            _PULL_TIMEOUT_S,
            check=False,
        ).returncode
        == 0
    )


def main() -> int:
    arguments = sys.argv[1:]
    if not arguments:
        print(
            "usage: dashboard_launcher.py {mcp_server|prewarm|<dashboard command>}", file=sys.stderr
        )
        return 2
    try:
        _attestation_mode()
    except ValueError as exc:
        print(f"dashboard_launcher: {exc}", file=sys.stderr)
        return 2
    warn = "--warn" in arguments
    arguments = [argument for argument in arguments if argument != "--warn"]
    mode = os.environ.get("DASHBOARD_LAUNCH_MODE", "docker")
    if mode not in {"docker", "host"}:
        print(
            f"DASHBOARD_LAUNCH_MODE must be docker or host (got {mode!r}); "
            "usage: DASHBOARD_LAUNCH_MODE=docker|host",
            file=sys.stderr,
        )
        return 2
    plugin_root = _plugin_root()
    source = resolve_source(plugin_root)
    pin = image_pin(plugin_root)
    image = pin["ref"] if pin is not None else None
    try:
        if arguments[0] == "prewarm":
            if pin is None:
                raise RuntimeError("no dashboard tools image is configured")
            if not _image_ready(
                pin,
                pull=True,
                prewarm=True,
                override=bool(os.environ.get("DASHBOARD_TOOLS_IMAGE")),
            ):
                raise RuntimeError(f"could not pull dashboard tools image {image}")
            return 0
        docker = shutil.which("docker")
        if mode == "docker":
            if docker is None or image is None:
                missing: list[str] = []
                suggestions: list[str] = []
                if docker is None:
                    missing.append("docker is not on PATH")
                    suggestions.append("install Docker")
                if image is None:
                    missing.append(
                        "no image resolved from DASHBOARD_TOOLS_IMAGE or the dashboard image lock"
                    )
                    suggestions.append("configure a dashboard tools image")
                suggestions.append("run dashboard_launcher.py prewarm")
                detail = f"{'; '.join(missing)}. {', then '.join(suggestions)}."
                if docker is None:
                    detail += _conversation_container_hint()
                raise RuntimeError(detail)
            if pin is None or not _image_ready(
                pin,
                pull=False,
                override=bool(os.environ.get("DASHBOARD_TOOLS_IMAGE")),
            ):
                raise RuntimeError(
                    f"dashboard tools image {image} is not pulled; "
                    "run dashboard_launcher.py prewarm"
                )
            ensure_isolated_network(docker)
            argv = _docker(image, source, _inner_args(arguments, "python"))
        else:
            source = _host_source()
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(source)
            argv = _inner_args(arguments, sys.executable)
            result = subprocess.run(argv, env=environment, check=False)
            return result.returncode
    except (OSError, RuntimeError) as exc:
        if warn:
            print(f"warn: {exc}", file=sys.stderr)
            print(json.dumps({"verdict": "fail", "detail": str(exc)}))
            return 0
        print(f"dashboard_launcher: {exc}", file=sys.stderr)
        return 1
    return subprocess.run(argv, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
