#!/usr/bin/env python3
"""Reject direct writes to generated dashboard applications and reports."""

from __future__ import annotations

import json
import shlex
import sys
from typing import Any

PATH_KEYS = ("path", "file_path", "paths", "target_file", "new_path")
PATCH_PREFIXES = ("*** Update File:", "*** Add File:", "*** Delete File:", "*** Move to:")
WRITE_TOOLS = {"file_editor", "apply_patch"}
WRITE_ACTIONS = {"create", "str_replace", "insert", "edit", "write"}


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _strings(child)]
    return []


def _is_tauri_generated_state(parts: list[str]) -> bool:
    if ".." in parts:
        return False
    for out_index, part in enumerate(parts):
        if part != "out":
            continue
        for index in range(out_index + 1, len(parts) - 2):
            if parts[index : index + 3] == ["tauri", "src-tauri", "gen"]:
                return True
    return False


def is_protected(value: str) -> bool:
    normalized = value.replace("\\", "/").lower().split("#", 1)[0]
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    name = parts[-1] if parts else ""
    if _is_tauri_generated_state(parts):
        return False
    return (
        "out" in parts
        or name == "dash-manifest.json"
        or (name.endswith(".dash-protocol.h") or name.endswith(".dash-protocol.json"))
        or name.endswith(".dash-report.json")
        or name.endswith(".dash-report.md")
    )


def _paths(tool_input: dict[str, Any], tool_name: str) -> list[str]:
    found = [value for key in PATH_KEYS for value in _strings(tool_input.get(key))]
    patch = tool_input.get("patch")
    if tool_name == "apply_patch" and isinstance(patch, str):
        for line in patch.splitlines():
            for prefix in PATCH_PREFIXES:
                if line.startswith(prefix):
                    found.append(line[len(prefix) :].strip())
                    break
    return found


def _terminal_target(command: str) -> str | None:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    for index, token in enumerate(tokens[:-1]):
        if token in {">", ">>", "2>", "2>>", "&>"} and is_protected(tokens[index + 1]):
            return tokens[index + 1]
    for index, token in enumerate(tokens):
        name = token.rsplit("/", 1)[-1]
        if name in {"cp", "mv", "install", "rsync"} and tokens[index + 1 :]:
            target = tokens[-1]
            if is_protected(target):
                return target
        if name in {"tee", "touch", "rm", "mkdir", "truncate"}:
            for operand in tokens[index + 1 :]:
                if not operand.startswith("-") and is_protected(operand):
                    return operand
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"invalid hook input: {exc}", file=sys.stderr)
        return 2
    if not isinstance(payload, dict):
        return 0
    name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    paths = _paths(tool_input, str(name))
    if name in WRITE_TOOLS and any(is_protected(path) for path in paths):
        action = tool_input.get("command") or tool_input.get("action")
        if (
            name == "apply_patch"
            or action in WRITE_ACTIONS
            or any(key in tool_input for key in ("file_text", "new_str", "content", "insert_text"))
        ):
            print(f"generated dashboard artifact is read-only: {paths[0]}", file=sys.stderr)
            return 2
    if name == "terminal" and isinstance(tool_input.get("command"), str):
        target = _terminal_target(tool_input["command"])
        if target:
            print(f"generated dashboard artifact is read-only: {target}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
