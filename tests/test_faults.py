from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from dashboard.contract import load_contract
from dashboard.faults import load_faults
from dashboard.gates import check_contract
from dashboard.generate import build_config, generate

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/smart-kettle/smart-kettle.dash.json"
FAULTS: list[dict[str, Any]] = [
    {"code": 1, "name": "dry_boil", "severity": "critical", "action": "Fill the kettle"},
    {"code": 2, "name": "scale", "severity": "warning", "action": "Descale the kettle"},
]


def _write(tmp_path: Path, faults: object = FAULTS, *, field_type: str = "u8") -> Path:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    for message in data["protocol"]["messages"]:
        for field in message["fields"]:
            if field["name"] == "error_code":
                field["type"] = field_type
    data["widgets"].append(
        {"id": "fault", "kind": "fault", "label": "Fault", "source": "status.error_code"}
    )
    firmware = {"system": "firmware", "artifact_kind": "firmware_contract", "faults": faults}
    firmware_path = tmp_path / "kettle.fw.json"
    firmware_path.write_text(json.dumps(firmware), encoding="utf-8")
    data["device"] = {
        "firmware_contract": "kettle.fw.json",
        "firmware_sha256": hashlib.sha256(firmware_path.read_bytes()).hexdigest(),
    }
    path = tmp_path / "kettle.dash.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _status(path: Path) -> tuple[str, str]:
    check = next(c for c in check_contract(load_contract(path), path) if c.id == "service.faults")
    return check.status, check.detail


def test_no_fault_widget_is_not_applicable() -> None:
    assert _status(EXAMPLE)[0] == "not_applicable"


def test_pinned_fault_table_passes_and_is_embedded(tmp_path: Path) -> None:
    path = _write(tmp_path)
    assert _status(path)[0] == "pass"
    faults, problems = load_faults(load_contract(path), path)
    assert problems == []
    config = build_config(load_contract(path), "0" * 64, faults)
    assert config["faults"] == FAULTS


def test_changed_firmware_contract_fails(tmp_path: Path) -> None:
    path = _write(tmp_path)
    (tmp_path / "kettle.fw.json").write_text("{}", encoding="utf-8")
    assert _status(path) == ("fail", "kettle.fw.json: sha256 mismatch")


def test_missing_firmware_link_fails(tmp_path: Path) -> None:
    path = _write(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["device"] = {}
    path.write_text(json.dumps(data), encoding="utf-8")
    assert _status(path) == ("fail", "fault widgets require device.firmware_contract")


@pytest.mark.parametrize(
    "faults",
    [
        [],
        "dry_boil",
        [{"code": 1, "name": "dry_boil", "severity": "fatal", "action": "x"}],
        [{"code": True, "name": "dry_boil", "severity": "error", "action": "x"}],
        [{"code": 1, "name": "", "severity": "error", "action": "x"}],
        [FAULTS[0], {**FAULTS[1], "code": 1}],
    ],
)
def test_malformed_fault_table_fails(tmp_path: Path, faults: object) -> None:
    assert _status(_write(tmp_path, faults))[0] == "fail"


@pytest.mark.parametrize(
    ("code", "status"), [(0, "fail"), (1, "pass"), (255, "pass"), (256, "fail")]
)
def test_fault_code_must_fit_the_source_field(tmp_path: Path, code: int, status: str) -> None:
    faults = [{"code": code, "name": "dry_boil", "severity": "error", "action": "Fill"}]
    assert _status(_write(tmp_path, faults))[0] == status


def test_non_integer_source_fails(tmp_path: Path) -> None:
    status, detail = _status(_write(tmp_path, field_type="i16"))
    assert status == "fail"
    assert "must be an unsigned integer" in detail


def test_generate_refuses_an_unusable_fault_table(tmp_path: Path) -> None:
    path = _write(tmp_path, [])
    with pytest.raises(ValueError, match="fault table unusable"):
        generate(path, tmp_path / "out")
