#!/usr/bin/env python3
"""Render the fixable HIGH/CRITICAL findings behind a Trivy gate failure.

Reads the full Trivy JSON report produced before the SARIF gate and emits a
markdown table for $GITHUB_STEP_SUMMARY so a publish failure names the
offending CVEs without a log download.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast

MAX_ROWS = 50


def _object(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [_object(item) for item in cast(list[Any], value) if isinstance(item, dict)]


def fixable_findings(report: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for result in _items(report.get("Results")):
        target = str(result.get("Target") or "")
        for vuln in _items(result.get("Vulnerabilities")):
            if vuln.get("Severity") not in ("CRITICAL", "HIGH"):
                continue
            fixed = vuln.get("FixedVersion")
            if not fixed:
                continue
            findings.append(
                {
                    "id": str(vuln.get("VulnerabilityID") or "?"),
                    "package": str(vuln.get("PkgName") or "?"),
                    "installed": str(vuln.get("InstalledVersion") or "?"),
                    "fixed": str(fixed),
                    "severity": str(vuln.get("Severity")),
                    "target": target,
                }
            )
    return findings


def render_markdown(findings: list[dict[str, str]]) -> str:
    lines = ["## Trivy gate findings", ""]
    if not findings:
        lines.append("No fixable HIGH/CRITICAL vulnerabilities parsed from the report.")
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            "| CVE | Package | Installed | Fixed in | Severity |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for finding in findings[:MAX_ROWS]:
        lines.append(
            f"| {finding['id']} | {finding['package']} | "
            f"{finding['installed']} | {finding['fixed']} | {finding['severity']} |"
        )
    if len(findings) > MAX_ROWS:
        lines.append(f"| … | {len(findings) - MAX_ROWS} more | | | |")
    lines.extend(["", f"{len(findings)} fixable HIGH/CRITICAL finding(s)."])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trivy_json", type=Path)
    args = parser.parse_args(argv)
    report = _object(json.loads(args.trivy_json.read_text(encoding="utf-8")))
    print(render_markdown(fixable_findings(report)), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
