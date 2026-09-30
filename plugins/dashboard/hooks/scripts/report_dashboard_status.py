#!/usr/bin/env python3
"""Add recent dashboard gate verdicts to stop-hook context."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import cast

SKIP_DIRECTORIES = {".git", ".venv", "__pycache__", "node_modules", ".cache"}
MAX_DEPTH = 5


def _find_reports(root: Path) -> list[Path]:
    reports: list[Path] = []
    for current, directories, files in os.walk(root):
        directory = Path(current)
        try:
            depth = len(directory.relative_to(root).parts)
        except ValueError:
            continue
        if depth >= MAX_DEPTH:
            directories.clear()
        else:
            directories[:] = sorted(name for name in directories if name not in SKIP_DIRECTORIES)
        reports.extend(directory / name for name in files if name.endswith(".dash-report.json"))
    return sorted(reports)


def _check_ids(checks: list[object], status: str) -> list[str]:
    found: list[str] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        check = cast(dict[str, object], check)
        if check.get("status") == status:
            found.append(str(check.get("id", "unknown")))
    return found


def main() -> int:
    try:
        event = json.load(sys.stdin)
        root = Path(event.get("working_dir") or os.getcwd()).resolve()
        lines: list[str] = []
        for path in _find_reports(root):
            try:
                report = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                lines.append(f"{path}: unreadable report ({exc})")
                continue
            if not isinstance(report, dict):
                lines.append(f"{path}: unreadable report (expected a JSON object)")
                continue
            report = cast(dict[str, object], report)
            if "verdict" not in report:
                lines.append(f"{path}: unreadable report (missing verdict)")
                continue
            lines.append(f"{path}: verdict={report.get('verdict', 'unknown')}")
            checks = report.get("checks", [])
            if not isinstance(checks, list):
                checks = []
            checks = cast(list[object], checks)
            failures = _check_ids(checks, "fail")
            if failures:
                lines.append(f"Failing dashboard gates: {', '.join(failures)}")
            unknown = _check_ids(checks, "unknown")
            if unknown:
                lines.append(f"Unknown dashboard gates: {', '.join(unknown)}")
        context = "\n".join(lines) if lines else f"No dashboard reports found under {root}."
        print(json.dumps({"decision": "allow", "additionalContext": context}))
        return 0
    except Exception as exc:
        print(f"report_dashboard_status: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
