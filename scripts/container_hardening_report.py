#!/usr/bin/env python3
"""Aggregate the weekly container-hardening report.

Reads the full Trivy JSON scan, the Docker CIS compliance JSON, and the
Lynis report written by container-audit.yml, and emits
container-hardening.json. CIS failures whose IDs are documented deferred
policy decisions (docs/operations.md "Container hardening") are reported
as accepted instead of noise; a scan that produced no CIS results fails —
dead telemetry must not masquerade as coverage.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

# CIS check IDs that are deferred policy decisions — see docs/operations.md
# "Container hardening" (non-root USER and HEALTHCHECK enforcement).
ACCEPTED_CIS_FAILURES = frozenset({"DS-0002", "DS-0026"})


def _object(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [_object(item) for item in cast(list[Any], value) if isinstance(item, dict)]


def _summaries(node: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield node
    for child in _items(node.get("Results")):
        yield from _summaries(child)


def _cis_totals(cis_data: dict[str, Any]) -> dict[str, Any]:
    passed = failed = 0
    failed_ids: list[str] = []
    for result in _summaries(cis_data):
        summary = _object(result.get("MisconfSummary"))
        passed += int(summary.get("Successes") or 0)
        failed += int(summary.get("Failures") or 0)
        for misconfig in _items(result.get("Misconfigurations")):
            if misconfig.get("Status") == "FAIL":
                check_id = misconfig.get("ID") or misconfig.get("AVDID") or "?"
                failed_ids.append(str(check_id))
    return {
        "passed": passed,
        "failed": failed,
        "accepted_policy_failures": sorted(
            check_id for check_id in failed_ids if check_id in ACCEPTED_CIS_FAILURES
        ),
        "unexpected_failure_ids": sorted(
            check_id for check_id in failed_ids if check_id not in ACCEPTED_CIS_FAILURES
        ),
    }


def cis_payload_nonempty(cis_path: Path) -> bool:
    try:
        cis_data: Any = json.loads(cis_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(cis_data, dict):
        return False
    totals = _cis_totals(_object(cis_data))
    return int(totals["passed"]) + int(totals["failed"]) > 0


def build_report(
    *,
    trivy_path: Path,
    cis_path: Path,
    lynis_report: Path | None,
    image_ref: str,
) -> dict[str, Any]:
    trivy = _object(json.loads(trivy_path.read_text(encoding="utf-8")))
    vulns: Counter[str] = Counter()
    secrets: Counter[str] = Counter()
    licenses = 0
    mis_pass = mis_total = 0
    fixable_high = 0
    for result in _items(trivy.get("Results")):
        for v in _items(result.get("Vulnerabilities")):
            sev = str(v.get("Severity") or "UNKNOWN").lower()
            fixed = bool(v.get("FixedVersion"))
            vulns[sev] += 1
            if fixed:
                vulns[f"{sev}_fixed"] += 1
                if sev in ("critical", "high"):
                    fixable_high += 1
        for m in _items(result.get("Misconfigurations")):
            mis_total += 1
            if m.get("Status") == "PASS":
                mis_pass += 1
        for s in _items(result.get("Secrets")):
            secrets[str(s.get("Severity") or "UNKNOWN").lower()] += 1
        licenses += len(_items(result.get("Licenses")))
    cis_data = _object(json.loads(cis_path.read_text(encoding="utf-8")))
    cis = _cis_totals(cis_data)
    if cis["passed"] + cis["failed"] == 0:
        # dead telemetry must fail, not masquerade as coverage
        sys.exit("Docker CIS scan produced no results")
    lynis: dict[str, Any] = {"hardening_index": "unknown", "warnings": 0}
    if lynis_report is not None:
        try:
            for line in lynis_report.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("hardening_index="):
                    lynis["hardening_index"] = line.split("=", 1)[1].strip()
                elif line.startswith("warning[]"):
                    lynis["warnings"] += 1
        except OSError:
            pass
    image, _, digest = image_ref.partition("@")
    return {
        "image": image,
        "digest": digest,
        "trivy": {
            "critical": vulns["critical"],
            "high": vulns["high"],
            "medium": vulns["medium"],
            "low": vulns["low"],
            "fixable_high_or_critical": fixable_high,
            "misconfig_pass": mis_pass,
            "misconfig_total": mis_total,
            "secrets": sum(secrets.values()),
            "license_findings": licenses,
        },
        "cis_docker": cis,
        "lynis": lynis,
        "gate": {"fixable_high_or_critical": fixable_high},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trivy-json", type=Path)
    parser.add_argument("--cis-json", type=Path)
    parser.add_argument("--lynis-report", type=Path)
    parser.add_argument("--image-ref", default="")
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--check-cis",
        type=Path,
        metavar="PATH",
        help="exit 0 only when the CIS JSON contains a non-empty result payload",
    )
    args = parser.parse_args(argv)
    if args.check_cis is not None:
        if cis_payload_nonempty(args.check_cis):
            return 0
        print(f"CIS report {args.check_cis} has no results", file=sys.stderr)
        return 1
    missing = [
        flag
        for flag, value in (
            ("--trivy-json", args.trivy_json),
            ("--cis-json", args.cis_json),
            ("--out", args.out),
        )
        if value is None
    ]
    if missing:
        parser.error(f"missing required arguments: {', '.join(missing)}")
    report = build_report(
        trivy_path=args.trivy_json,
        cis_path=args.cis_json,
        lynis_report=args.lynis_report,
        image_ref=args.image_ref,
    )
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.out.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
