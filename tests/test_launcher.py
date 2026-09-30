from __future__ import annotations

import subprocess
from pathlib import Path

from plugins.dashboard.scripts.dashboard_launcher import (
    ISOLATED_NETWORK,
    _docker,  # pyright: ignore[reportPrivateUsage]
    _image_ready,  # pyright: ignore[reportPrivateUsage]
    _inner_args,  # pyright: ignore[reportPrivateUsage]
    _lock_ref,  # pyright: ignore[reportPrivateUsage]
    ensure_isolated_network,
    image_ref,
    resolve_source,
)
from pytest import MonkeyPatch, raises

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/dashboard"


def _docker_on_path(_name: str) -> str:
    return "docker"


def test_launcher_resolves_checkout_source_and_supports_host_and_image_commands(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("DASHBOARD_TOOLS_IMAGE", raising=False)

    assert resolve_source(PLUGIN) == ROOT / "src"
    assert image_ref(PLUGIN) is None
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
