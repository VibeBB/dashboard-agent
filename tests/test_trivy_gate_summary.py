from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from scripts.trivy_gate_summary import fixable_findings, main, render_markdown

TRIVY_JSON: dict[str, Any] = {
    "Results": [
        {
            "Target": "ghcr.io/vibebb/dashboard-tools (debian 13.1)",
            "Vulnerabilities": [
                {
                    "VulnerabilityID": "CVE-2026-1",
                    "PkgName": "tar",
                    "InstalledVersion": "7.5.16",
                    "FixedVersion": "7.5.17",
                    "Severity": "CRITICAL",
                },
                {
                    "VulnerabilityID": "CVE-2026-2",
                    "PkgName": "undici",
                    "InstalledVersion": "1.0.0",
                    "FixedVersion": "1.0.1",
                    "Severity": "HIGH",
                },
                {
                    "VulnerabilityID": "CVE-2026-3",
                    "PkgName": "unfixable",
                    "InstalledVersion": "9.9",
                    "Severity": "CRITICAL",
                },
                {
                    "VulnerabilityID": "CVE-2026-4",
                    "PkgName": "medium-thing",
                    "InstalledVersion": "1.0",
                    "FixedVersion": "1.1",
                    "Severity": "MEDIUM",
                },
            ],
        }
    ]
}


def test_fixable_findings_filter_severity_and_fixed_version(tmp_path: Path) -> None:
    findings = fixable_findings(TRIVY_JSON)

    assert [finding["id"] for finding in findings] == ["CVE-2026-1", "CVE-2026-2"]
    assert findings[0]["fixed"] == "7.5.17"


def test_render_markdown_lists_the_gated_cves() -> None:
    markdown = render_markdown(fixable_findings(TRIVY_JSON))

    assert "CVE-2026-1" in markdown
    assert "tar" in markdown
    assert "unfixable" not in markdown
    assert "2 fixable HIGH/CRITICAL finding(s)." in markdown


def test_empty_report_renders_a_clear_note() -> None:
    markdown = render_markdown([])

    assert "No fixable HIGH/CRITICAL" in markdown


def test_main_prints_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "trivy-image.json"
    path.write_text(json.dumps(TRIVY_JSON), encoding="utf-8")

    assert main([str(path)]) == 0
    assert "CVE-2026-2" in capsys.readouterr().out
