from __future__ import annotations

import json
from pathlib import Path

from pytest import MonkeyPatch

from dashboard import gates as gates_module
from dashboard import screenshots, servo
from dashboard.contract import PlatformDecl, Route, load_contract
from dashboard.gates import Check, check_contract, run_gates
from dashboard.interchange import sha256_file
from dashboard.servo import SmokeResult
from dashboard.wasm import WasmResult

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


def test_full_gates_capture_visuals_after_browser_e2e(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    contract_path = ROOT / "examples/smart-kettle/smart-kettle.dash.json"
    contract = load_contract(contract_path)
    out_dir = tmp_path / "out"
    generated = out_dir / contract.name
    generated.mkdir(parents=True)
    (generated / "dash-manifest.json").write_text(
        json.dumps({"contract_sha256": sha256_file(contract_path), "files": {}}),
        encoding="utf-8",
    )
    root = ROOT.resolve()
    playwright = root / "runtime/node_modules/.bin/playwright"
    original_is_file = Path.is_file

    def is_file(path: Path) -> bool:
        return True if path == playwright else original_is_file(path)

    monkeypatch.setattr(Path, "is_file", is_file)

    def which(_tool: str) -> str:
        return "/usr/bin/tool"

    monkeypatch.setattr(gates_module.shutil, "which", which)
    events: list[str] = []

    def run(command: list[str], _cwd: Path, timeout: int = 900) -> tuple[bool, str]:
        del timeout
        events.append("e2e" if "playwright" in command[0] else "runtime")
        return True, "passed"

    monkeypatch.setattr(gates_module, "_run", run)

    def codec_parity(_root: Path, _output: Path) -> WasmResult:
        return WasmResult(ok=True, detail="parity passed")

    def build_module(
        _root: Path,
        _output: Path,
        _sources: list[Path],
        _exports: list[str],
    ) -> WasmResult:
        return WasmResult(ok=True, detail="module passed")

    monkeypatch.setattr(gates_module, "build_codec_parity", codec_parity)
    monkeypatch.setattr(gates_module, "build_module", build_module)
    desktop = out_dir / f"{contract.name}.screens" / "desktop.png"

    def capture(_generated: Path, _output: Path) -> screenshots.CaptureResult:
        events.append("visual")
        return screenshots.CaptureResult(
            ok=True,
            detail="captured",
            images=[
                screenshots.ScreenImage(
                    name="desktop",
                    path=desktop,
                    width=1280,
                    height=800,
                    sha256="a" * 64,
                    bytes=100,
                )
            ],
        )

    monkeypatch.setattr(screenshots, "capture", capture)

    def smoke(_generated: Path) -> SmokeResult:
        return SmokeResult(ok=True, detail="servo passed")

    monkeypatch.setattr(servo, "smoke", smoke)

    report = run_gates(contract_path, out_dir, full=True)
    visual = _check_by_id(report.checks, "visual.capture")

    assert visual.status == "pass"
    assert visual.evidence == [str(desktop)]
    assert events.index("e2e") < events.index("visual")


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


def test_tauri_gates_pass_and_are_not_applicable_without_tauri_usage() -> None:
    kettle_path = ROOT / "examples/smart-kettle/smart-kettle.dash.json"
    kettle_checks = check_contract(load_contract(kettle_path), kettle_path)
    assert {
        check_id: _check_by_id(kettle_checks, check_id).status
        for check_id in (
            "tauri.identifier",
            "tauri.targets-routes",
            "tauri.transport-requires-shell",
        )
    } == {
        "tauri.identifier": "pass",
        "tauri.targets-routes": "pass",
        "tauri.transport-requires-shell": "pass",
    }

    bench_path = ROOT / "examples/bench-meter/bench-meter.dash.json"
    bench_checks = check_contract(load_contract(bench_path), bench_path)
    assert {
        check_id: _check_by_id(bench_checks, check_id).status
        for check_id in (
            "tauri.identifier",
            "tauri.targets-routes",
            "tauri.transport-requires-shell",
        )
    } == {
        "tauri.identifier": "not_applicable",
        "tauri.targets-routes": "not_applicable",
        "tauri.transport-requires-shell": "not_applicable",
    }


def test_tauri_gates_fail_invalid_identifier_missing_routes_and_orphaned_transports() -> None:
    path = ROOT / "examples/smart-kettle/smart-kettle.dash.json"
    contract = load_contract(path)
    assert contract.shell is not None and contract.shell.tauri is not None

    invalid_shell = contract.shell.model_copy(
        update={
            "tauri": contract.shell.tauri.model_copy(
                update={"identifier": "com._vibebb.smartkettle"}
            )
        }
    )
    invalid_identifier = contract.model_copy(update={"shell": invalid_shell})
    checks = check_contract(invalid_identifier, path)
    assert _check_by_id(checks, "tauri.identifier").status == "fail"

    platforms = [
        platform.model_copy(
            update={"routes": [route for route in platform.routes if route.browser != "tauri"]}
        )
        if platform.os == "windows"
        else platform
        for platform in contract.platforms
    ]
    missing_route = contract.model_copy(update={"platforms": platforms})
    checks = check_contract(missing_route, path)
    assert _check_by_id(checks, "tauri.targets-routes").status == "fail"

    no_shell = contract.model_copy(update={"shell": None})
    checks = check_contract(no_shell, path)
    assert _check_by_id(checks, "tauri.transport-requires-shell").status == "fail"


def test_tauri_matrix_rejects_ios_serial_and_chromeos_tauri_routes() -> None:
    path = ROOT / "examples/smart-kettle/smart-kettle.dash.json"
    contract = load_contract(path)
    platforms: list[PlatformDecl] = []
    for platform in contract.platforms:
        routes = list(platform.routes)
        if platform.os == "ios":
            routes.append(Route(browser="tauri", transport="kettle-tauri-serial"))
        if platform.os == "chromeos":
            routes.append(Route(browser="tauri", transport="kettle-tauri-ble"))
        platforms.append(platform.model_copy(update={"routes": routes}))
    invalid_routes = contract.model_copy(update={"platforms": platforms})

    checks = check_contract(invalid_routes, path)
    route_check = _check_by_id(checks, "platform.route-known")
    assert route_check.status == "fail"
    assert "ios/tauri/tauri_serial" in route_check.detail
    assert "chromeos/tauri/tauri_ble" in route_check.detail
