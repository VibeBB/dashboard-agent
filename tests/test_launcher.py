from __future__ import annotations

import subprocess
from pathlib import Path

from plugins.dashboard.scripts.dashboard_launcher import (
    ISOLATED_NETWORK,
    _docker,  # pyright: ignore[reportPrivateUsage]
    _inner_args,  # pyright: ignore[reportPrivateUsage]
    ensure_isolated_network,
    image_ref,
    resolve_source,
)
from pytest import MonkeyPatch, raises

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/dashboard"


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
