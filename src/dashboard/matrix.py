"""Browser hardware support facts used by validation and generated diagnostics."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from .contract import BrowserName, OSName, TransportKind

Support = tuple[str, str | None]

CAVEATS: dict[str, str] = {
    "linux-web-bluetooth-flag": "Linux Web Bluetooth requires a Chromium flag and BlueZ.",
    "android-webusb-driver": "Android WebUSB cannot claim interfaces owned by system drivers.",
    "android-web-serial-limited": (
        "Android Web Serial supports limited RFCOMM and USB serial devices."
    ),
    "bluefy-notifications": (
        "Bluefy Web Bluetooth notifications can be unreliable on some versions."
    ),
    "webusb-claimed-interface": "The operating system may reserve the requested USB interface.",
    "chromeos-managed-device-apis": (
        "Managed ChromeOS devices may restrict browser device APIs; check your admin policy."
    ),
    "bsd-hardware-apis-unverified": (
        "BSD Chromium has no Web Bluetooth backend and does not build Web Serial. "
        "WebUSB is fake-only on FreeBSD/NetBSD; OpenBSD's compiled libusb backend "
        "is unverified. Hardware routes are not offered; WebMCP requires "
        "Chromium's testing/origin-trial API."
    ),
    "local-network-access": (
        "The browser may require permission to access devices on the local network."
    ),
}

SUPPORT: dict[tuple[OSName, BrowserName, TransportKind], Support] = {}
_chromium = ("chrome", "edge", "opera")
_all_kinds: tuple[TransportKind, ...] = (
    "web_bluetooth",
    "webusb",
    "web_serial",
    "websocket",
    "webrtc",
)
for _os in ("windows", "macos", "chromeos"):
    for _browser in _chromium:
        for _kind in _all_kinds:
            SUPPORT[(_os, _browser, _kind)] = ("yes", None)
for _browser in _chromium:
    SUPPORT[("linux", _browser, "web_bluetooth")] = (
        "caveat",
        "linux-web-bluetooth-flag",
    )
    for _kind in ("webusb", "web_serial", "websocket", "webrtc"):
        SUPPORT[("linux", _browser, _kind)] = ("yes", None)
for _browser in _chromium:
    SUPPORT[("android", _browser, "web_bluetooth")] = ("yes", None)
    SUPPORT[("android", _browser, "webusb")] = ("caveat", "android-webusb-driver")
    SUPPORT[("android", _browser, "web_serial")] = (
        "caveat",
        "android-web-serial-limited",
    )
    for _kind in ("websocket", "webrtc"):
        SUPPORT[("android", _browser, _kind)] = ("yes", None)
for _kind in ("websocket", "webrtc"):
    SUPPORT[("android", "samsung_internet", _kind)] = ("yes", None)
for _os in ("windows", "macos", "linux", "android"):
    for _kind in ("websocket", "webrtc"):
        SUPPORT[(_os, "firefox", _kind)] = ("yes", None)
for _kind in ("websocket", "webrtc"):
    SUPPORT[("macos", "safari", _kind)] = ("yes", None)
for _browser in ("chrome", "firefox"):
    for _kind in ("websocket", "webrtc"):
        SUPPORT[("bsd", _browser, _kind)] = ("yes", None)
for _os in ("ios", "ipados"):
    for _browser in ("safari", "chrome", "edge", "firefox"):
        for _kind in ("websocket", "webrtc"):
            SUPPORT[(_os, _browser, _kind)] = ("yes", None)
    SUPPORT[(_os, "bluefy", "web_bluetooth")] = ("caveat", "bluefy-notifications")
    for _kind in ("websocket", "webrtc"):
        SUPPORT[(_os, "bluefy", _kind)] = ("yes", None)


def private_network_caveat(url: str) -> str | None:
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return None
    if not host:
        return None
    host = host.lower().rstrip(".")
    if host.endswith(".local"):
        return "local-network-access"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return None
    private_networks = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
    )
    if address.is_link_local or any(address in network for network in private_networks):
        return "local-network-access"
    return None


def route_caveats(
    os_name: OSName, browser: BrowserName, kind: TransportKind, url: str | None
) -> list[str]:
    support = SUPPORT.get((os_name, browser, kind))
    caveats = [support[1]] if support and support[0] == "caveat" and support[1] else []
    if kind == "webusb":
        caveats.append("webusb-claimed-interface")
    if os_name == "chromeos" and kind in ("web_bluetooth", "webusb", "web_serial"):
        caveats.append("chromeos-managed-device-apis")
    if kind in ("websocket", "webrtc") and url:
        local = private_network_caveat(url)
        if local:
            caveats.append(local)
    return sorted(set(caveats))


def route_support(os_name: OSName, browser: BrowserName, kind: TransportKind) -> Support | None:
    return SUPPORT.get((os_name, browser, kind))
