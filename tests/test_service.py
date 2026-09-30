from __future__ import annotations

from pathlib import Path
from typing import cast

from dashboard.service import matrix_payload, screenshot_payload, validate_payload

ROOT = Path(__file__).resolve().parents[1]


def test_matrix_payload_includes_bsd_network_only_routes() -> None:
    payload = matrix_payload()
    rows = payload["rows"]
    assert isinstance(rows, list)
    bsd_rows = [
        cast(dict[str, object], row)
        for row in cast(list[object], rows)
        if isinstance(row, dict) and cast(dict[str, object], row).get("os") == "bsd"
    ]

    assert {(row["browser"], row["transport"]) for row in bsd_rows} == {
        ("chrome", "websocket"),
        ("chrome", "webrtc"),
        ("firefox", "websocket"),
        ("firefox", "webrtc"),
    }
    caveats = payload["caveats"]
    assert isinstance(caveats, dict)
    assert "bsd-hardware-apis-unverified" in cast(dict[str, object], caveats)


def test_validation_payload_accepts_ipados_contract_declarations() -> None:
    payload = validate_payload(ROOT / "examples/smart-kettle/smart-kettle.dash.json")

    assert payload["verdict"] == "pass"
    platforms = payload["platforms"]
    assert isinstance(platforms, list)
    platform_names = cast(list[object], platforms)
    assert platform_names.count("ios") == 1
    assert platform_names.count("ipados") == 1


def test_screenshot_payload_requires_fresh_generation(tmp_path: Path) -> None:
    contract = ROOT / "examples/smart-kettle/smart-kettle.dash.json"

    payload = screenshot_payload(contract, tmp_path / "out")

    assert payload["verdict"] == "fail"
    assert payload["stage"] == "screenshot"
    assert "cannot load generation manifest" in cast(str, payload["detail"])
    assert payload["images"] == []
