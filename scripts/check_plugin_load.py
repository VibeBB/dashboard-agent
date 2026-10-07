"""Load plugins/dashboard through the OpenHands SDK and assert expected assets."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "dashboard"
EXPECTED_AGENTS = {"dashboard-architect", "dashboard-developer", "dashboard-review"}
EXPECTED_SKILLS = {
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
EXPECTED_COMMANDS = {"design", "doctor", "gates", "generate", "screenshot", "smoke"}
EXPECTED_HOOKS: dict[str, set[str]] = {
    "session_start": {
        "dashboard-doctor",
        "intake-attachments",
        "ensure-llm-profiles",
        "ensure-agent-profiles",
        "require-records",
    },
    "user_prompt_submit": {"intake-attachments"},
    "pre_tool_use": {"protect-generated", "safety-rail"},
    "stop": {"intake-attachments", "report-dashboard-status", "require-records"},
    "post_tool_use": {"record-vision-tool-event", "record-image-observation"},
}


def _registered_tools() -> set[str]:
    import openhands.tools.preset.default  # pyright: ignore[reportMissingImports,reportMissingModuleSource]
    from openhands.sdk.tool.registry import (  # pyright: ignore[reportMissingImports,reportMissingModuleSource]
        list_registered_tools,
    )

    openhands.tools.preset.default.register_default_tools(enable_browser=False)
    import openhands.tools.glob.definition  # pyright: ignore[reportMissingImports,reportMissingModuleSource,reportUnusedImport]
    import openhands.tools.grep.definition  # pyright: ignore[reportMissingImports,reportMissingModuleSource,reportUnusedImport]
    import openhands.tools.task.definition  # pyright: ignore[reportMissingImports,reportMissingModuleSource,reportUnusedImport]
    from openhands.sdk.tool.builtins import (  # pyright: ignore[reportMissingImports,reportMissingModuleSource]
        BUILT_IN_TOOL_CLASSES,
    )

    return set(list_registered_tools()) | set(BUILT_IN_TOOL_CLASSES)


def check_plugin(plugin_path: Path = PLUGIN) -> list[str]:
    from openhands.sdk.plugin import (
        Plugin,  # pyright: ignore[reportMissingImports,reportMissingModuleSource]
    )

    try:
        plugin = Plugin.load(plugin_path)
    except Exception as exc:
        return [f"Plugin.load failed: {exc}"]
    reasons: list[str] = []
    manifest = json.loads((plugin_path / ".plugin" / "plugin.json").read_text(encoding="utf-8"))
    if plugin.manifest.version != manifest.get("version"):
        reasons.append(
            f"manifest version {plugin.manifest.version!r} != "
            f"plugin.json {manifest.get('version')!r}"
        )
    for label, actual, expected in (
        ("agents", {item.name for item in plugin.agents}, EXPECTED_AGENTS),
        ("skills", {item.name for item in plugin.skills}, EXPECTED_SKILLS),
        ("commands", {item.name for item in plugin.commands}, EXPECTED_COMMANDS),
    ):
        if actual != expected:
            reasons.append(f"{label} {sorted(actual)} != {sorted(expected)}")
    if plugin.hooks is not None:
        collected: dict[str, set[str]] = {name: set() for name in EXPECTED_HOOKS}
        for event_name in collected:
            groups: list[Any] = getattr(plugin.hooks, event_name, None) or []
            for group in groups:
                collected[event_name].update(
                    hook.name for hook in group.hooks if hook.name is not None
                )
        for event_name, expected in EXPECTED_HOOKS.items():
            if collected[event_name] != expected:
                reasons.append(
                    f"{event_name} hooks {sorted(collected[event_name])} != {sorted(expected)}"
                )
    else:
        reasons.append("plugin hooks were not loaded")
    registered = _registered_tools()
    for agent in plugin.agents:
        for tool in agent.tools:
            if tool not in registered:
                reasons.append(f"agent {agent.name!r} tool {tool!r} not registered")
    for command in plugin.commands:
        for tool in command.allowed_tools:
            if tool not in registered:
                reasons.append(f"command {command.name!r} allowed-tool {tool!r} not registered")
    return reasons


def main() -> int:
    reasons = check_plugin()
    if reasons:
        print("\n".join(reasons), file=sys.stderr)
        return 1
    print("plugin-load OK: dashboard agents, skills, and commands")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
