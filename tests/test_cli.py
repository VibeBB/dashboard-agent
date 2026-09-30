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
