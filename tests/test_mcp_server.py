from __future__ import annotations

import asyncio
import base64
import hashlib
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


def test_record_tools_use_input_schemas_and_return_text_only(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def record(kind: str, arguments: dict[str, object]) -> service.Json:
        captured.update({"kind": kind, "arguments": arguments})
        return {"verdict": "pass", "stage": "record", "record": {"event_id": "a" * 64}}

    monkeypatch.setattr(service, "record_payload", record)
    for name, kind in (
        ("dashboard_record_decision", "decision"),
        ("dashboard_record_impression", "impression"),
        ("dashboard_record_vision_review", "vision-review"),
    ):
        result = asyncio.run(_call_tool(name, {"stage": "generate"}))

        assert result.isError is False
        assert len(result.content) == 1
        assert isinstance(result.content[0], types.TextContent)
        assert _result_payload(result)["stage"] == "record"
        assert captured["kind"] == kind
    specs = {tool.name: tool for tool in mcp_server.tool_specs()}
    for name in (
        "dashboard_record_decision",
        "dashboard_record_impression",
        "dashboard_record_vision_review",
    ):
        assert "properties" in specs[name].inputSchema
        assert specs[name].annotations is not None
        assert specs[name].annotations.readOnlyHint is False

    monkeypatch.setattr(
        service,
        "record_payload",
        lambda _kind, _arguments: {"verdict": "fail", "stage": "record", "detail": "invalid"},
    )
    invalid = asyncio.run(_call_tool("dashboard_record_decision", {}))
    assert invalid.isError is False
    assert _result_payload(invalid)["detail"] == "invalid"


def test_records_status_is_read_only_text_only(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(
        service,
        "records_status_payload",
        lambda: {"verdict": "pass", "counts": {}},
    )

    result = asyncio.run(_call_tool("dashboard_records_status", {}))
    tool = next(tool for tool in mcp_server.tool_specs() if tool.name == "dashboard_records_status")

    assert result.isError is False
    assert len(result.content) == 1
    assert isinstance(result.content[0], types.TextContent)
    assert tool.annotations is not None
    assert tool.annotations.readOnlyHint is True


def test_screenshot_tool_is_write_capable_and_inlines_image(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    image = tmp_path / "desktop.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nsmall image")
    vision_review = [{"image_path": str(image), "sha256": "a" * 64}]

    def screenshot(_contract: Path, _out: Path | None) -> service.Json:
        return {
            "verdict": "pass",
            "images": [str(image)],
            "vision_review": vision_review,
        }

    monkeypatch.setattr(
        service,
        "screenshot_payload",
        screenshot,
    )
    tool = next(tool for tool in mcp_server.tool_specs() if tool.name == "dashboard_screenshot")

    assert tool.annotations is not None
    assert tool.annotations.readOnlyHint is False
    result = asyncio.run(_call_tool("dashboard_screenshot", {"contract_path": "contract.json"}))
    payload = _result_payload(result)

    assert result.isError is False
    assert payload["vision_review"] == vision_review
    assert payload["inline_images"] == [
        {
            "path": str(image),
            "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
            "attached": True,
            "reason": None,
        }
    ]
    assert len(result.content) == 2
    block = result.content[1]
    assert isinstance(block, types.ImageContent)
    assert block.mimeType == "image/png"
    assert base64.b64decode(block.data) == image.read_bytes()


def test_inline_image_count_and_size_caps_are_reported(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.png"
    oversized.write_bytes(b"x" * (4 * 1024 * 1024 + 1))
    paths = [oversized]
    for index in range(9):
        image = tmp_path / f"small-{index}.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\nsmall")
        paths.append(image)

    blocks = mcp_server.render_content({"verdict": "pass", "images": [str(path) for path in paths]})
    payload = cast(dict[str, object], json.loads(cast(types.TextContent, blocks[0]).text))
    entries = cast(list[dict[str, object]], payload["inline_images"])
    attached = [block for block in blocks if isinstance(block, types.ImageContent)]

    assert len(attached) == 8
    assert entries[0]["reason"] == "over_4_mib"
    assert entries[-1]["reason"] == "image_limit_reached"
    assert sum(entry["attached"] is True for entry in entries) == 8


def test_gates_and_smoke_tools_inline_generated_images(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    image = tmp_path / "dashboard.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nimage")
    vision_review = [{"image_path": str(image), "sha256": "a" * 64}]
    payload: service.Json = {
        "verdict": "pass",
        "images": [str(image)],
        "vision_review": vision_review,
    }

    def gates(
        _contract: Path,
        _out: Path | None,
        *,
        full: bool,
    ) -> service.Json:
        return payload if full else {"verdict": "pass"}

    def smoke(_contract: Path, _out: Path | None) -> service.Json:
        return payload

    monkeypatch.setattr(service, "gates_payload", gates)
    monkeypatch.setattr(service, "smoke_payload", smoke)

    for tool_name in ("dashboard_gates", "dashboard_smoke"):
        result = asyncio.run(_call_tool(tool_name, {"contract_path": "contract.json"}))

        assert len(result.content) == 2
        assert isinstance(result.content[1], types.ImageContent)
        inline_images = cast(
            list[dict[str, object]],
            _result_payload(result)["inline_images"],
        )
        assert inline_images[0]["attached"] is True
        assert _result_payload(result)["vision_review"] == vision_review


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
