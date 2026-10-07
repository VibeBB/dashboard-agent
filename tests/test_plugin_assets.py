from __future__ import annotations

import json
from pathlib import Path

from plugins.dashboard.hooks.scripts.protect_generated import is_protected
from plugins.dashboard.hooks.scripts.safety_rail import evaluate

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/dashboard"


def test_plugin_assets_have_expected_manifest_and_entry_points() -> None:
    manifest = json.loads((PLUGIN / ".plugin/plugin.json").read_text(encoding="utf-8"))
    hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text(encoding="utf-8"))
    mcp = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))

    assert manifest["name"] == "dashboard"
    assert set(mcp["mcpServers"]) == {"dashboard"}
    assert set(hooks) == {
        "session_start",
        "user_prompt_submit",
        "pre_tool_use",
        "post_tool_use",
        "stop",
    }
    assert {path.stem for path in (PLUGIN / "agents").glob("*.md")} == {
        "dashboard-architect",
        "dashboard-developer",
        "dashboard-review",
    }
    assert {path.stem for path in (PLUGIN / "commands").glob("*.md")} == {
        "design",
        "doctor",
        "gates",
        "generate",
        "screenshot",
        "smoke",
    }
    assert {path.parent.name for path in (PLUGIN / "skills").glob("*/SKILL.md")} == {
        "dashboard-contract",
        "dashboard-contract-rules",
        "dashboard-out-rules",
        "dashboard-platform-matrix",
        "dashboard-tauri",
        "dashboard-protocol",
        "dashboard-servo",
        "dashboard-sibling-cooperation",
        "dashboard-transports",
        "dashboard-wasm",
        "dashboard-webmcp",
        "dashboard-workflow",
    }


def test_generated_artifacts_are_protected() -> None:
    for path in (
        "examples/smart-kettle/out/smart-kettle/index.html",
        "out/smart-kettle.screens/desktop.png",
        "out/dashboard.config.json",
        "examples/kettle/kettle.dash-protocol.h",
        "examples/kettle/kettle.dash-protocol.json",
        "examples/kettle/kettle.dash-report.json",
        "observations/dashboard/image-observations.jsonl",
        "observations/dashboard/vision-tool-events.jsonl",
        "observations/dashboard/decisions.jsonl",
        "observations/dashboard/impressions.jsonl",
        "observations/dashboard/vision-reviews.jsonl",
        "observations/dashboard/records-status.json",
        "liaison/example.ux-response.json",
        "intake/attachments/manifest.jsonl",
    ):
        assert is_protected(path)
    assert not is_protected("examples/smart-kettle/smart-kettle.dash.json")
    assert not is_protected("observations/wire/records-status.json")
    assert not is_protected("other/example.ux-response.json")


def test_liaison_responses_are_protected_only_in_liaison_directories() -> None:
    assert is_protected("liaison/request-id.ux-response.json")
    assert is_protected("nested/liaison/request-id.ux-response.json")
    assert not is_protected("requests/request-id.ux-response.json")


def test_tauri_generated_platform_projects_are_user_owned() -> None:
    assert not is_protected(
        "examples/smart-kettle/out/smart-kettle/tauri/src-tauri/gen/android/device_filter.xml"
    )
    assert is_protected("examples/smart-kettle/out/smart-kettle/tauri/src-tauri/Cargo.toml")
    assert is_protected(
        "examples/smart-kettle/out/smart-kettle/tauri/src-tauri/gen/../../Cargo.toml"
    )


def test_safety_rail_blocks_destructive_git_operations() -> None:
    assert evaluate("git reset --hard") is not None
    assert evaluate("git add .") is not None
    assert evaluate("git push --force feature") is not None
    assert evaluate("git push origin main") is not None
    assert evaluate("git status --short") is None
