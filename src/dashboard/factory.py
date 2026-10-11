"""Read the pinned prodeng factory-test spec into the factory view configuration."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

from .contract import DashboardContract
from .interchange import sha256_file

BAUD = re.compile(r"(\d+)\s*baud")


def load_factory(
    contract: DashboardContract, contract_path: Path
) -> tuple[dict[str, object] | None, list[str]]:
    """Return the runtime factory config, or the problems that make it unusable."""
    config = contract.factory
    if config is None:
        return None, []
    path = Path(config.spec)
    if not path.is_absolute():
        path = contract_path.resolve().parent / path
    if not path.is_file():
        return None, [f"{config.spec}: file not found"]
    if sha256_file(path) != config.spec_sha256:
        return None, [f"{config.spec}: sha256 mismatch"]
    try:
        document: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, [f"{config.spec}: invalid JSON: {exc}"]
    spec = cast(dict[str, object], document) if isinstance(document, dict) else {}
    problems: list[str] = []
    if spec.get("declared") is not True:
        problems.append("spec declares no factory test mode")
    raw_interface = spec.get("interface")
    interface = cast(dict[str, object], raw_interface) if isinstance(raw_interface, dict) else {}
    if interface.get("transport") != "uart":
        problems.append(f"factory view drives uart only, spec uses {interface.get('transport')}")
    transport = next((item for item in contract.transports if item.id == config.transport), None)
    if transport is None or transport.kind != "web_serial":
        problems.append(f"{config.transport}: factory transport must be a declared web_serial")
    else:
        match = BAUD.search(str(interface.get("settings", "")))
        if match is None:
            problems.append("spec interface settings name no baud rate")
        elif int(match.group(1)) != transport.baud_rate:
            problems.append(
                f"spec baud {match.group(1)} != {transport.id} baud_rate {transport.baud_rate}"
            )
    commands: list[dict[str, object]] = []
    raw_commands = spec.get("commands")
    if not isinstance(raw_commands, list) or not raw_commands:
        problems.append("spec lists no commands")
    else:
        for index, raw in enumerate(cast(list[object], raw_commands)):
            item = cast(dict[str, object], raw) if isinstance(raw, dict) else {}
            texts = [item.get(key) for key in ("id", "name", "request", "response_pattern")]
            timeout = item.get("timeout_ms")
            destructive = item.get("destructive")
            if (
                not all(isinstance(text, str) and text for text in texts)
                or isinstance(timeout, bool)
                or not isinstance(timeout, int)
                or timeout <= 0
                or not isinstance(destructive, bool)
            ):
                problems.append(f"command {index}: malformed")
                continue
            commands.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "request": item["request"],
                    "response_pattern": item["response_pattern"],
                    "timeout_ms": timeout,
                    "destructive": destructive,
                }
            )
    if problems:
        return None, problems
    return {
        "spec_sha256": config.spec_sha256,
        "transport": config.transport,
        "commands": commands,
        "exit": str(spec.get("exit", "")),
    }, []
