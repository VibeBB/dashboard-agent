from __future__ import annotations

from pathlib import Path

from dashboard.contract import load_contract
from dashboard.gates import Check, check_contract, run_gates

ROOT = Path(__file__).resolve().parents[1]


def _check_by_id(checks: list[Check], check_id: str) -> Check:
    return next(check for check in checks if check.id == check_id)


def test_example_contracts_pass_static_gates() -> None:
    for path in (
        ROOT / "examples/smart-kettle/smart-kettle.dash.json",
        ROOT / "examples/bench-meter/bench-meter.dash.json",
    ):
        report = run_gates(path, path.parent / "out", full=False)
        assert report.verdict == "pass", report.model_dump_json(indent=2)


def test_gate_reports_duplicate_protocol_ids() -> None:
    path = ROOT / "examples/smart-kettle/smart-kettle.dash.json"
    contract = load_contract(path)
    messages = list(contract.protocol.messages)
    duplicate = messages[0].model_copy(update={"id": messages[1].id})
    protocol = contract.protocol.model_copy(update={"messages": [*messages, duplicate]})
    malformed = contract.model_copy(update={"protocol": protocol})

    checks = check_contract(malformed, path)

    assert _check_by_id(checks, "protocol.ids-unique").status == "fail"
    assert _check_by_id(checks, "platform.caveats-acknowledged").status == "pass"
