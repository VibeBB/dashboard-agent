from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from plugins.dashboard.scripts import dashboard_launcher as launcher
from plugins.dashboard.scripts.dashboard_launcher import (
    ISOLATED_NETWORK,
    ImagePin,
    _docker,  # pyright: ignore[reportPrivateUsage]
    _image_ready,  # pyright: ignore[reportPrivateUsage]
    _inner_args,  # pyright: ignore[reportPrivateUsage]
    _lock_ref,  # pyright: ignore[reportPrivateUsage]
    ensure_isolated_network,
    image_ref,
    resolve_source,
)
from pytest import CaptureFixture, MonkeyPatch, raises

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/dashboard"


def _docker_on_path(_name: str) -> str:
    return "docker"


def _no_docker(_name: str) -> None:
    return None


def _no_image(_plugin_root: Path) -> ImagePin | None:
    return None


def _test_image(_plugin_root: Path) -> ImagePin:
    return {
        "ref": "dashboard-tools:test",
        "image": None,
        "digest": None,
        "attestation": None,
    }


def _image_is_ready(
    _image: ImagePin | str,
    *,
    pull: bool,
    prewarm: bool = False,
    override: bool = False,
) -> bool:
    assert not pull
    return True


def _network_ready(_docker: str) -> None:
    return None


def _clear_launch_environment(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("DASHBOARD_LAUNCH_MODE", raising=False)
    monkeypatch.delenv("DASHBOARD_TOOLS_IMAGE", raising=False)
    monkeypatch.delenv("DASHBOARD_SRC", raising=False)


def _capture_subprocess(monkeypatch: MonkeyPatch, *, returncode: int = 0) -> list[list[str]]:
    commands: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, returncode, "", "")

    monkeypatch.setattr(
        "plugins.dashboard.scripts.dashboard_launcher.subprocess.run",
        run,
    )
    return commands


def _run_launcher(monkeypatch: MonkeyPatch, *arguments: str) -> int:
    monkeypatch.setattr(launcher.sys, "argv", ["dashboard_launcher.py", *arguments])
    return launcher.main()


def test_launcher_resolves_checkout_source_and_supports_host_and_image_commands(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("DASHBOARD_TOOLS_IMAGE", raising=False)

    assert resolve_source(PLUGIN) == ROOT / "src"
    assert image_ref(_null_plugin_root(tmp_path)) is None
    assert _inner_args(["doctor"], "python3.12") == [
        "python3.12",
        "-m",
        "dashboard",
        "doctor",
    ]
    assert _inner_args(["mcp_server"], "python") == [
        "python",
        "-m",
        "dashboard.mcp_server",
    ]


def _null_plugin_root(tmp_path: Path) -> Path:
    plugin_root = tmp_path / "plugins/dashboard"
    plugin_root.mkdir(parents=True)
    pin = '{\n  "image": "ghcr.io/vibebb/dashboard-tools",\n  "digest": null,\n  "tag": null\n}\n'
    (plugin_root / "tools-image.json").write_text(pin, encoding="utf-8")
    lock_root = tmp_path / "docker"
    lock_root.mkdir()
    (lock_root / "image-digests.json").write_text(
        '{\n  "dashboard_tools": {\n'
        '    "image": "ghcr.io/vibebb/dashboard-tools",\n'
        '    "digest": null,\n    "tag": null\n  }\n}\n',
        encoding="utf-8",
    )
    return plugin_root


def test_container_invocation_mounts_source_and_uses_internal_network() -> None:
    command = _docker(
        "dashboard-tools:ci",
        ROOT / "src",
        ["python", "-m", "dashboard", "doctor"],
    )

    assert command[command.index("--network") + 1] == ISOLATED_NETWORK
    assert f"{ROOT / 'src'}:/opt/dashboard/src:ro" in command
    assert "PYTHONPATH=/opt/dashboard/src" in command
    assert command[-4:] == ["python", "-m", "dashboard", "doctor"]


def test_container_invocation_sets_project_dir_when_host_does_not(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENHANDS_PROJECT_DIR", raising=False)

    command = _docker("dashboard-tools:ci", None, ["python", "-m", "dashboard", "doctor"])

    assert f"OPENHANDS_PROJECT_DIR={Path.cwd().resolve()}" in command


def _mock_docker_runs(
    monkeypatch: MonkeyPatch,
    responses: list[tuple[int, str, str]],
) -> list[list[str]]:
    commands: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        returncode, stdout, stderr = responses.pop(0)
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)

    monkeypatch.setattr(
        "plugins.dashboard.scripts.dashboard_launcher.subprocess.run",
        run,
    )
    return commands


def test_ensure_isolated_network_reuses_internal_network(monkeypatch: MonkeyPatch) -> None:
    commands = _mock_docker_runs(monkeypatch, [(0, "true\n", "")])

    ensure_isolated_network("docker")

    assert commands == [
        ["docker", "network", "inspect", "--format", "{{.Internal}}", ISOLATED_NETWORK]
    ]


def test_ensure_isolated_network_creates_missing_network(monkeypatch: MonkeyPatch) -> None:
    commands = _mock_docker_runs(monkeypatch, [(1, "", "not found"), (0, "network-id\n", "")])

    ensure_isolated_network("docker")

    assert commands == [
        ["docker", "network", "inspect", "--format", "{{.Internal}}", ISOLATED_NETWORK],
        ["docker", "network", "create", "--internal", ISOLATED_NETWORK],
    ]


def test_ensure_isolated_network_rejects_non_internal_network(monkeypatch: MonkeyPatch) -> None:
    _mock_docker_runs(monkeypatch, [(0, "false\n", "")])

    with raises(RuntimeError, match="exists but is not internal"):
        ensure_isolated_network("docker")


def test_ensure_isolated_network_accepts_concurrent_creation(monkeypatch: MonkeyPatch) -> None:
    commands = _mock_docker_runs(
        monkeypatch,
        [(1, "", "not found"), (1, "", "already exists"), (0, "true\n", "")],
    )

    ensure_isolated_network("docker")

    assert commands == [
        ["docker", "network", "inspect", "--format", "{{.Internal}}", ISOLATED_NETWORK],
        ["docker", "network", "create", "--internal", ISOLATED_NETWORK],
        ["docker", "network", "inspect", "--format", "{{.Internal}}", ISOLATED_NETWORK],
    ]


def test_network_inspect_timeout_does_not_try_to_create(
    monkeypatch: MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    def timeout(command: list[str], *, timeout: int, **_kwargs: object) -> None:
        commands.append(command)
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(
        "plugins.dashboard.scripts.dashboard_launcher.subprocess.run",
        timeout,
    )

    with raises(RuntimeError, match="docker network inspect timed out after 30s"):
        ensure_isolated_network("docker")

    assert len(commands) == 1
    assert commands[0][1:3] == ["network", "inspect"]


def test_network_create_timeout_names_operation_and_timeout(
    monkeypatch: MonkeyPatch,
) -> None:
    calls = 0

    def run(
        command: list[str],
        *,
        timeout: int,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str] | None:
        nonlocal calls
        calls += 1
        if calls == 1:
            return subprocess.CompletedProcess(command, 1, "", "not found")
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(
        "plugins.dashboard.scripts.dashboard_launcher.subprocess.run",
        run,
    )

    with raises(RuntimeError, match="docker network create timed out after 30s"):
        ensure_isolated_network("docker")


def test_image_inspect_timeout_does_not_try_to_pull(monkeypatch: MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def timeout(command: list[str], *, timeout: int, **_kwargs: object) -> None:
        commands.append(command)
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(
        "plugins.dashboard.scripts.dashboard_launcher.shutil.which",
        _docker_on_path,
    )
    monkeypatch.setattr(
        "plugins.dashboard.scripts.dashboard_launcher.subprocess.run",
        timeout,
    )

    with raises(RuntimeError, match="docker image inspect timed out after 30s"):
        _image_ready("dashboard-tools:ci", pull=True)

    assert len(commands) == 1
    assert commands[0][1:3] == ["image", "inspect"]


def test_image_pull_timeout_names_operation_and_timeout(monkeypatch: MonkeyPatch) -> None:
    calls = 0

    def run(
        command: list[str],
        *,
        timeout: int,
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str] | None:
        nonlocal calls
        calls += 1
        if calls == 1:
            return subprocess.CompletedProcess(command, 1)
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(
        "plugins.dashboard.scripts.dashboard_launcher.shutil.which",
        _docker_on_path,
    )
    monkeypatch.setattr(
        "plugins.dashboard.scripts.dashboard_launcher.subprocess.run",
        run,
    )

    with raises(RuntimeError, match="docker pull timed out after 900s"):
        _image_ready("dashboard-tools:ci", pull=True)


def test_lock_ref_rejects_non_object_json(tmp_path: Path) -> None:
    for index, payload in enumerate(("[]", "null", '{"dashboard_tools": []}')):
        lock = tmp_path / f"lock-{index}.json"
        lock.write_text(payload, encoding="utf-8")
        assert _lock_ref(lock) is None


def test_default_docker_without_image_fails_closed(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    _clear_launch_environment(monkeypatch)
    monkeypatch.setattr(launcher.shutil, "which", _docker_on_path)
    monkeypatch.setattr(launcher, "image_pin", _no_image)
    commands = _capture_subprocess(monkeypatch)

    assert _run_launcher(monkeypatch, "doctor") == 1
    assert not commands
    error = capsys.readouterr().err
    assert "no image resolved from DASHBOARD_TOOLS_IMAGE" in error
    assert "configure a dashboard tools image" in error
    assert "dashboard_launcher.py prewarm" in error
    assert "DASHBOARD_LAUNCH_MODE=host" not in error


def test_default_docker_without_binary_fails_closed(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    _clear_launch_environment(monkeypatch)
    monkeypatch.setattr(launcher.shutil, "which", _no_docker)
    monkeypatch.setattr(launcher, "image_pin", _test_image)
    commands = _capture_subprocess(monkeypatch)

    assert _run_launcher(monkeypatch, "doctor") == 1
    assert not commands
    error = capsys.readouterr().err
    assert "docker is not on PATH" in error
    assert "install Docker" in error
    assert "dashboard_launcher.py prewarm" in error
    assert "DASHBOARD_LAUNCH_MODE=host" not in error


def test_default_docker_warn_emits_existing_json(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    _clear_launch_environment(monkeypatch)
    monkeypatch.setattr(launcher.shutil, "which", _docker_on_path)
    monkeypatch.setattr(launcher, "image_pin", _no_image)
    commands = _capture_subprocess(monkeypatch)

    assert _run_launcher(monkeypatch, "doctor", "--warn") == 0
    assert not commands
    captured = capsys.readouterr()
    warning = json.loads(captured.out)
    assert warning["verdict"] == "fail"
    assert "no image resolved from DASHBOARD_TOOLS_IMAGE" in warning["detail"]
    assert "dashboard_launcher.py prewarm" in warning["detail"]
    assert captured.err.startswith("warn:")


def test_host_mode_runs_on_host_when_image_exists(monkeypatch: MonkeyPatch) -> None:
    _clear_launch_environment(monkeypatch)
    monkeypatch.setenv("DASHBOARD_LAUNCH_MODE", "host")
    monkeypatch.setenv("DASHBOARD_SRC", str(ROOT / "src"))
    monkeypatch.setattr(launcher.shutil, "which", _docker_on_path)
    monkeypatch.setattr(launcher, "image_pin", _test_image)
    commands = _capture_subprocess(monkeypatch, returncode=17)

    assert _run_launcher(monkeypatch, "doctor") == 17
    assert commands == [[sys.executable, "-m", "dashboard", "doctor"]]


def test_host_mode_requires_explicit_source(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    _clear_launch_environment(monkeypatch)
    monkeypatch.setenv("DASHBOARD_LAUNCH_MODE", "host")
    monkeypatch.setattr(launcher.shutil, "which", _docker_on_path)
    monkeypatch.setattr(launcher, "image_pin", _test_image)
    commands = _capture_subprocess(monkeypatch)

    assert _run_launcher(monkeypatch, "doctor") == 1
    assert not commands
    assert "requires DASHBOARD_SRC" in capsys.readouterr().err


def test_host_mode_rejects_invalid_explicit_source(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    _clear_launch_environment(monkeypatch)
    monkeypatch.setenv("DASHBOARD_LAUNCH_MODE", "host")
    monkeypatch.setenv("DASHBOARD_SRC", str(tmp_path))
    monkeypatch.setattr(launcher.shutil, "which", _docker_on_path)
    monkeypatch.setattr(launcher, "image_pin", _test_image)
    commands = _capture_subprocess(monkeypatch)

    assert _run_launcher(monkeypatch, "doctor") == 1
    assert not commands
    assert "does not contain dashboard/__init__.py" in capsys.readouterr().err


def test_invalid_mode_exits_two_with_usage(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    _clear_launch_environment(monkeypatch)
    monkeypatch.setenv("DASHBOARD_LAUNCH_MODE", "auto")
    commands = _capture_subprocess(monkeypatch)

    assert _run_launcher(monkeypatch, "doctor") == 2
    assert not commands
    error = capsys.readouterr().err
    assert "usage:" in error
    assert "DASHBOARD_LAUNCH_MODE=docker|host" in error


def test_prewarm_rejects_auto_launch_mode(
    monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    _clear_launch_environment(monkeypatch)
    monkeypatch.setenv("DASHBOARD_LAUNCH_MODE", "auto")

    assert _run_launcher(monkeypatch, "prewarm") == 2
    assert "DASHBOARD_LAUNCH_MODE=docker|host" in capsys.readouterr().err


def test_default_docker_runs_image_when_available(monkeypatch: MonkeyPatch) -> None:
    _clear_launch_environment(monkeypatch)
    monkeypatch.setattr(launcher.shutil, "which", _docker_on_path)
    monkeypatch.setattr(launcher, "image_pin", _test_image)
    monkeypatch.setattr(
        "plugins.dashboard.scripts.dashboard_launcher._image_ready",
        _image_is_ready,
    )
    monkeypatch.setattr(launcher, "ensure_isolated_network", _network_ready)
    commands = _capture_subprocess(monkeypatch)

    assert _run_launcher(monkeypatch, "doctor") == 0
    assert commands[0][:2] == ["docker", "run"]
    assert "dashboard-tools:test" in commands[0]
    assert commands[0][-4:] == ["python", "-m", "dashboard", "doctor"]


def test_explicit_docker_mode_with_image_runs_docker(monkeypatch: MonkeyPatch) -> None:
    _clear_launch_environment(monkeypatch)
    monkeypatch.setenv("DASHBOARD_LAUNCH_MODE", "docker")
    monkeypatch.setattr(launcher.shutil, "which", _docker_on_path)
    monkeypatch.setattr(launcher, "image_pin", _test_image)
    monkeypatch.setattr(
        "plugins.dashboard.scripts.dashboard_launcher._image_ready",
        _image_is_ready,
    )
    monkeypatch.setattr(launcher, "ensure_isolated_network", _network_ready)
    commands = _capture_subprocess(monkeypatch)

    assert _run_launcher(monkeypatch, "doctor") == 0
    assert commands[0][:2] == ["docker", "run"]
    assert "dashboard-tools:test" in commands[0]
