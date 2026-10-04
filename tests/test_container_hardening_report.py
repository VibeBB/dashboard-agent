from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from scripts.container_hardening_report import (
    ACCEPTED_CIS_FAILURES,
    build_report,
    cis_payload_nonempty,
    main,
)

TRIVY_JSON: dict[str, Any] = {
    "Results": [
        {
            "Vulnerabilities": [
                {"Severity": "CRITICAL", "FixedVersion": "1.2.3"},
                {"Severity": "HIGH", "FixedVersion": ""},
                {"Severity": "HIGH", "FixedVersion": "2.0.0"},
                {"Severity": "MEDIUM", "FixedVersion": "3.0.0"},
            ],
            "Misconfigurations": [{"Status": "PASS"}, {"Status": "FAIL"}],
            "Secrets": [{"Severity": "HIGH"}],
            "Licenses": [{"Name": "MIT"}],
        }
    ]
}

CIS_JSON: dict[str, Any] = {
    "Results": [
        {
            "Results": [
                {
                    "MisconfSummary": {"Successes": 10, "Failures": 2},
                    "Misconfigurations": [
                        {"ID": "DS-0002", "Status": "FAIL"},
                        {"ID": "DS-0026", "Status": "FAIL"},
                        {"ID": "DS-0001", "Status": "PASS"},
                    ],
                }
            ]
        }
    ]
}

CIS_EMPTY: dict[str, Any] = {"Results": [{"Results": [{"Misconfigurations": []}]}]}


def _write(tmp_path: Path, name: str, payload: object) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_cis_aggregation_counts_nested_summaries(tmp_path: Path) -> None:
    cis_path = _write(tmp_path, "cis.json", CIS_JSON)

    report = build_report(
        trivy_path=_write(tmp_path, "trivy.json", TRIVY_JSON),
        cis_path=cis_path,
        lynis_report=None,
        image_ref="ghcr.io/vibebb/dashboard-tools@sha256:" + "ab" * 32,
    )

    assert report["cis_docker"]["passed"] == 10
    assert report["cis_docker"]["failed"] == 2
    assert sorted(report["cis_docker"]["accepted_policy_failures"]) == sorted(ACCEPTED_CIS_FAILURES)
    assert report["cis_docker"]["unexpected_failure_ids"] == []
    assert report["trivy"]["critical"] == 1
    assert report["trivy"]["high"] == 2
    assert report["trivy"]["fixable_high_or_critical"] == 2
    assert report["gate"]["fixable_high_or_critical"] == 2
    assert report["trivy"]["misconfig_pass"] == 1
    assert report["trivy"]["misconfig_total"] == 2
    assert report["trivy"]["secrets"] == 1
    assert report["trivy"]["license_findings"] == 1


def test_cis_unexpected_failures_are_distinguished(tmp_path: Path) -> None:
    cis = json.loads(json.dumps(CIS_JSON))
    cis["Results"][0]["Results"][0]["Misconfigurations"].append({"ID": "DS-0007", "Status": "FAIL"})
    cis["Results"][0]["Results"][0]["MisconfSummary"]["Failures"] = 3

    report = build_report(
        trivy_path=_write(tmp_path, "trivy.json", TRIVY_JSON),
        cis_path=_write(tmp_path, "cis.json", cis),
        lynis_report=None,
        image_ref="image@sha256:" + "cd" * 32,
    )

    assert report["cis_docker"]["unexpected_failure_ids"] == ["DS-0007"]
    assert report["cis_docker"]["accepted_policy_failures"] == [
        "DS-0002",
        "DS-0026",
    ]


def test_empty_cis_payload_fails_the_report(tmp_path: Path) -> None:
    cis_path = _write(tmp_path, "cis.json", CIS_EMPTY)

    assert cis_payload_nonempty(cis_path) is False
    with pytest.raises(SystemExit):
        build_report(
            trivy_path=_write(tmp_path, "trivy.json", TRIVY_JSON),
            cis_path=cis_path,
            lynis_report=None,
            image_ref="image@sha256:" + "ef" * 32,
        )


def test_check_cis_mode_for_the_retry_loop(tmp_path: Path) -> None:
    good = _write(tmp_path, "cis.json", CIS_JSON)
    empty = _write(tmp_path, "cis-empty.json", CIS_EMPTY)
    malformed = tmp_path / "cis-malformed.json"
    malformed.write_text("{not json", encoding="utf-8")

    assert main(["--check-cis", str(good)]) == 0
    assert main(["--check-cis", str(empty)]) == 1
    assert main(["--check-cis", str(malformed)]) == 1
    assert cis_payload_nonempty(good) is True


def test_report_writes_json_and_lynis_metrics(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    lynis = tmp_path / "lynis-report.dat"
    lynis.write_text("hardening_index=61\nwarning[]=AUTH-9000:test\n", encoding="utf-8")

    assert (
        main(
            [
                "--trivy-json",
                str(_write(tmp_path, "trivy.json", TRIVY_JSON)),
                "--cis-json",
                str(_write(tmp_path, "cis.json", CIS_JSON)),
                "--lynis-report",
                str(lynis),
                "--image-ref",
                "ghcr.io/vibebb/dashboard-tools@sha256:" + "0a" * 32,
                "--out",
                str(out),
            ]
        )
        == 0
    )

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["lynis"] == {"hardening_index": "61", "warnings": 1}
    assert report["image"] == "ghcr.io/vibebb/dashboard-tools"
