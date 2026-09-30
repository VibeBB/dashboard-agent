"""Expose dashboard services over stdio MCP."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

from mcp import types
from mcp.server import Server
from mcp.server.lowlevel import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

from . import __version__, service
from .workspace import workspace_path

server: Server = Server(f"dashboard-mcp/{__version__}")

_CONTRACT = {"contract_path": {"type": "string"}}
_OUT = {"out_dir": {"type": "string"}}
_STRINGS = {"type": "array", "items": {"type": "string"}}
_IMAGE_TOOLS = {"dashboard_screenshot", "dashboard_gates", "dashboard_smoke"}
_IMAGE_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
_MAX_INLINE_IMAGES = 8
_MAX_INLINE_IMAGE_BYTES = 4 * 1024 * 1024


def _schema(properties: Mapping[str, object], required: list[str]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": dict(properties),
        "required": required,
        "additionalProperties": False,
    }


TOOLS: dict[str, tuple[str, dict[str, object], bool]] = {
    "dashboard_doctor": ("Probe required dashboard tools", _schema({}, []), True),
    "dashboard_matrix": ("Show declared browser and transport support", _schema({}, []), True),
    "dashboard_validate": (
        "Validate a dashboard JSON contract",
        _schema(_CONTRACT, ["contract_path"]),
        True,
    ),
    "dashboard_generate": (
        "Generate a dashboard application and optional Tauri scaffold from a contract",
        _schema({**_CONTRACT, **_OUT}, ["contract_path"]),
        False,
    ),
    "dashboard_check": (
        "Run static dashboard contract gates",
        _schema({**_CONTRACT, **_OUT}, ["contract_path"]),
        False,
    ),
    "dashboard_gates": (
        "Run full gates, browser tests, WASM parity, and Servo smoke",
        _schema({**_CONTRACT, **_OUT}, ["contract_path"]),
        False,
    ),
    "dashboard_smoke": (
        "Run the Servo WebDriver smoke check for a generated dashboard",
        _schema({**_CONTRACT, **_OUT}, ["contract_path"]),
        False,
    ),
    "dashboard_screenshot": (
        "Capture desktop and mobile screenshots of a fresh generated dashboard",
        _schema({**_CONTRACT, **_OUT}, ["contract_path"]),
        False,
    ),
    "dashboard_protocol_export": (
        "Export the dashboard protocol interchange artifact",
        _schema({**_CONTRACT, **_OUT}, ["contract_path"]),
        False,
    ),
    "dashboard_request": (
        "Write a change request for a sibling agent",
        _schema(
            {
                **_CONTRACT,
                **_OUT,
                "target": {"type": "string"},
                "risk": {"type": "string", "enum": ["low", "high"]},
                "change": {"type": "string"},
                "rationale": {"type": "string"},
                "failing_checks": _STRINGS,
            },
            ["contract_path", "target", "risk", "change", "rationale"],
        ),
        False,
    ),
}


def tool_specs() -> list[types.Tool]:
    return [
        types.Tool(
            name=name,
            description=description,
            inputSchema=schema,
            annotations=types.ToolAnnotations(readOnlyHint=read_only),
        )
        for name, (description, schema, read_only) in TOOLS.items()
    ]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return tool_specs()


def _string(arguments: dict[str, object], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _path(arguments: dict[str, object], key: str) -> Path | None:
    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty path")
    return workspace_path(value)


def _strings(arguments: dict[str, object], key: str) -> list[str]:
    value = arguments.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list of strings")
    items = cast(list[object], value)
    if any(not isinstance(item, str) for item in items):
        raise ValueError(f"{key} must be a list of strings")
    return cast(list[str], items)


def dispatch(name: str, arguments: dict[str, object]) -> service.Json:
    handlers: dict[str, Callable[[], service.Json]] = {
        "dashboard_doctor": service.doctor_payload,
        "dashboard_matrix": service.matrix_payload,
        "dashboard_validate": lambda: service.validate_payload(
            workspace_path(_string(arguments, "contract_path"))
        ),
        "dashboard_generate": lambda: service.generate_payload(
            workspace_path(_string(arguments, "contract_path")),
            _path(arguments, "out_dir"),
        ),
        "dashboard_check": lambda: service.gates_payload(
            workspace_path(_string(arguments, "contract_path")),
            _path(arguments, "out_dir"),
            full=False,
        ),
        "dashboard_gates": lambda: service.gates_payload(
            workspace_path(_string(arguments, "contract_path")),
            _path(arguments, "out_dir"),
            full=True,
        ),
        "dashboard_smoke": lambda: service.smoke_payload(
            workspace_path(_string(arguments, "contract_path")),
            _path(arguments, "out_dir"),
        ),
        "dashboard_screenshot": lambda: service.screenshot_payload(
            workspace_path(_string(arguments, "contract_path")),
            _path(arguments, "out_dir"),
        ),
        "dashboard_protocol_export": lambda: service.protocol_export_payload(
            workspace_path(_string(arguments, "contract_path")),
            _path(arguments, "out_dir"),
        ),
        "dashboard_request": lambda: service.request_payload(
            workspace_path(_string(arguments, "contract_path")),
            _path(arguments, "out_dir"),
            target=_string(arguments, "target"),
            risk=_string(arguments, "risk"),
            change=_string(arguments, "change"),
            rationale=_string(arguments, "rationale"),
            failing_checks=_strings(arguments, "failing_checks"),
        ),
    }
    handler = handlers.get(name)
    if handler is None:
        return {"verdict": "fail", "detail": f"unknown tool {name}"}
    return handler()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def render_content(payload: service.Json) -> list[types.ContentBlock]:
    rendered = dict(payload)
    values = rendered.pop("images", [])
    paths = cast(list[object], values) if isinstance(values, list) else []
    inline_images: list[dict[str, object]] = []
    images: list[types.ImageContent] = []
    for value in paths:
        if not isinstance(value, str):
            continue
        path = Path(value)
        mime = _IMAGE_MIME.get(path.suffix.lower())
        if mime is None:
            continue
        entry: dict[str, object] = {
            "path": str(path),
            "sha256": None,
            "attached": False,
            "reason": None,
        }
        try:
            size = path.stat().st_size
            if size > _MAX_INLINE_IMAGE_BYTES:
                entry["sha256"] = _file_sha256(path)
                entry["reason"] = "over_4_mib"
            elif len(images) >= _MAX_INLINE_IMAGES:
                entry["sha256"] = _file_sha256(path)
                entry["reason"] = "image_limit_reached"
            else:
                data = path.read_bytes()
                if len(data) > _MAX_INLINE_IMAGE_BYTES:
                    entry["sha256"] = hashlib.sha256(data).hexdigest()
                    entry["reason"] = "over_4_mib"
                else:
                    entry["sha256"] = hashlib.sha256(data).hexdigest()
                    entry["attached"] = True
                    images.append(
                        types.ImageContent(
                            type="image",
                            data=base64.b64encode(data).decode("ascii"),
                            mimeType=mime,
                        )
                    )
        except OSError:
            entry["reason"] = "unavailable"
        inline_images.append(entry)
    rendered["inline_images"] = inline_images
    return [
        types.TextContent(
            type="text",
            text=json.dumps(rendered, ensure_ascii=False, indent=2),
        ),
        *images,
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, object]) -> types.CallToolResult:
    is_error = name not in TOOLS
    try:
        payload: service.Json = await asyncio.to_thread(dispatch, name, arguments or {})
    except Exception as exc:
        payload = {
            "verdict": "fail",
            "detail": f"{name} error: {exc}",
            "error_type": type(exc).__name__,
        }
        is_error = True
    content = (
        render_content(payload)
        if name in _IMAGE_TOOLS
        else [
            cast(
                types.ContentBlock,
                types.TextContent(
                    type="text",
                    text=json.dumps(payload, ensure_ascii=False, indent=2),
                ),
            )
        ]
    )
    return types.CallToolResult(content=content, isError=is_error)


async def _run() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="dashboard-agent",
                server_version=__version__,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
