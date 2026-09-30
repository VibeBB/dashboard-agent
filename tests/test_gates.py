from __future__ import annotations

from pathlib import Path

from dashboard.contract import PlatformDecl, Route, load_contract
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
