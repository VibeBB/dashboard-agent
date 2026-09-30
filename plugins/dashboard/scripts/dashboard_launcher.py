#!/usr/bin/env python3
"""Resolve the dashboard package and tools image, then execute an entry point."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_MODULES = {"mcp_server": "dashboard.mcp_server"}
ISOLATED_NETWORK = "dashboard-isolated"


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


def _lock_ref(lock_path: Path) -> str | None:
    try:
        entry = json.loads(lock_path.read_text(encoding="utf-8")).get("dashboard_tools")
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(entry, dict) or not entry.get("image"):
        return None
    if entry.get("digest"):
        return f"{entry['image']}@{entry['digest']}"
    if entry.get("tag"):
        return f"{entry['image']}:{entry['tag']}"
    return None


def image_ref(plugin_root: Path) -> str | None:
    explicit = os.environ.get("DASHBOARD_TOOLS_IMAGE")
    if explicit:
        return explicit
    plugin_lock = _lock_ref(plugin_root / "tools-image.json")
    return plugin_lock or _lock_ref(plugin_root.parent.parent / "docker" / "image-digests.json")


def ensure_isolated_network(docker: str) -> None:
    inspect_command = [
        docker,
        "network",
        "inspect",
        "--format",
        "{{.Internal}}",
        ISOLATED_NETWORK,
    ]
    inspected = subprocess.run(inspect_command, capture_output=True, text=True, check=False)
    if inspected.returncode == 0:
        if inspected.stdout.strip().lower() != "true":
            raise RuntimeError(f"Docker network {ISOLATED_NETWORK} exists but is not internal")
        return

    created = subprocess.run(
        [docker, "network", "create", "--internal", ISOLATED_NETWORK],
        capture_output=True,
        text=True,
        check=False,
    )
    if created.returncode == 0:
        return

    inspected = subprocess.run(inspect_command, capture_output=True, text=True, check=False)
    if inspected.returncode == 0:
        if inspected.stdout.strip().lower() == "true":
            return
        raise RuntimeError(f"Docker network {ISOLATED_NETWORK} exists but is not internal")

    detail = created.stderr.strip() or inspected.stderr.strip()
    raise RuntimeError(f"could not create internal Docker network {ISOLATED_NETWORK}: {detail}")


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
        "--user",
        f"{os.getuid()}:{os.getgid()}",
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
    return [*argv, image, *command]


def _inner_args(arguments: list[str], python: str) -> list[str]:
    if arguments[0] in _MODULES:
        return [python, "-m", _MODULES[arguments[0]], *arguments[1:]]
    return [python, "-m", "dashboard", *arguments]


def _image_ready(image: str, *, pull: bool) -> bool:
    docker = shutil.which("docker")
    if docker is None:
        raise RuntimeError("docker is not on PATH")
    inspected = subprocess.run(
        [docker, "image", "inspect", image],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if inspected.returncode == 0:
        return True
    if not pull:
        return False
    return subprocess.run([docker, "pull", image], check=False).returncode == 0


def main() -> int:
    arguments = sys.argv[1:]
    if not arguments:
        print(
            "usage: dashboard_launcher.py {mcp_server|prewarm|<dashboard command>}", file=sys.stderr
        )
        return 2
    warn = "--warn" in arguments
    arguments = [argument for argument in arguments if argument != "--warn"]
    plugin_root = _plugin_root()
    source = resolve_source(plugin_root)
    image = image_ref(plugin_root)
    try:
        if arguments[0] == "prewarm":
            if image is None:
                raise RuntimeError("no dashboard tools image is configured")
            if not _image_ready(image, pull=True):
                raise RuntimeError(f"could not pull dashboard tools image {image}")
            return 0
        docker = shutil.which("docker")
        if image and docker:
            if not _image_ready(image, pull=False):
                raise RuntimeError(
                    f"dashboard tools image {image} is not pulled; "
                    "run dashboard_launcher.py prewarm"
                )
            ensure_isolated_network(docker)
            argv = _docker(image, source, _inner_args(arguments, "python"))
        else:
            if source is None:
                raise RuntimeError("dashboard source is not installed; set DASHBOARD_SRC")
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
