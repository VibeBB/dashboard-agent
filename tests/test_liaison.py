from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import cast

import pytest
from mcp import types
from pydantic import ValidationError
from pytest import CaptureFixture, MonkeyPatch

from dashboard import cli, liaison, mcp_server, records, service

_NOW = "2025-01-02T03:04:05Z"
_DECISION_ID = "d" * 64
_IMPRESSION_ID = "i" * 64


def _request_document(
    root: Path,
    request_id: str,
    *,
    target: str = "dashboard",
    inputs: bool = True,
    depends_on: list[str] | None = None,
    risk: str = "low",
    rationale: str = "Review the dashboard interaction for the new device workflow.",
) -> dict[str, object]:
    hashed_inputs: list[dict[str, str]] = []
    if inputs:
        input_path = root / "device.txt"
        input_path.write_text("device contract input\n", encoding="utf-8")
        hashed_inputs.append(
            {
                "path": "device.txt",
                "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
            }
        )
    if risk == "high":
        ux_path = root / "design.ux.json"
        ux_path.write_text(
            json.dumps({"jobs": [{"id": "pump_control"}]}),
            encoding="utf-8",
        )
        hashed_inputs.append(
            {
                "path": "design.ux.json",
                "sha256": hashlib.sha256(ux_path.read_bytes()).hexdigest(),
            }
        )
    return {
        "schema_version": 2,
        "system": "ux-creator",
        "id": request_id,
        "target_agent": target,
        "stage": "design",
        "risk": risk,
        "purpose": "Review the new dashboard workflow and its operator controls.",
        "rationale": rationale,
        "requested_changes": ["Review the hazardous control presentation"],
        "inputs": hashed_inputs,
        "expected_deliverables": ["A reviewed dashboard interaction"],
        "acceptance": ["The operator can distinguish hazardous controls"],
        "depends_on": depends_on or [],
        "created_at": _NOW,
    }


def _write_request(
    root: Path,
    request_id: str,
    *,
    target: str = "dashboard",
    inputs: bool = True,
    depends_on: list[str] | None = None,
    risk: str = "low",
    rationale: str = "Review the dashboard interaction for the new device workflow.",
) -> Path:
    directory = root / "liaison"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{request_id}.ux-request.json"
    path.write_text(
        json.dumps(
            _request_document(
                root,
                request_id,
                target=target,
                inputs=inputs,
                depends_on=depends_on,
                risk=risk,
                rationale=rationale,
            )
        ),
        encoding="utf-8",
    )
    return path


def _write_response(
    root: Path,
    request_id: str,
    *,
    status: str = "accepted",
    responder: str = "dashboard",
    input_hashes: dict[str, str] | None = None,
    request: str | None = None,
) -> Path:
    directory = root / "liaison"
    path = directory / f"{request_id}.ux-response.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "system": "ux-creator",
                "request": request or request_id,
                "responder": responder,
                "status": status,
                "reason": (
                    "The dashboard review is complete with the requested evidence."
                    if status not in {"accepted", "in_progress"}
                    else ""
                ),
                "input_hashes": input_hashes or {},
                "artifacts": (
                    [{"path": "review.txt", "sha256": "a" * 64}] if status == "done" else []
                ),
                "gate_verdicts": (
                    [{"gate": "ui.full", "verdict": "pass"}] if status == "done" else []
                ),
                "decision_refs": [],
                "impression_refs": [],
                "questions_for_user": [],
                "responded_at": _NOW,
            }
        ),
        encoding="utf-8",
    )
    return path


def _record_refs(root: Path) -> None:
    directory = records.records_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / records.LOG_FILES["decision"]).write_text(
        json.dumps({"event_id": _DECISION_ID}) + "\n",
        encoding="utf-8",
    )
    (directory / records.LOG_FILES["stage_impression"]).write_text(
        json.dumps({"event_id": _IMPRESSION_ID}) + "\n",
        encoding="utf-8",
    )


def _write_gate_report(
    root: Path,
    *,
    verdict: str = "pass",
    scope: str = "full",
    check_status: str = "pass",
) -> Path:
    path = root / "out" / "full.dash-report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "system": "dashboard",
                "artifact_kind": "dashboard_gate_report",
                "design": "full",
                "scope": scope,
                "contract_sha256": "b" * 64,
                "verdict": verdict,
                "checks": [
                    {
                        "id": "ui.full",
                        "status": check_status,
                        "detail": "",
                        "evidence": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _done_payload(report: Path, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "request": "review-ui",
        "status": "done",
        "reason": "The dashboard implementation and validation are complete.",
        "artifacts": [str(report)],
        "gate_verdicts": [{"gate": "ui.full", "verdict": "pass"}],
        "decision_refs": [_DECISION_ID],
        "impression_refs": [_IMPRESSION_ID],
    }
    payload.update(overrides)
    return payload


async def _call_tool(name: str, arguments: dict[str, object]) -> types.CallToolResult:
    return cast(types.CallToolResult, await mcp_server.call_tool(name, arguments))


def _tool_payload(result: types.CallToolResult) -> dict[str, object]:
    assert len(result.content) == 1
    block = result.content[0]
    assert isinstance(block, types.TextContent)
    return cast(dict[str, object], json.loads(block.text))


def test_inbox_reports_new_requests_and_missing_directory(tmp_path: Path) -> None:
    missing = liaison.ux_inbox(root=tmp_path)
    assert missing["verdict"] == "pass"
    assert missing["requests"] == []
    assert missing["detail"] == "liaison directory does not exist"

    _write_request(tmp_path, "review-ui")
    inbox = liaison.ux_inbox(root=tmp_path)
    request = cast(list[dict[str, object]], inbox["requests"])[0]

    assert inbox["verdict"] == "pass"
    assert request["id"] == "review-ui"
    assert request["state"] == "new"
    assert request["final"] is False
    assert (
        request["request_sha256"]
        == hashlib.sha256(
            (tmp_path / "liaison" / "review-ui.ux-request.json").read_bytes()
        ).hexdigest()
    )
    assert inbox["counts"] == {"new": 1, "answered": 0, "stale": 0, "blocked": 0}


def test_inbox_classifies_valid_responses_as_answered(tmp_path: Path) -> None:
    _write_request(tmp_path, "review-ui")
    input_path = tmp_path / "device.txt"
    input_hash = hashlib.sha256(input_path.read_bytes()).hexdigest()
    _write_response(tmp_path, "review-ui", input_hashes={"device.txt": input_hash})

    inbox = liaison.ux_inbox(root=tmp_path)
    request = cast(list[dict[str, object]], inbox["requests"])[0]

    assert request["state"] == "answered"
    assert cast(dict[str, object], request["response"])["status"] == "accepted"
    assert inbox["counts"] == {"new": 0, "answered": 1, "stale": 0, "blocked": 0}


def test_inbox_marks_changed_request_inputs_stale(tmp_path: Path) -> None:
    _write_request(tmp_path, "review-ui")
    original_hash = hashlib.sha256((tmp_path / "device.txt").read_bytes()).hexdigest()
    _write_response(tmp_path, "review-ui", input_hashes={"device.txt": original_hash})
    (tmp_path / "device.txt").write_text("updated input\n", encoding="utf-8")

    inbox = liaison.ux_inbox(root=tmp_path)
    request = cast(list[dict[str, object]], inbox["requests"])[0]

    assert request["state"] == "stale"
    assert request["stale_inputs"] == ["device.txt"]
    assert (
        cast(list[dict[str, object]], request["inputs"])[0]["current_sha256"]
        == hashlib.sha256(b"updated input\n").hexdigest()
    )


def test_inbox_marks_response_hash_mismatch_stale(tmp_path: Path) -> None:
    _write_request(tmp_path, "review-ui")
    _write_response(tmp_path, "review-ui", input_hashes={})

    inbox = liaison.ux_inbox(root=tmp_path)
    request = cast(list[dict[str, object]], inbox["requests"])[0]

    assert request["state"] == "stale"
    assert request["stale_inputs"] == ["device.txt"]


def test_inbox_blocks_unanswered_dependencies_and_counts_other_targets(
    tmp_path: Path,
) -> None:
    _write_request(tmp_path, "upstream", target="firmware", inputs=False)
    _write_request(tmp_path, "review-ui", inputs=False, depends_on=["upstream"])

    inbox = liaison.ux_inbox(root=tmp_path)
    request = cast(list[dict[str, object]], inbox["requests"])[0]

    assert inbox["other_targets"] == 1
    assert request["state"] == "blocked"
    assert request["blocked_by"] == ["upstream"]


def test_inbox_accepts_done_dependencies_from_any_responder(tmp_path: Path) -> None:
    _write_request(tmp_path, "upstream", target="firmware", inputs=False)
    _write_response(tmp_path, "upstream", status="done", responder="wire")
    _write_request(tmp_path, "review-ui", inputs=False, depends_on=["upstream"])

    inbox = liaison.ux_inbox(root=tmp_path)
    request = next(
        item
        for item in cast(list[dict[str, object]], inbox["requests"])
        if item["id"] == "review-ui"
    )

    assert request["state"] == "new"
    assert request["blocked_by"] == []


def test_inbox_marks_dependency_cycles_blocked_and_circular(tmp_path: Path) -> None:
    _write_request(tmp_path, "alpha", inputs=False, depends_on=["beta"])
    _write_request(tmp_path, "beta", inputs=False, depends_on=["alpha"])

    inbox = liaison.ux_inbox(root=tmp_path)

    assert inbox["counts"] == {"new": 0, "answered": 0, "stale": 0, "blocked": 2}
    assert all(
        item["state"] == "blocked" and item["circular"] is True
        for item in cast(list[dict[str, object]], inbox["requests"])
    )


@pytest.mark.parametrize(
    ("case", "filename"),
    [
        ("invalid-json", "review-ui.ux-request.json"),
        ("extra-field", "review-ui.ux-request.json"),
        ("id-mismatch", "review-ui.ux-request.json"),
        ("naive-created-at", "review-ui.ux-request.json"),
        ("high-risk-without-ux", "review-ui.ux-request.json"),
        ("high-risk-without-job-id", "review-ui.ux-request.json"),
        ("high-risk-unreadable-ux", "review-ui.ux-request.json"),
    ],
)
def test_inbox_reports_malformed_requests(
    tmp_path: Path,
    case: str,
    filename: str,
) -> None:
    directory = tmp_path / "liaison"
    directory.mkdir()
    path = directory / filename
    if case == "invalid-json":
        path.write_text("{invalid", encoding="utf-8")
    else:
        value = _request_document(
            tmp_path,
            "review-ui",
            risk=(
                "high"
                if case
                in {
                    "high-risk-without-ux",
                    "high-risk-without-job-id",
                    "high-risk-unreadable-ux",
                }
                else "low"
            ),
            rationale=(
                "Please review the device controls carefully."
                if case == "high-risk-without-job-id"
                else "Review the dashboard interaction for the new device workflow."
            ),
        )
        if case == "extra-field":
            value["unexpected"] = True
        elif case == "id-mismatch":
            value["id"] = "different-id"
        elif case == "naive-created-at":
            value["created_at"] = "2025-01-02T03:04:05"
        elif case == "high-risk-without-ux":
            value["inputs"] = [
                item
                for item in cast(list[dict[str, str]], value["inputs"])
                if not item["path"].endswith(".ux.json")
            ]
        elif case == "high-risk-unreadable-ux":
            (tmp_path / "design.ux.json").write_text("{invalid", encoding="utf-8")
        path.write_text(json.dumps(value), encoding="utf-8")

    inbox = liaison.ux_inbox(root=tmp_path)

    assert inbox["verdict"] == "fail"
    assert inbox["requests"] == []
    assert cast(list[dict[str, str]], inbox["malformed"])[0]["path"] == str(path)


@pytest.mark.parametrize("mismatch", ["request", "responder"])
def test_invalid_matching_response_is_malformed_and_treated_as_absent(
    tmp_path: Path,
    mismatch: str,
) -> None:
    _write_request(tmp_path, "review-ui", inputs=False)
    _write_response(
        tmp_path,
        "review-ui",
        request="different-request" if mismatch == "request" else None,
        responder="firmware" if mismatch == "responder" else "dashboard",
    )

    inbox = liaison.ux_inbox(root=tmp_path)
    request = cast(list[dict[str, object]], inbox["requests"])[0]

    assert inbox["verdict"] == "fail"
    assert request["state"] == "new"
    assert request["response"] is None
    assert len(cast(list[object], inbox["malformed"])) == 1


def test_respond_rejects_short_reason_for_rejected_status(tmp_path: Path) -> None:
    _write_request(tmp_path, "review-ui", inputs=False)

    result = liaison.ux_respond(
        {"request": "review-ui", "status": "rejected", "reason": "No thanks."},
        root=tmp_path,
    )

    assert result["verdict"] == "fail"
    assert result["stage"] == "ux-respond"
    assert "20 non-whitespace characters" in cast(str, result["detail"])


@pytest.mark.parametrize("claimed_status", ["fail", "unknown"])
def test_respond_refuses_done_with_fail_or_unknown_gate(
    tmp_path: Path,
    claimed_status: str,
) -> None:
    _write_request(tmp_path, "review-ui", inputs=False)
    _record_refs(tmp_path)
    report = _write_gate_report(tmp_path)
    payload = _done_payload(
        report,
        gate_verdicts=[{"gate": "ui.full", "verdict": claimed_status}],
    )

    result = liaison.ux_respond(payload, root=tmp_path)

    assert result["verdict"] == "fail"


def test_respond_requires_a_passing_full_gate_report(tmp_path: Path) -> None:
    _write_request(tmp_path, "review-ui", inputs=False)
    _record_refs(tmp_path)
    other_artifact = tmp_path / "review.txt"
    other_artifact.write_text("reviewed", encoding="utf-8")

    result = liaison.ux_respond(
        _done_payload(other_artifact),
        root=tmp_path,
    )

    assert result["verdict"] == "fail"
    assert "passing full .dash-report.json" in cast(str, result["detail"])


def test_respond_refuses_gate_claims_that_mismatch_full_report(tmp_path: Path) -> None:
    _write_request(tmp_path, "review-ui", inputs=False)
    _record_refs(tmp_path)
    report = _write_gate_report(tmp_path)

    result = liaison.ux_respond(
        _done_payload(report, gate_verdicts=[{"gate": "ui.full", "verdict": "fail"}]),
        root=tmp_path,
    )

    assert result["verdict"] == "fail"
    assert "does not match" in cast(str, result["detail"])


def test_respond_rejects_unknown_decision_event_ids(tmp_path: Path) -> None:
    _write_request(tmp_path, "review-ui", inputs=False)
    report = _write_gate_report(tmp_path)
    payload = _done_payload(report, decision_refs=["e" * 64])

    result = liaison.ux_respond(payload, root=tmp_path)

    assert result["verdict"] == "fail"
    assert "unknown decision_refs" in cast(str, result["detail"])


def test_respond_rejects_unknown_impression_event_ids(tmp_path: Path) -> None:
    _write_request(tmp_path, "review-ui", inputs=False)
    _record_refs(tmp_path)
    report = _write_gate_report(tmp_path)
    payload = _done_payload(report, impression_refs=["e" * 64])

    result = liaison.ux_respond(payload, root=tmp_path)

    assert result["verdict"] == "fail"
    assert "unknown impression_refs" in cast(str, result["detail"])


def test_respond_refuses_done_for_stale_inputs(tmp_path: Path) -> None:
    _write_request(tmp_path, "review-ui")
    (tmp_path / "device.txt").write_text("changed after request\n", encoding="utf-8")
    _record_refs(tmp_path)
    report = _write_gate_report(tmp_path)

    result = liaison.ux_respond(_done_payload(report), root=tmp_path)

    assert result["verdict"] == "fail"
    assert "inputs are stale" in cast(str, result["detail"])


def test_respond_refuses_done_until_dependencies_are_done(tmp_path: Path) -> None:
    _write_request(tmp_path, "upstream", inputs=False)
    _write_request(tmp_path, "review-ui", inputs=False, depends_on=["upstream"])
    _record_refs(tmp_path)
    report = _write_gate_report(tmp_path)

    result = liaison.ux_respond(_done_payload(report), root=tmp_path)

    assert result["verdict"] == "fail"
    assert "dependencies are not done: upstream" in cast(str, result["detail"])


def test_respond_done_writes_hashed_artifacts_and_inputs(tmp_path: Path) -> None:
    _write_request(tmp_path, "review-ui")
    _record_refs(tmp_path)
    report = _write_gate_report(tmp_path)
    result = liaison.ux_respond(_done_payload(report), root=tmp_path)

    assert result["verdict"] == "pass"
    response = cast(dict[str, object], result["response"])
    assert response["responder"] == "dashboard"
    assert response["status"] == "done"
    input_hashes = cast(dict[str, str], response["input_hashes"])
    assert (
        input_hashes["device.txt"]
        == hashlib.sha256((tmp_path / "device.txt").read_bytes()).hexdigest()
    )
    artifact = cast(list[dict[str, str]], response["artifacts"])[0]
    assert artifact == {
        "path": "out/full.dash-report.json",
        "sha256": hashlib.sha256(report.read_bytes()).hexdigest(),
    }
    written = json.loads(Path(cast(str, result["path"])).read_text(encoding="utf-8"))
    assert written == response


def test_respond_allows_needs_info_when_an_input_is_missing(tmp_path: Path) -> None:
    _write_request(tmp_path, "review-ui")
    (tmp_path / "device.txt").unlink()

    result = liaison.ux_respond(
        {
            "request": "review-ui",
            "status": "needs_info",
            "reason": "The source input is missing; please provide its current version.",
            "questions_for_user": ["Can you restore the device contract file?"],
        },
        root=tmp_path,
    )

    assert result["verdict"] == "pass"
    assert cast(dict[str, object], result["response"])["input_hashes"] == {}


def test_mcp_and_cli_route_ux_liaison_tools(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    captured: dict[str, object] = {}

    def inbox(liaison_dir: Path | None = None) -> service.Json:
        captured["liaison_dir"] = liaison_dir
        return {"verdict": "pass", "stage": "ux-inbox", "requests": []}

    def respond(payload: dict[str, object]) -> service.Json:
        captured["response_payload"] = payload
        return {"verdict": "pass", "stage": "ux-respond"}

    monkeypatch.setattr(service, "ux_inbox_payload", inbox)
    monkeypatch.setattr(service, "ux_respond_payload", respond)
    tools = {tool.name: tool for tool in mcp_server.tool_specs()}
    assert tools["dashboard_ux_inbox"].annotations is not None
    assert tools["dashboard_ux_inbox"].annotations.readOnlyHint is True
    assert tools["dashboard_ux_respond"].annotations is not None
    assert tools["dashboard_ux_respond"].annotations.readOnlyHint is False

    inbox_result = asyncio.run(_call_tool("dashboard_ux_inbox", {}))
    assert inbox_result.isError is False
    assert _tool_payload(inbox_result)["stage"] == "ux-inbox"
    response_payload: dict[str, object] = {"request": "review-ui", "status": "accepted"}
    respond_result = asyncio.run(_call_tool("dashboard_ux_respond", response_payload))
    assert respond_result.isError is False
    assert captured["response_payload"] == response_payload

    liaison_dir = tmp_path / "liaison"
    assert cli.main(["ux-inbox", "--liaison-dir", str(liaison_dir)]) == 0
    assert captured["liaison_dir"] == liaison_dir
    assert json.loads(capsys.readouterr().out)["stage"] == "ux-inbox"
    payload_path = tmp_path / "response.json"
    payload_path.write_text(json.dumps(response_payload), encoding="utf-8")
    assert cli.main(["ux-respond", "--json", str(payload_path)]) == 0
    assert captured["response_payload"] == response_payload
    assert json.loads(capsys.readouterr().out) == {
        "verdict": "pass",
        "stage": "ux-respond",
    }


def test_hashed_path_rejects_absolute_and_escaping_paths() -> None:
    for path in ("/outside/file.ux.json", "../outside.ux.json", "C:\\outside.ux.json"):
        with pytest.raises(ValidationError):
            liaison.HashedPath(path=path, sha256="a" * 64)


def test_family_request_id_with_dot_and_underscore_is_accepted(tmp_path: Path) -> None:
    _write_request(tmp_path, "kettle.panel_v2")
    inbox = liaison.ux_inbox(root=tmp_path)
    request = cast(list[dict[str, object]], inbox["requests"])[0]
    assert inbox["verdict"] == "pass"
    assert request["id"] == "kettle.panel_v2"
    assert request["state"] == "new"
