"""Decode a status field through the hash-pinned firmware fault table."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from .contract import DashboardContract, Widget, resolve
from .interchange import sha256_file

SEVERITIES = ("info", "warning", "error", "critical")
UNSIGNED_MAX = {"u8": 0xFF, "u16": 0xFFFF, "u32": 0xFFFFFFFF}


def fault_widgets(contract: DashboardContract) -> list[Widget]:
    return [widget for widget in contract.widgets if widget.kind == "fault"]


def _source_widths(contract: DashboardContract, widgets: list[Widget]) -> tuple[int, list[str]]:
    """Smallest unsigned range among fault sources, and non-integer sources."""
    problems: list[str] = []
    width = UNSIGNED_MAX["u32"]
    messages = {message.name: message for message in contract.protocol.messages}
    for widget in widgets:
        if widget.source is None or "." not in widget.source:
            continue
        message_name, field_name = widget.source.split(".", 1)
        message = messages.get(message_name)
        field = (
            None
            if message is None
            else next((item for item in message.fields if item.name == field_name), None)
        )
        if field is None:
            continue
        if field.type not in UNSIGNED_MAX:
            problems.append(
                f"{widget.id}: fault source {widget.source} must be an unsigned integer"
            )
        else:
            width = min(width, UNSIGNED_MAX[field.type])
    return width, problems


def _fault_entry(item: object, limit: int) -> dict[str, object] | None:
    if not isinstance(item, dict):
        return None
    entry = cast(dict[str, object], item)
    code = entry.get("code")
    name = entry.get("name")
    severity = entry.get("severity")
    action = entry.get("action")
    if (
        not isinstance(code, int)
        or isinstance(code, bool)
        or not 1 <= code <= limit
        or not isinstance(name, str)
        or not name
        or severity not in SEVERITIES
        or not isinstance(action, str)
        or not action
    ):
        return None
    return {"code": code, "name": name, "severity": severity, "action": action}


def load_faults(
    contract: DashboardContract, contract_path: Path
) -> tuple[list[dict[str, object]] | None, list[str]]:
    """Return the decoded fault table for fault widgets, or the reasons it is unusable."""
    widgets = fault_widgets(contract)
    if not widgets:
        return None, []
    limit, problems = _source_widths(contract, widgets)
    path_text = contract.device.firmware_contract
    if path_text is None:
        return None, [*problems, "fault widgets require device.firmware_contract"]
    path = resolve(contract_path, path_text)
    if not path.is_file():
        return None, [*problems, f"{path_text}: file not found"]
    if sha256_file(path) != contract.device.firmware_sha256:
        return None, [*problems, f"{path_text}: sha256 mismatch"]
    try:
        artifact = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, [*problems, f"{path_text}: invalid JSON: {exc}"]
    raw = cast(dict[str, object], artifact).get("faults") if isinstance(artifact, dict) else None
    if not isinstance(raw, list) or not raw:
        return None, [*problems, f"{path_text}: declares no faults"]
    faults: list[dict[str, object]] = []
    for index, item in enumerate(cast(list[object], raw)):
        entry = _fault_entry(item, limit)
        if entry is None:
            problems.append(
                f"{path_text}: faults[{index}] is malformed or exceeds the source range"
            )
        elif any(known["code"] == entry["code"] for known in faults):
            problems.append(f"{path_text}: duplicate fault code {entry['code']}")
        else:
            faults.append(entry)
    return (None if problems else faults), problems
