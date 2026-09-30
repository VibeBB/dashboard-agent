# BSD Chromium port capabilities

The BSD matrix entry offers only WebSocket and WebRTC for Chromium ports and
Firefox. Hardware device APIs are not offered. These port-source findings are
the basis for that boundary.

## Port versions

FreeBSD `www/chromium` and OpenBSD `www/chromium` are at version
`154.0.8037.57`. NetBSD pkgsrc `www/chromium`, maintained by `kikadf`, has an
update dated 2026-09-29; binary packages lag behind. See the
[FreeBSD port](https://cgit.freebsd.org/ports/plain/www/chromium/files/patch-services_device_serial_BUILD.gn),
[OpenBSD port](https://raw.githubusercontent.com/openbsd/ports/master/www/chromium/patches/patch-services_device_serial_BUILD_gn),
and [NetBSD pkgsrc package](https://github.com/NetBSD/pkgsrc/tree/trunk/www/chromium).

## Web Serial

Web Serial is not built on any of the three BSD ports. Their
`services/device/serial/BUILD.gn` patches use the condition
`(!is_bsd && is_linux || is_chromeos) && use_udev`:
[FreeBSD](https://cgit.freebsd.org/ports/plain/www/chromium/files/patch-services_device_serial_BUILD.gn),
[OpenBSD](https://raw.githubusercontent.com/openbsd/ports/master/www/chromium/patches/patch-services_device_serial_BUILD_gn),
[NetBSD](https://raw.githubusercontent.com/NetBSD/pkgsrc/trunk/www/chromium/patches/patch-services_device_serial_BUILD_gn).
FreeBSD tracks [bug 280733, “web serial api access is disabled”](https://bugs.freebsd.org/bugzilla/show_bug.cgi?id=280733),
whose status is New.

## WebUSB

FreeBSD and NetBSD use `UsbServiceFake`; it is present only to keep WebAuthn/FIDO
working and does not provide real device access:
[FreeBSD](https://cgit.freebsd.org/ports/plain/www/chromium/files/patch-services_device_usb_usb__service.cc),
[NetBSD](https://raw.githubusercontent.com/NetBSD/pkgsrc/trunk/www/chromium/patches/patch-services_device_usb_usb__service.cc).
OpenBSD compiles the libusb-based `UsbServiceImpl`, but that backend is
untested with `pledge(2)` / `unveil(2)` sandboxing, so WebUSB is not offered:
[OpenBSD](https://raw.githubusercontent.com/openbsd/ports/master/www/chromium/patches/patch-services_device_usb_usb_service_cc).

## Web Bluetooth, WebSocket, WebRTC, and WebMCP

The ports disable BlueZ with `use_bluez = use_dbus && !is_bsd`; no Web Bluetooth
backend is built. FreeBSD and NetBSD carry the same patch as
[OpenBSD](https://raw.githubusercontent.com/openbsd/ports/master/www/chromium/patches/patch-device_bluetooth_cast_bluetooth_gni).
No BSD-specific disabling was found for standard WebSocket or WebRTC, so those
routes remain available. WebMCP remains Chromium's optional
[origin-trial/testing feature](https://developer.chrome.com/docs/ai/webmcp/imperative-api);
the runtime feature-detects `document.modelContext`.
