from __future__ import annotations

from pathlib import Path

from dashboard.contract import load_contract
from dashboard.webmcp import definitions, json_schema_valid

ROOT = Path(__file__).resolve().parents[1]


def test_smart_kettle_webmcp_tools_are_safety_annotated() -> None:
    contract = load_contract(ROOT / "examples/smart-kettle/smart-kettle.dash.json")
    tools = definitions(contract)

    assert [tool["name"] for tool in tools] == [
        "dashboard_status",
        "read_telemetry",
        "send_set_target",
        "send_start_boil",
    ]
    assert tools[0]["annotations"] == {"readOnlyHint": True}
    assert tools[1]["annotations"] == {
        "readOnlyHint": True,
        "untrustedContentHint": True,
    }
    assert tools[2]["annotations"] == {"consequentialHint": False}
    assert tools[3]["annotations"] == {"consequentialHint": True}
    assert all(json_schema_valid(tool["inputSchema"]) for tool in tools)


def test_bench_meter_webmcp_is_read_only() -> None:
    contract = load_contract(ROOT / "examples/bench-meter/bench-meter.dash.json")
    tools = definitions(contract)

    assert [tool["name"] for tool in tools] == ["dashboard_status", "read_telemetry"]
    assert tools[0]["annotations"] == {"readOnlyHint": True}
    assert tools[1]["annotations"] == {
        "readOnlyHint": True,
        "untrustedContentHint": True,
    }
