from __future__ import annotations

import json
from pathlib import Path

from pytest import CaptureFixture, MonkeyPatch

from dashboard import cli, service


def test_screenshot_command_routes_to_service(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    contract = tmp_path / "dashboard.dash.json"
    output = tmp_path / "out"
    captured: dict[str, object] = {}

    def screenshot(path: Path, out_dir: Path | None) -> service.Json:
        captured.update({"contract": path, "out_dir": out_dir})
        return {"verdict": "pass"}

    monkeypatch.setattr(service, "screenshot_payload", screenshot)

    assert cli.main(["screenshot", str(contract), "--out", str(output)]) == 0
    assert captured == {"contract": contract, "out_dir": output}
    assert json.loads(capsys.readouterr().out) == {"verdict": "pass"}


def test_record_command_routes_json_payload_to_service(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    record_file = tmp_path / "decision.json"
    record_file.write_text('{"id":"dashboard-transport"}', encoding="utf-8")
    captured: dict[str, object] = {}

    def record(kind: str, payload: dict[str, object]) -> service.Json:
        captured.update({"kind": kind, "payload": payload})
        return {"verdict": "pass", "stage": "record"}

    monkeypatch.setattr(service, "record_payload", record)

    assert cli.main(["record", "decision", "--json", str(record_file)]) == 0
    assert captured == {"kind": "decision", "payload": {"id": "dashboard-transport"}}
    assert json.loads(capsys.readouterr().out) == {"verdict": "pass", "stage": "record"}


def test_record_status_routes_to_service(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        service,
        "records_status_payload",
        lambda: {"verdict": "pass", "stage": "record", "counts": {}},
    )

    assert cli.main(["record", "status"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "verdict": "pass",
        "stage": "record",
        "counts": {},
    }
