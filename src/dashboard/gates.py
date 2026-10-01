"""Fail-closed contract and generated-application gates."""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, ValidationError

from .contract import (
    REVERSE_DNS,
    WIRE_TYPES,
    BleTransportBase,
    DashboardContract,
    WebRtcTransport,
    WebSocketTransport,
    load_contract,
    resolve,
)
from .interchange import sha256_file
from .matrix import CAVEATS, route_caveats, route_support
from .screenshots import capture
from .wasm import build_codec_parity, build_module
from .webmcp import definitions, has_hazard, json_schema_valid

PASS = "pass"
FAIL = "fail"


class Check(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    status: Literal["pass", "fail", "not_applicable"]
    detail: str = ""
    evidence: list[str] = []


class GateReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    system: Literal["dashboard"] = "dashboard"
    artifact_kind: Literal["dashboard_gate_report"] = "dashboard_gate_report"
    design: str
    scope: Literal["static", "full"]
    contract_sha256: str | None
    verdict: Literal["pass", "fail"]
    checks: list[Check]


def _check(check_id: str, problems: list[str], evidence: list[str] | None = None) -> Check:
    return Check(
        id=check_id,
        status=FAIL if problems else PASS,
        detail="; ".join(problems),
        evidence=evidence or [],
    )


def _duplicates(values: list[str]) -> list[str]:
    return sorted({value for value in values if values.count(value) > 1})


def check_contract(contract: DashboardContract, contract_path: Path) -> list[Check]:
    messages = contract.protocol.messages
    transports = contract.transports
    message_by_name = {item.name: item for item in messages}
    transport_by_id = {item.id: item for item in transports}
    checks: list[Check] = []

    checks.append(
        _check(
            "protocol.ids-unique",
            [f"duplicate message ids: {', '.join(_duplicates([str(m.id) for m in messages]))}"]
            if _duplicates([str(m.id) for m in messages])
            else [],
        )
    )
    checks.append(
        _check(
            "protocol.names-unique",
            [f"duplicate message names: {', '.join(_duplicates([m.name for m in messages]))}"]
            if _duplicates([m.name for m in messages])
            else [],
        )
    )
    frame_problems: list[str] = []
    range_problems: list[str] = []
    for message in messages:
        field_names = [field.name for field in message.fields]
        duplicate_fields = _duplicates(field_names)
        if duplicate_fields:
            range_problems.append(f"{message.name}: duplicate fields {', '.join(duplicate_fields)}")
        payload_bytes = sum(WIRE_TYPES[field.type][0] for field in message.fields)
        raw_bytes = 2 + payload_bytes + 2
        encoded_bytes = raw_bytes + math.ceil(raw_bytes / 254) + 1 + 1
        if encoded_bytes > contract.protocol.max_frame_bytes:
            frame_problems.append(
                f"{message.name}: maximum encoded frame {encoded_bytes} exceeds "
                f"{contract.protocol.max_frame_bytes}"
            )
        for field in message.fields:
            lower_type, upper_type = WIRE_TYPES[field.type][1:]
            if field.min is not None and field.max is not None and field.min >= field.max:
                range_problems.append(f"{message.name}.{field.name}: min must be less than max")
            if field.min is not None and (
                not math.isfinite(field.min) or field.min / field.scale < lower_type
            ):
                range_problems.append(
                    f"{message.name}.{field.name}: min is outside {field.type} range"
                )
            if field.max is not None and (
                not math.isfinite(field.max) or field.max / field.scale > upper_type
            ):
                range_problems.append(
                    f"{message.name}.{field.name}: max is outside {field.type} range"
                )
            if not math.isfinite(field.scale):
                range_problems.append(f"{message.name}.{field.name}: scale must be finite")
    checks.append(_check("protocol.frame-size", frame_problems))
    checks.append(_check("protocol.field-range", range_problems))
    checks.append(
        _check(
            "protocol.ack-direction",
            [
                f"{message.name}: ack is only valid for host_to_device"
                for message in messages
                if message.ack and message.direction != "host_to_device"
            ],
        )
    )
    checks.append(
        _check(
            "transport.ids-unique",
            [f"duplicate transport ids: {', '.join(_duplicates([t.id for t in transports]))}"]
            if _duplicates([t.id for t in transports])
            else [],
        )
    )
    url_problems: list[str] = []
    ble_problems: list[str] = []
    usb_problems: list[str] = []
    for transport in transports:
        if isinstance(transport, WebSocketTransport):
            url = transport.url
            scheme = urlsplit(url).scheme
            host = (urlsplit(url).hostname or "").lower()
            if scheme != "wss" and not (
                scheme == "ws" and host in {"localhost", "127.0.0.1", "::1"}
            ):
                url_problems.append(f"{transport.id}: use wss:// or a loopback ws:// URL")
        elif isinstance(transport, WebRtcTransport):
            parsed = urlsplit(transport.signaling_url)
            if parsed.scheme != "wss":
                url_problems.append(f"{transport.id}: signaling_url must use wss://")
            for ice_server in transport.ice_servers:
                for ice_url in ice_server.urls:
                    if urlsplit(ice_url).scheme not in {"stun", "turn", "turns"}:
                        url_problems.append(f"{transport.id}: invalid ICE URL {ice_url}")
        elif isinstance(transport, BleTransportBase):
            for value in (
                transport.service_uuid,
                transport.rx_characteristic,
                transport.tx_characteristic,
            ):
                if not value.islower() or (len(value) == 36 and value != value.lower()):
                    ble_problems.append(f"{transport.id}: BLE UUID must be lowercase")
        elif transport.kind == "webusb" and transport.interface_class != 0xFF:
            usb_problems.append(f"{transport.id}: interface_class must be vendor-specific (0xFF)")
    checks.append(_check("transport.secure-url", url_problems))
    checks.append(_check("transport.webusb-vendor-class", usb_problems))
    checks.append(_check("transport.ble-uuids", ble_problems))

    refs = [route.transport for platform in contract.platforms for route in platform.routes]
    checks.append(
        _check(
            "transport.used",
            [
                "unreferenced transports: "
                f"{', '.join(sorted(set(t.id for t in transports) - set(refs)))}"
            ]
            if set(t.id for t in transports) - set(refs)
            else [],
        )
    )
    supported = [p for p in contract.platforms if p.status == "supported"]
    checks.append(
        _check(
            "platform.declared", [] if supported else ["at least one platform must be supported"]
        )
    )
    route_problems: list[str] = []
    caveat_problems: list[str] = []
    unsupported_problems: list[str] = []
    for platform in contract.platforms:
        if platform.status == "unsupported" and not platform.reason:
            unsupported_problems.append(f"{platform.os}: unsupported platform needs a reason")
        if platform.status != "supported":
            continue
        for route in platform.routes:
            transport = transport_by_id.get(route.transport)
            if transport is None:
                route_problems.append(
                    f"{platform.os}/{route.browser}: unknown transport {route.transport}"
                )
                continue
            support = route_support(platform.os, route.browser, transport.kind)
            if support is None:
                route_problems.append(
                    f"{platform.os}/{route.browser}/{transport.kind}: "
                    "unsupported or invalid browser pair"
                )
                continue
            url: str | None = None
            if isinstance(transport, WebSocketTransport):
                url = transport.url
            elif isinstance(transport, WebRtcTransport):
                url = transport.signaling_url
            expected = route_caveats(platform.os, route.browser, transport.kind, url)
            unknown_ack = sorted(set(route.acknowledged_caveats) - set(CAVEATS))
            missing_ack = sorted(set(expected) - set(route.acknowledged_caveats))
            if unknown_ack:
                caveat_problems.append(
                    f"{platform.os}/{route.browser}/{route.transport}: unknown caveats "
                    f"{', '.join(unknown_ack)}"
                )
            if missing_ack:
                caveat_problems.append(
                    f"{platform.os}/{route.browser}/{route.transport}: acknowledge "
                    f"{', '.join(missing_ack)}"
                )
    checks.append(_check("platform.route-known", route_problems))
    checks.append(_check("platform.caveats-acknowledged", caveat_problems))
    checks.append(_check("platform.unsupported-reason", unsupported_problems))

    tauri_shell = contract.shell.tauri if contract.shell is not None else None
    has_tauri_transport = any(
        transport.kind in {"tauri_ble", "tauri_serial"} for transport in transports
    )
    if tauri_shell is None and not has_tauri_transport:
        checks.extend(
            Check(
                id=check_id,
                status="not_applicable",
                detail="contract declares no Tauri shell or transports",
            )
            for check_id in (
                "tauri.identifier",
                "tauri.targets-routes",
                "tauri.transport-requires-shell",
            )
        )
    else:
        if tauri_shell is None:
            checks.append(
                Check(
                    id="tauri.identifier",
                    status="not_applicable",
                    detail="contract declares no Tauri shell",
                )
            )
            checks.append(
                Check(
                    id="tauri.targets-routes",
                    status="not_applicable",
                    detail="contract declares no Tauri shell",
                )
            )
        else:
            identifier_problems = (
                []
                if re.fullmatch(REVERSE_DNS, tauri_shell.identifier)
                else [f"invalid reverse-DNS identifier: {tauri_shell.identifier}"]
            )
            checks.append(_check("tauri.identifier", identifier_problems))

            targets = set(tauri_shell.targets)
            target_route_problems: list[str] = []
            for target in tauri_shell.targets:
                if target == "ios":
                    declarations = [
                        platform
                        for platform in contract.platforms
                        if platform.os in {"ios", "ipados"} and platform.status == "supported"
                    ]
                    if not declarations:
                        target_route_problems.append(
                            "ios: shell target requires a supported iOS or iPadOS declaration"
                        )
                    for platform in declarations:
                        if not any(route.browser == "tauri" for route in platform.routes):
                            target_route_problems.append(
                                f"{platform.os}: supported declaration needs a tauri route"
                            )
                else:
                    platform = next(
                        (
                            item
                            for item in contract.platforms
                            if item.os == target and item.status == "supported"
                        ),
                        None,
                    )
                    if platform is None or not any(
                        route.browser == "tauri" for route in platform.routes
                    ):
                        target_route_problems.append(
                            f"{target}: shell target needs a supported tauri route"
                        )
            for platform in contract.platforms:
                if platform.status != "supported":
                    continue
                if any(route.browser == "tauri" for route in platform.routes):
                    target = "ios" if platform.os == "ipados" else platform.os
                    if target not in targets:
                        target_route_problems.append(
                            f"{platform.os}: tauri route requires shell target {target}"
                        )
            checks.append(_check("tauri.targets-routes", target_route_problems))

        shell_problems = (
            ["tauri_ble or tauri_serial transports require shell.tauri"]
            if has_tauri_transport and tauri_shell is None
            else []
        )
        checks.append(_check("tauri.transport-requires-shell", shell_problems))

    widget_problems: list[str] = []
    refs_seen: list[str] = []
    for widget in contract.widgets:
        is_display = widget.kind in {"value", "gauge", "chart", "indicator"}
        if is_display:
            if widget.source is None or "." not in widget.source:
                widget_problems.append(f"{widget.id}: display widgets require message.field source")
            else:
                message_name, field_name = widget.source.split(".", 1)
                message = message_by_name.get(message_name)
                if message is None or message.direction != "device_to_host":
                    widget_problems.append(
                        f"{widget.id}: source must read a device_to_host message"
                    )
                elif field_name not in {field.name for field in message.fields}:
                    widget_problems.append(f"{widget.id}: unknown source field {widget.source}")
                refs_seen.append(widget.source)
        else:
            if widget.command is None:
                widget_problems.append(f"{widget.id}: control widgets require a command")
            else:
                message = message_by_name.get(widget.command)
                if message is None or message.direction != "host_to_device":
                    widget_problems.append(
                        f"{widget.id}: command must target a host_to_device message"
                    )
                elif widget.field is not None and widget.field not in {
                    f.name for f in message.fields
                }:
                    widget_problems.append(f"{widget.id}: unknown command field {widget.field}")
                refs_seen.append(widget.command)
        if widget.hazard and not widget.confirm:
            widget_problems.append(f"{widget.id}: hazard controls require confirm=true")
    widget_ids = [widget.id for widget in contract.widgets]
    duplicates = _duplicates(widget_ids)
    if duplicates:
        widget_problems.append(f"duplicate widget ids: {', '.join(duplicates)}")
    checks.append(_check("widget.refs", widget_problems))
    checks.append(
        _check(
            "widget.hazard-confirm",
            [
                f"{w.id}: hazard requires confirm=true"
                for w in contract.widgets
                if w.hazard and not w.confirm
            ],
        )
    )
    checks.append(
        _check(
            "widget.ids-unique",
            [f"duplicate widget ids: {', '.join(duplicates)}"] if duplicates else [],
        )
    )

    import_problems: list[str] = []
    for item in contract.imports:
        path = resolve(contract_path, item.path)
        if not path.is_file():
            import_problems.append(f"{item.path}: file not found")
        elif sha256_file(path) != item.sha256:
            import_problems.append(f"{item.path}: sha256 mismatch")
    checks.append(_check("imports.sha256", import_problems))

    firmware_problems: list[str] = []
    firmware_path = contract.device.firmware_contract
    if firmware_path is not None:
        path = resolve(contract_path, firmware_path)
        if not path.is_file():
            firmware_problems.append(f"{firmware_path}: file not found")
        elif sha256_file(path) != contract.device.firmware_sha256:
            firmware_problems.append(f"{firmware_path}: sha256 mismatch")
        else:
            try:
                artifact = json.loads(path.read_text(encoding="utf-8"))
                if (
                    artifact.get("system") != "firmware"
                    or artifact.get("artifact_kind") != "firmware_contract"
                ):
                    firmware_problems.append(f"{firmware_path}: not a firmware_contract artifact")
            except (OSError, json.JSONDecodeError) as exc:
                firmware_problems.append(f"{firmware_path}: invalid JSON: {exc}")
    checks.append(_check("firmware.link", firmware_problems))

    webmcp_tools = definitions(contract)
    if contract.webmcp is None:
        checks.extend(
            Check(id=check_id, status="not_applicable", detail="WebMCP is not configured")
            for check_id in ("webmcp.tool-names", "webmcp.hazard-consequential", "webmcp.schema")
        )
    else:
        webmcp_name_problems: list[str] = []
        names = [str(tool.get("name", "")) for tool in webmcp_tools]
        duplicates = _duplicates(names)
        if duplicates:
            webmcp_name_problems.append(f"duplicate tool names: {', '.join(duplicates)}")
        for name in names:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
                webmcp_name_problems.append(f"invalid WebMCP tool name: {name}")
        checks.append(_check("webmcp.tool-names", webmcp_name_problems))

        hazard_problems: list[str] = []
        annotations_by_name: dict[str, object] = {
            str(tool.get("name", "")): tool.get("annotations", {}) for tool in webmcp_tools
        }
        for message in messages:
            if message.direction != "host_to_device":
                continue
            annotation = annotations_by_name.get(f"send_{message.name}", {})
            widget_confirmation = all(
                widget.confirm
                for widget in contract.widgets
                if widget.command == message.name and widget.hazard
            )
            if has_hazard(contract, message.name) and (
                not isinstance(annotation, dict)
                or cast(dict[str, object], annotation).get("consequentialHint") is not True
                or not widget_confirmation
            ):
                hazard_problems.append(
                    f"send_{message.name}: hazardous controls require consequentialHint "
                    "and confirmation"
                )
        checks.append(_check("webmcp.hazard-consequential", hazard_problems))

        schema_problems: list[str] = []
        for tool in webmcp_tools:
            schema = tool.get("inputSchema")
            if not json_schema_valid(schema):
                schema_problems.append(f"{tool.get('name')}: invalid input schema")
        checks.append(_check("webmcp.schema", schema_problems))
    return checks


def _run(command: list[str], cwd: Path, timeout: int = 900) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output or f"exit code {result.returncode}"


def generated_freshness(contract_path: Path, generated_dir: Path) -> list[str]:
    generated = generated_dir / "dash-manifest.json"
    freshness: list[str] = []
    try:
        manifest_value: object = json.loads(generated.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"cannot load generation manifest: {exc}"]
    if not isinstance(manifest_value, dict):
        return ["generation manifest is not a JSON object"]
    manifest = cast(dict[str, object], manifest_value)
    if manifest.get("contract_sha256") != sha256_file(contract_path):
        freshness.append("manifest contract_sha256 does not match the contract")
    files = manifest.get("files")
    if not isinstance(files, dict):
        return [*freshness, "generation manifest files must be an object"]
    for name, expected in cast(dict[object, object], files).items():
        if not isinstance(name, str) or not isinstance(expected, str):
            freshness.append("generation manifest contains an invalid file entry")
            continue
        artifact = generated_dir / name
        try:
            artifact.resolve().relative_to(generated_dir.resolve())
        except (OSError, RuntimeError, ValueError):
            freshness.append(f"generated file path escapes output: {name}")
            continue
        if not artifact.is_file() or sha256_file(artifact) != expected:
            freshness.append(f"generated file missing or stale: {name}")
    return freshness


def _run_full(contract_path: Path, out_dir: Path, contract: DashboardContract) -> list[Check]:
    root = Path(__file__).resolve().parents[2]
    generated_dir = out_dir.resolve() / contract.name
    checks = [_check("generated.fresh", generated_freshness(contract_path, generated_dir))]

    for check_id, command in (
        ("runtime.typecheck", ["runtime/node_modules/.bin/tsc", "-p", "runtime"]),
        ("runtime.test", ["node", "--test", "runtime/test/"]),
    ):
        tool = shutil.which(command[0])
        if tool is None and not (root / command[0]).exists():
            checks.append(_check(check_id, [f"required tool not found: {command[0]}"]))
            continue
        command[0] = tool or str(root / command[0])
        ok, output = _run(command, root)
        checks.append(_check(check_id, [] if ok else [output], [output] if output else []))

    parity = build_codec_parity(root, out_dir / "wasm-parity")
    checks.append(_check("wasm.parity", [] if parity.ok else [parity.detail], [parity.detail]))
    module_problems: list[str] = []
    modules = contract.wasm.modules if contract.wasm is not None else []
    for module in modules:
        result = build_module(
            root,
            out_dir / f"wasm-{module.id}",
            [resolve(contract_path, source) for source in module.sources],
            module.exports,
        )
        if not result.ok:
            module_problems.append(f"{module.id}: {result.detail}")
    checks.append(
        Check(
            id="wasm.modules",
            status=PASS if not module_problems else FAIL,
            detail="; ".join(module_problems)
            or (
                "no wasm modules declared" if not contract.wasm or not contract.wasm.modules else ""
            ),
            evidence=[],
        )
        if modules
        else Check(
            id="wasm.modules", status="not_applicable", detail="contract declares no WASM modules"
        )
    )

    playwright = root / "runtime/node_modules/.bin/playwright"
    if not playwright.is_file():
        checks.append(
            _check("e2e.chromium", ["Playwright is not installed in runtime/node_modules"])
        )
    else:
        ok, output = _run(
            [str(playwright), "test", "-c", "runtime/playwright.config.ts"], root, timeout=1200
        )
        checks.append(_check("e2e.chromium", [] if ok else [output], [output] if output else []))

    try:
        result = capture(generated_dir, out_dir)
        checks.append(
            _check(
                "visual.capture",
                [] if result.ok else [result.detail],
                [str(image.path) for image in result.images],
            )
        )
    except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
        checks.append(_check("visual.capture", [str(exc)]))

    if any(transport.kind == "websocket" for transport in contract.transports):
        try:
            from .servo import smoke

            result = smoke(generated_dir)
            detail = result.detail
            if not detail.startswith("attempts="):
                detail = f"attempts={result.attempts}; {detail}"
            checks.append(
                Check(
                    id="smoke.servo",
                    status=PASS if result.ok else FAIL,
                    detail=detail,
                    evidence=[str(result.screenshot)] if result.screenshot else [detail],
                )
            )
        except (OSError, RuntimeError, TimeoutError) as exc:
            checks.append(_check("smoke.servo", [str(exc)]))
    else:
        checks.append(
            Check(
                id="smoke.servo",
                status="not_applicable",
                detail="Servo WebSocket route smoke requires a declared WebSocket transport",
            )
        )
    return checks


def run_gates(contract_path: Path, out_dir: Path, *, full: bool = False) -> GateReport:
    path = contract_path.resolve()
    try:
        contract = load_contract(path)
    except (OSError, ValueError, ValidationError) as exc:
        return GateReport(
            design=path.name.removesuffix(".dash.json"),
            scope="full" if full else "static",
            contract_sha256=sha256_file(path) if path.is_file() else None,
            verdict=FAIL,
            checks=[Check(id="contract.schema", status=FAIL, detail=str(exc))],
        )
    checks = [Check(id="contract.schema", status=PASS, detail="contract loaded")]
    checks.extend(check_contract(contract, path))
    if full:
        checks.extend(_run_full(path, out_dir, contract))
    return GateReport(
        design=contract.name,
        scope="full" if full else "static",
        contract_sha256=sha256_file(path),
        verdict=FAIL if any(check.status == FAIL for check in checks) else PASS,
        checks=checks,
    )


def report_markdown(report: GateReport) -> str:
    lines = [
        f"# Dashboard gate report: {report.design}",
        "",
        f"- verdict: **{report.verdict}** ({report.scope})",
        f"- contract sha256: `{report.contract_sha256}`",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for check in report.checks:
        detail = (check.detail or "; ".join(check.evidence[:3])).replace("|", "\\|")
        lines.append(f"| {check.id} | {check.status} | {detail} |")
    return "\n".join(lines) + "\n"


def write_outputs(report: GateReport, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{report.design}.dash-report.json"
    markdown_path = out_dir / f"{report.design}.dash-report.md"
    json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(report_markdown(report), encoding="utf-8")
    return [json_path, markdown_path]
