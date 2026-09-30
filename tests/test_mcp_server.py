from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import cast

from mcp import types
from pytest import MonkeyPatch, raises

from dashboard import mcp_server, service
from dashboard.workspace import workspace_path


async def _call_tool(name: str, arguments: dict[str, object]) -> types.CallToolResult:
    return cast(types.CallToolResult, await mcp_server.call_tool(name, arguments))


def _result_payload(result: types.CallToolResult) -> dict[str, object]:
    assert result.content
    block = result.content[0]
    assert isinstance(block, types.TextContent)
    return cast(dict[str, object], json.loads(block.text))


def _dispatch_for(verdict: str):
    def dispatch(_name: str, _arguments: dict[str, object]) -> service.Json:
        return {"verdict": verdict, "detail": "gate result"}

    return dispatch


def test_call_tool_marks_unknown_tool_as_error() -> None:
    result = asyncio.run(_call_tool("missing_tool", {}))

    assert result.isError is True
    assert _result_payload(result) == {
        "verdict": "fail",
        "detail": "unknown tool missing_tool",
    }


def test_call_tool_marks_handler_exceptions_as_errors(
    monkeypatch: MonkeyPatch,
) -> None:
    def fail(_name: str, _arguments: dict[str, object]) -> service.Json:
        raise KeyError("contract_path")

    monkeypatch.setattr(mcp_server, "dispatch", fail)

    result = asyncio.run(_call_tool("dashboard_validate", {}))
    payload = _result_payload(result)

    assert result.isError is True
    assert payload["verdict"] == "fail"
    assert payload["error_type"] == "KeyError"
    assert payload["detail"] == "dashboard_validate error: 'contract_path'"


def test_service_failure_verdict_is_not_an_mcp_error(monkeypatch: MonkeyPatch) -> None:
    for verdict in ("fail", "unknown"):
        monkeypatch.setattr(mcp_server, "dispatch", _dispatch_for(verdict))
        result = asyncio.run(_call_tool("dashboard_check", {}))

        assert result.isError is False
        assert _result_payload(result)["verdict"] == verdict


def test_workspace_path_accepts_relative_and_absolute_inside_paths(
    tmp_path: Path,
) -> None:
    inside = tmp_path / "contract.json"
    inside.write_text("{}", encoding="utf-8")

    assert workspace_path("contract.json", tmp_path) == inside
    assert workspace_path(inside, tmp_path) == inside


def test_workspace_path_rejects_traversal_outside_and_symlink(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / "outside.json"
    link = tmp_path / "linked"
    link.symlink_to(tmp_path.parent, target_is_directory=True)

    with raises(ValueError, match="outside the workspace"):
        workspace_path("../outside.json", tmp_path)
    with raises(ValueError, match="outside the workspace"):
        workspace_path(outside, tmp_path)
    with raises(ValueError, match="symlink"):
        workspace_path("linked/outside.json", tmp_path)


def test_dispatch_resolves_contract_and_output_paths_within_workspace(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    captured: dict[str, object] = {}

    def validate(path: Path) -> service.Json:
        captured["contract"] = path
        return {"verdict": "pass"}

    def gates(path: Path, out_dir: Path | None, *, full: bool) -> service.Json:
        captured.update({"contract": path, "out_dir": out_dir, "full": full})
        return {"verdict": "pass"}

    monkeypatch.setattr(service, "validate_payload", validate)
    monkeypatch.setattr(service, "gates_payload", gates)

    mcp_server.dispatch("dashboard_validate", {"contract_path": "contract.json"})
    assert captured["contract"] == (tmp_path / "contract.json").resolve()
    mcp_server.dispatch(
        "dashboard_check",
        {"contract_path": str(tmp_path / "contract.json"), "out_dir": "out"},
    )
    assert captured["contract"] == (tmp_path / "contract.json").resolve()
    assert captured["out_dir"] == (tmp_path / "out").resolve()
    assert captured["full"] is False

    with raises(ValueError, match="outside the workspace"):
        mcp_server.dispatch("dashboard_validate", {"contract_path": "../outside.json"})
    with raises(ValueError, match="outside the workspace"):
        mcp_server.dispatch(
            "dashboard_validate",
            {"contract_path": str(tmp_path.parent / "outside.json")},
        )
    link = tmp_path / "linked"
    link.symlink_to(tmp_path.parent, target_is_directory=True)
    with raises(ValueError, match="symlink"):
        mcp_server.dispatch("dashboard_validate", {"contract_path": "linked/outside.json"})
    with raises(ValueError, match="outside the workspace"):
        mcp_server.dispatch(
            "dashboard_check",
            {"contract_path": "contract.json", "out_dir": str(tmp_path.parent / "out")},
        )
    with raises(ValueError, match="symlink"):
        mcp_server.dispatch(
            "dashboard_check",
            {"contract_path": "contract.json", "out_dir": "linked/out"},
        )
