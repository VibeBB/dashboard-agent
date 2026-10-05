from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import cast

from mcp import types
from pytest import CaptureFixture, MonkeyPatch

from dashboard import cli, mcp_server, service
from dashboard.contract import ImportRef
from dashboard.requests import write_request

ROOT = Path(__file__).resolve().parents[1]
_DECISION_ID = "d" * 64


def _workspace_contract(root: Path, *, firmware: bool) -> Path:
    value = json.loads(
        (ROOT / "examples/bench-meter/bench-meter.dash.json").read_text(encoding="utf-8")
    )
    if firmware:
        firmware_path = root / "firmware.json"
        firmware_path.write_text('{"artifact_kind":"firmware_contract"}\n', encoding="utf-8")
        value["device"] = {
            "firmware_contract": "firmware.json",
            "firmware_sha256": hashlib.sha256(firmware_path.read_bytes()).hexdigest(),
        }
    contract_path = root / "demo.dash.json"
    contract_path.write_text(json.dumps(value), encoding="utf-8")
    return contract_path


def _write_decision(root: Path, event_id: str = _DECISION_ID) -> None:
    directory = root / "observations" / "dashboard"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "decisions.jsonl").write_text(
        json.dumps({"event_id": event_id}) + "\n",
        encoding="utf-8",
    )


def test_outbound_request_is_schema_v2_with_hashed_contract_inputs(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    contract = _workspace_contract(tmp_path, firmware=True)
    _write_decision(tmp_path)

    request, path = write_request(
        contract,
        "bench-meter",
        tmp_path / "out",
        target="fpga",
        risk="high",
        change="Add display scaling",
        rationale="Align the display with the calibrated signal range.",
        failing_checks=["widgets.binding"],
        decision_refs=[_DECISION_ID],
    )
    serialized = json.loads(path.read_text(encoding="utf-8"))

    assert serialized["schema_version"] == 2
    assert serialized["target"] == "fpga"
    assert serialized["decision_refs"] == [_DECISION_ID]
    assert [(item["path"], item["sha256"]) for item in serialized["inputs"]] == [
        ("demo.dash.json", hashlib.sha256(contract.read_bytes()).hexdigest()),
        (
            "firmware.json",
            hashlib.sha256((tmp_path / "firmware.json").read_bytes()).hexdigest(),
        ),
    ]
    assert request.inputs[0].path == "demo.dash.json"


def test_outbound_request_requires_known_decision_for_high_risk(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    contract = _workspace_contract(tmp_path, firmware=False)

    result = service.request_payload(
        contract,
        tmp_path / "out",
        target="firmware",
        risk="high",
        change="Adjust packet timing",
        rationale="Update the firmware timing contract for reconnect safety.",
        failing_checks=[],
        decision_refs=[],
    )

    assert result["verdict"] == "fail"
    assert "decision_ref" in cast(str, result["detail"])


def test_outbound_request_rejects_unknown_decision_refs(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    contract = _workspace_contract(tmp_path, firmware=False)

    result = service.request_payload(
        contract,
        tmp_path / "out",
        target="wire",
        risk="low",
        change="Add serial transport",
        rationale="The device needs a bounded serial transport option.",
        failing_checks=[],
        decision_refs=["e" * 64],
    )

    assert result["verdict"] == "fail"
    assert "unknown decision_refs" in cast(str, result["detail"])


def test_import_refs_accept_sibling_family() -> None:
    for system in (
        "firmware",
        "circuit",
        "ux-creator",
        "mech",
        "wire",
        "bard",
        "fpga",
        "sim",
        "prodeng",
        "doc",
    ):
        reference = ImportRef.model_validate(
            {"from_system": system, "path": "contract.json", "sha256": "a" * 64}
        )
        assert reference.from_system == system


def test_cli_and_mcp_request_args_accept_repeatable_decision_refs(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}

    def request(
        contract_path: Path,
        out_dir: Path | None,
        **kwargs: object,
    ) -> service.Json:
        captured.update({"contract_path": contract_path, "out_dir": out_dir, **kwargs})
        return {"verdict": "pass"}

    monkeypatch.setattr(service, "request_payload", request)
    contract = tmp_path / "demo.dash.json"
    contract.write_text("{}", encoding="utf-8")
    cli.main(
        [
            "request",
            str(contract),
            "--target",
            "fpga",
            "--risk",
            "low",
            "--change",
            "Add display scaling",
            "--rationale",
            "Match the interface to the calibrated display.",
            "--decision-ref",
            _DECISION_ID,
            "--decision-ref",
            "c" * 64,
        ]
    )
    assert captured["decision_refs"] == [_DECISION_ID, "c" * 64]

    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))

    async def call_request() -> types.CallToolResult:
        return cast(
            types.CallToolResult,
            await mcp_server.call_tool(
                "dashboard_request",
                {
                    "contract_path": str(contract),
                    "target": "fpga",
                    "risk": "low",
                    "change": "Add display scaling",
                    "rationale": "Match the interface to the calibrated display.",
                    "decision_refs": [_DECISION_ID, "c" * 64],
                },
            ),
        )

    result = asyncio.run(call_request())
    assert result.isError is False
    assert captured["decision_refs"] == [_DECISION_ID, "c" * 64]
    tool = next(tool for tool in mcp_server.tool_specs() if tool.name == "dashboard_request")
    target = cast(dict[str, object], tool.inputSchema["properties"])
    target_values = cast(dict[str, object], target["target"])["enum"]
    assert "fpga" in cast(list[str], target_values)
    assert json.loads(capsys.readouterr().out)["verdict"] == "pass"
