from __future__ import annotations

from pathlib import Path

from plugins.dashboard.scripts.dashboard_launcher import (
    _docker,  # pyright: ignore[reportPrivateUsage]
    _inner_args,  # pyright: ignore[reportPrivateUsage]
    image_ref,
    resolve_source,
)
from pytest import MonkeyPatch

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


def test_container_invocation_mounts_source_and_disables_network() -> None:
    command = _docker(
        "dashboard-tools:ci",
        ROOT / "src",
        ["python", "-m", "dashboard", "doctor"],
    )

    assert command[command.index("--network") + 1] == "none"
    assert f"{ROOT / 'src'}:/opt/dashboard/src:ro" in command
    assert "PYTHONPATH=/opt/dashboard/src" in command
    assert command[-4:] == ["python", "-m", "dashboard", "doctor"]
