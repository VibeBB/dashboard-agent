"""Boundary and decision-table tests for the static contract gates.

Techniques follow docs/test-coverage.md: 3-value boundaries (below / on /
above) for the COBS frame-size limit and wire-type field ranges, and
decision tables for transport URL security, BLE UUID case, and protocol
uniqueness rules.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from dashboard.contract import load_contract
from dashboard.gates import check_contract

ROOT = Path(__file__).resolve().parents[1]
KETTLE = ROOT / "examples/smart-kettle/smart-kettle.dash.json"
BASE: dict[str, Any] = json.loads(KETTLE.read_text(encoding="utf-8"))


def _status(tmp_path: Path, data: dict[str, Any], check_id: str) -> tuple[str, str]:
    path = tmp_path / KETTLE.name
    path.write_text(json.dumps(data), encoding="utf-8")
    checks = check_contract(load_contract(path), path)
    found = next(check for check in checks if check.id == check_id)
    return found.status, found.detail


def _data() -> dict[str, Any]:
    return copy.deepcopy(BASE)


def _encoded(payload: int) -> int:
    raw = 2 + payload + 2
    return raw + math.ceil(raw / 254) + 2


# ------------------------------------------------------------ frame size


@pytest.mark.parametrize("payload", [10, 121, 250, 251])
@pytest.mark.parametrize(("offset", "status"), [(-1, "fail"), (0, "pass"), (1, "pass")])
def test_frame_size_three_value_boundary(
    tmp_path: Path, payload: int, offset: int, status: str
) -> None:
    data = _data()
    data["protocol"]["messages"][0]["fields"] = [
        {"name": f"f{index}", "type": "u8"} for index in range(payload)
    ]
    data["protocol"]["max_frame_bytes"] = _encoded(payload) + offset
    assert _status(tmp_path, data, "protocol.frame-size")[0] == status


def test_cobs_overhead_steps_at_254_raw_bytes() -> None:
    assert _encoded(250) == 254 + 1 + 2
    assert _encoded(251) == 255 + 2 + 2


# ----------------------------------------------------------- field range


def _field(tmp_path: Path, **field: Any) -> tuple[str, str]:
    data = _data()
    data["protocol"]["messages"][0]["fields"] = [{"name": "value", **field}]
    return _status(tmp_path, data, "protocol.field-range")


# i16 with scale 0.5 represents -16384.0 ... 16383.5 exactly.
@pytest.mark.parametrize(
    ("bound", "value", "status"),
    [
        ("min", -16384.5, "fail"),
        ("min", -16384.0, "pass"),
        ("min", -16383.5, "pass"),
        ("max", 16383.0, "pass"),
        ("max", 16383.5, "pass"),
        ("max", 16384.0, "fail"),
    ],
)
def test_scaled_field_range_three_value_boundary(
    tmp_path: Path, bound: str, value: float, status: str
) -> None:
    assert _field(tmp_path, type="i16", scale=0.5, **{bound: value})[0] == status


@pytest.mark.parametrize(
    ("wire", "low", "high"),
    [("u8", 0.0, 255.0), ("i8", -128.0, 127.0), ("u16", 0.0, 65535.0), ("bool", 0.0, 1.0)],
)
def test_unscaled_type_limits(tmp_path: Path, wire: str, low: float, high: float) -> None:
    assert _field(tmp_path, type=wire, min=low, max=high)[0] == "pass"
    assert _field(tmp_path, type=wire, min=low - 1.0)[0] == "fail"
    assert _field(tmp_path, type=wire, max=high + 1.0)[0] == "fail"


@pytest.mark.parametrize(
    ("low", "high", "status"), [(1.0, 2.0, "pass"), (2.0, 2.0, "fail"), (3.0, 2.0, "fail")]
)
def test_min_must_be_below_max(tmp_path: Path, low: float, high: float, status: str) -> None:
    status_seen, detail = _field(tmp_path, type="u8", min=low, max=high)
    assert status_seen == status
    assert ("min must be less than max" in detail) == (status == "fail")


def test_duplicate_field_names_fail(tmp_path: Path) -> None:
    data = _data()
    data["protocol"]["messages"][0]["fields"] = [
        {"name": "x", "type": "u8"},
        {"name": "x", "type": "u8"},
    ]
    status, detail = _status(tmp_path, data, "protocol.field-range")
    assert status == "fail"
    assert "duplicate fields x" in detail


# -------------------------------------------------------- protocol rules


@pytest.mark.parametrize(
    ("edit", "check_id"),
    [
        ({"id": 2}, "protocol.ids-unique"),
        ({"name": "set_target"}, "protocol.names-unique"),
    ],
)
def test_protocol_rules_fail(tmp_path: Path, edit: dict[str, Any], check_id: str) -> None:
    data = _data()
    data["protocol"]["messages"][0].update(edit)
    assert _status(tmp_path, data, check_id)[0] == "fail"
    assert _status(tmp_path, _data(), check_id)[0] == "pass"


# ------------------------------------------------------------ transports


def _transport(data: dict[str, Any], kind: str) -> dict[str, Any]:
    return next(item for item in data["transports"] if item["kind"] == kind)


# Decision table: scheme x loopback host.
@pytest.mark.parametrize(
    ("url", "status"),
    [
        ("wss://kettle.example/ws", "pass"),
        ("wss://localhost/ws", "pass"),
        ("ws://localhost:8080/ws", "pass"),
        ("ws://LOCALHOST:8080/ws", "pass"),
        ("ws://127.0.0.1/ws", "pass"),
        ("ws://[::1]:9000/ws", "pass"),
        ("ws://127.0.0.2/ws", "fail"),
        ("ws://kettle.example/ws", "fail"),
    ],
)
def test_websocket_url_decision_table(tmp_path: Path, url: str, status: str) -> None:
    data = _data()
    _transport(data, "websocket")["url"] = url
    assert _status(tmp_path, data, "transport.secure-url")[0] == status


def _rejected(tmp_path: Path, data: dict[str, Any], match: str) -> None:
    path = tmp_path / KETTLE.name
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValidationError, match=match):
        load_contract(path)


# The schema rejects these before the gate runs; the gate re-checks them as
# defence in depth for contracts constructed in memory.
@pytest.mark.parametrize("field", ["service_uuid", "rx_characteristic", "tx_characteristic"])
def test_uppercase_ble_uuid_is_rejected_by_the_schema(tmp_path: Path, field: str) -> None:
    data = _data()
    transport = _transport(data, "web_bluetooth")
    transport[field] = transport[field].upper()
    _rejected(tmp_path, data, "lowercase")


def test_ack_on_device_to_host_is_rejected_by_the_schema(tmp_path: Path) -> None:
    data = _data()
    data["protocol"]["messages"][0]["ack"] = True
    _rejected(tmp_path, data, "ack is only valid")


@pytest.mark.parametrize(("value", "ok"), [(15, False), (16, True), (512, True), (513, False)])
def test_max_frame_bytes_schema_bounds(tmp_path: Path, value: int, ok: bool) -> None:
    data = _data()
    data["protocol"]["max_frame_bytes"] = value
    if ok:
        assert _status(tmp_path, data, "protocol.frame-size")[0] == "pass"
    else:
        _rejected(tmp_path, data, "max_frame_bytes")


def test_unreferenced_transport_fails(tmp_path: Path) -> None:
    data = _data()
    extra = copy.deepcopy(_transport(data, "web_serial"))
    extra["id"] = "spare-serial"
    data["transports"].append(extra)
    status, detail = _status(tmp_path, data, "transport.used")
    assert status == "fail"
    assert "spare-serial" in detail
