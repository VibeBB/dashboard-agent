from __future__ import annotations

import io
import json
from pathlib import Path

from plugins.dashboard.hooks.scripts import report_dashboard_status
from pytest import CaptureFixture, MonkeyPatch


def _run(
    root: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> str:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"working_dir": str(root)})))
    assert report_dashboard_status.main() == 0
    return capsys.readouterr().out


def test_report_lists_failed_and_unknown_checks(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    (tmp_path / "result.dash-report.json").write_text(
        json.dumps(
            {
                "verdict": "fail",
                "checks": [
                    {"id": "types", "status": "fail"},
                    {"id": "servo", "status": "unknown"},
                ],
            }
        ),
        encoding="utf-8",
    )

    output = _run(tmp_path, monkeypatch, capsys)

    assert "verdict=fail" in output
    assert "Failing dashboard gates: types" in output
    assert "Unknown dashboard gates: servo" in output


def test_report_marks_unreadable_non_object_and_missing_verdict(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    (tmp_path / "invalid.dash-report.json").write_text("{invalid", encoding="utf-8")
    (tmp_path / "array.dash-report.json").write_text("[]", encoding="utf-8")
    (tmp_path / "missing.dash-report.json").write_text('{"checks": []}', encoding="utf-8")

    output = _run(tmp_path, monkeypatch, capsys)

    assert f"{tmp_path / 'invalid.dash-report.json'}: unreadable report (" in output
    assert (
        f"{tmp_path / 'array.dash-report.json'}: unreadable report (expected a JSON object)"
        in output
    )
    assert f"{tmp_path / 'missing.dash-report.json'}: unreadable report (missing verdict)" in output


def test_report_lists_unanswered_dashboard_ux_requests(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    liaison = tmp_path / "liaison"
    liaison.mkdir()
    (liaison / "awaiting-dashboard.ux-request.json").write_text(
        json.dumps({"id": "awaiting-dashboard", "target_agent": "dashboard"}),
        encoding="utf-8",
    )
    (liaison / "answered.ux-request.json").write_text(
        json.dumps({"id": "answered", "target_agent": "dashboard"}),
        encoding="utf-8",
    )
    (liaison / "answered.ux-response.json").write_text("{}", encoding="utf-8")
    (liaison / "other-target.ux-request.json").write_text(
        json.dumps({"id": "other-target", "target_agent": "firmware"}),
        encoding="utf-8",
    )
    (tmp_path / "not-in-liaison.ux-request.json").write_text(
        json.dumps({"id": "not-in-liaison", "target_agent": "dashboard"}),
        encoding="utf-8",
    )

    output = _run(tmp_path, monkeypatch, capsys)

    context = json.loads(output)["additionalContext"]
    assert (
        "1 UX request(s) awaiting a dashboard response: awaiting-dashboard — run dashboard_ux_inbox"
    ) in context
