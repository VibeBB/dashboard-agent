from __future__ import annotations

from pathlib import Path

from dashboard.contract import BrowserName, OSName, TransportKind, load_contract
from dashboard.matrix import CAVEATS, SUPPORT, route_caveats, route_support

ROOT = Path(__file__).resolve().parents[1]


def _pairs(os_name: OSName) -> set[tuple[BrowserName, TransportKind, str, str | None]]:
    return {
        (browser, kind, support, caveat)
        for (candidate_os, browser, kind), (support, caveat) in SUPPORT.items()
        if candidate_os == os_name
    }


def test_ipados_support_pairs_match_ios_exactly() -> None:
    assert _pairs("ipados") == _pairs("ios")
    assert {
        (browser, kind)
        for browser, kind, _support, _caveat in _pairs("ipados")
        if kind in ("webusb", "web_serial")
    } == set()


def test_example_ipados_declarations_are_independent_and_match_requirements() -> None:
    kettle = load_contract(ROOT / "examples/smart-kettle/smart-kettle.dash.json")
    ios = next(platform for platform in kettle.platforms if platform.os == "ios")
    ipados = next(platform for platform in kettle.platforms if platform.os == "ipados")
    assert ipados.status == ios.status == "supported"
    assert [route.model_dump() for route in ipados.routes] == [
        route.model_dump() for route in ios.routes
    ]

    bench = load_contract(ROOT / "examples/bench-meter/bench-meter.dash.json")
    bench_ipados = next(platform for platform in bench.platforms if platform.os == "ipados")
    assert bench_ipados.status == "unsupported"
    assert bench_ipados.reason


def test_bsd_offers_only_websocket_and_webrtc_for_chromium_and_firefox() -> None:
    assert _pairs("bsd") == {
        ("chrome", "websocket", "yes", None),
        ("chrome", "webrtc", "yes", None),
        ("firefox", "websocket", "yes", None),
        ("firefox", "webrtc", "yes", None),
    }
    assert "bsd-hardware-apis-unverified" in CAVEATS
    assert "fake-only on FreeBSD/NetBSD" in CAVEATS["bsd-hardware-apis-unverified"]
    assert (
        "OpenBSD's compiled libusb backend is unverified" in CAVEATS["bsd-hardware-apis-unverified"]
    )


def test_chromeos_chrome_supports_all_five_transports() -> None:
    pairs = {
        kind
        for (os_name, browser, kind), _support in SUPPORT.items()
        if os_name == "chromeos" and browser == "chrome"
    }

    assert pairs == {
        "web_bluetooth",
        "webusb",
        "web_serial",
        "websocket",
        "webrtc",
    }


def test_platform_caveats_match_routes() -> None:
    assert route_caveats("ipados", "bluefy", "web_bluetooth", None) == ["bluefy-notifications"]
    assert route_caveats("chromeos", "chrome", "webusb", None) == [
        "chromeos-managed-device-apis",
        "webusb-claimed-interface",
    ]
    assert route_caveats("windows", "chrome", "webusb", None) == ["webusb-claimed-interface"]


def test_tauri_native_transport_pairs_follow_shell_targets() -> None:
    for os_name in ("windows", "macos", "linux", "android", "ios", "ipados"):
        assert route_support(os_name, "tauri", "tauri_ble") == ("yes", None)
        assert route_support(os_name, "tauri", "websocket") == ("yes", None)
        assert route_support(os_name, "tauri", "webrtc") is not None

    for os_name in ("windows", "macos", "linux", "android"):
        assert route_support(os_name, "tauri", "tauri_serial") == ("yes", None)
    assert route_support("ios", "tauri", "tauri_serial") is None
    assert route_support("ipados", "tauri", "tauri_serial") is None
    assert route_support("chromeos", "tauri", "tauri_ble") is None
    assert route_support("windows", "chrome", "tauri_ble") is None
    assert SUPPORT[("linux", "tauri", "webrtc")] == ("caveat", "webkitgtk-webrtc")
    assert route_caveats("linux", "tauri", "webrtc", None) == ["webkitgtk-webrtc"]
    assert route_caveats("linux", "tauri", "webrtc", "ws://kettle.local/ws") == [
        "local-network-access",
        "webkitgtk-webrtc",
    ]
