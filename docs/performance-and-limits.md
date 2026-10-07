# Performance and limits

## Deterministic and advisory work

Static validation and gate checks are deterministic. Full gates add runtime
and browser work; they run in the pinned dashboard-tools image by default when
invoked through the plugin. Vision review is human/model advisory and is not a
gate measurement.

The outer full-gate pipeline runs its phases in order. Chromium E2E uses
Playwright with `fullyParallel: false`; the configuration does not pin a
worker count. There is no dashboard CLI `--jobs` option. The browser runner
uses its own Playwright scheduling within that configuration.

## Timeouts

These are source-level defaults and bounds; actual total runtime depends on
machine/container startup and on which gates apply.

| Operation | Timeout |
| --- | --- |
| Individual doctor tool-version probe | 20 seconds |
| Generated esbuild bundle | 120 seconds |
| Emscripten build/parity subprocess | 300 seconds |
| Ordinary full-gate subprocess (`runtime.typecheck`, `runtime.test`, etc.) | 900 seconds |
| Chromium Playwright gate | 1,200 seconds |
| Chromium screenshot subprocess | 180 seconds by default; caller can supply a timeout. |
| Playwright test | 90 seconds; expectation timeout 10 seconds; local web server readiness 30 seconds. |
| Servo WebDriver request | 5 seconds |
| Servo WebDriver readiness | 40 seconds |
| Servo dashboard initialization/page-state wait | 30 seconds |
| Servo screenshot request | 30 seconds |
| Servo process cleanup wait | 5 seconds per bounded wait |

Servo retries one transient WebDriver/page-state failure; a Servo process
crash remains single-attempt. The full gate includes a Servo smoke only when a
WebSocket transport is declared.

## Image and screenshot bounds

- Desktop viewport: 1280×800; mobile: 390×844. Capture is full-page, so PNG
  height may be greater than the viewport height.
- Chromium capture requires fresh generated output and a valid
  `dash-manifest.json`; page errors fail capture. Console errors are recorded
  in `screens.json` but do not alone fail capture.
- MCP attaches at most eight PNG/JPEG files, each no larger than 4 MiB. Excess
  and oversized files retain path/hash metadata without inline bytes.
- `dashboard_screenshot`, full `dashboard_gates`, and `dashboard_smoke` may
  include images. Other MCP tools, including record tools, are text-only.
- Servo is a network/render smoke engine, not a hardware API test. Its
  screenshot is optional and screenshot failure does not change smoke verdict.

## Protocol and session bounds

- `protocol.max_frame_bytes`: 16–512.
- Field wire sizes: 1 byte for `u8`, `i8`, `bool`; 2 bytes for `u16`, `i16`;
  4 bytes for `u32`, `i32`, `f32`. The gate includes ID, sequence, payload,
  CRC16, COBS overhead, and the zero delimiter when checking encoded size.
- Connect timeout: 1,000–60,000 ms, default 10,000.
- ACK timeout: 50–10,000 ms, default 1,000.
- Reconnect attempts: 0–20, default 5; backoff 100–60,000 ms, default 1,000.
- Message IDs are 0–254; ID 255 is reserved for ACK frames.

## Platform and browser route limits

These are implemented support facts in `src/dashboard/matrix.py`, not a
promise that a particular device, driver, browser build, permission policy, or
network will work. Each contract must declare OS/browser/transport routes and
acknowledge all route caveats. `dashboard matrix` returns the full source
matrix.

| OS | Browser routes and transports implemented |
| --- | --- |
| Windows | Chrome/Edge/Opera: Web Bluetooth, WebUSB, Web Serial, WebSocket, WebRTC. Firefox: WebSocket/WebRTC. Tauri: native BLE/serial, WebSocket, WebRTC. |
| macOS | Chrome/Edge/Opera: all five browser transports. Firefox and Safari: WebSocket/WebRTC. Tauri: native BLE/serial, WebSocket, WebRTC. |
| Linux | Chrome/Edge/Opera: Web Bluetooth (flag + BlueZ caveat), WebUSB, Web Serial, WebSocket, WebRTC. Firefox: WebSocket/WebRTC. Tauri: native BLE/serial, WebSocket, WebRTC; Tauri WebRTC depends on the distro's WebKitGTK build. |
| ChromeOS | Chrome/Edge/Opera: all five browser transports. Managed-device policy can restrict Bluetooth/USB/Serial; WebUSB interfaces may be claimed by the OS. |
| Android | Chrome/Edge/Opera: Web Bluetooth, WebUSB (driver caveat), Web Serial (limited RFCOMM/USB serial), WebSocket, WebRTC. Samsung Internet and Firefox: WebSocket/WebRTC. Tauri: native BLE/serial, WebSocket, WebRTC. |
| iOS | Safari/Chrome/Edge/Firefox: WebSocket/WebRTC. Bluefy adds Web Bluetooth with a notification-reliability caveat. Tauri adds BLE/WebSocket/WebRTC; Tauri serial is not offered. |
| iPadOS | Same browser route pairs as iOS, with separate contract declarations. Tauri adds BLE/WebSocket/WebRTC. No browser WebUSB/Web Serial or Tauri serial route is implemented. |
| BSD | Chrome and Firefox: WebSocket/WebRTC only. Browser hardware routes are not offered; BSD Chromium disables Web Bluetooth, lacks Web Serial, and has fake-only/unverified WebUSB implementations. |

Cross-platform caveats include OS-reserved WebUSB interfaces, ChromeOS managed
API restrictions, and local-network permission for private/link-local/`.local`
WebSocket or WebRTC signaling endpoints. A Tauri route is a separate shell
declaration, not an ordinary browser route. Native Apple builds require the
appropriate host toolchain and are not part of the Docker gates. WebMCP is an
optional, feature-detected browser capability rather than a device transport;
the BSD Chromium route requires its testing/origin-trial API.

## Launcher and image requirements

`DASHBOARD_LAUNCH_MODE` accepts only `docker` (default) or explicit
developer-only `host`. Docker mode requires Docker and a resolvable pinned or
overridden dashboard-tools image; missing prerequisites fail rather than
falling back. Run the launcher `prewarm` command to pull the image. Host mode
requires `DASHBOARD_SRC` and is not a production fallback.

The image pins Node 26, uv 0.12.23, Emscripten 6.0.10, Servo 0.7.0, and the
runtime package-lock versions of TypeScript, esbuild, and Playwright. The
plugin doctor reports the declared tool versions and full-gate image
availability. Full gates also need Chromium installed through the pinned
image. The Tauri scaffold is generated but native build/signing is not part
of the full gate.

## Gate cost profile

| Gate group | Main work and cost |
| --- | --- |
| Static | Contract parsing, protocol/frame math, route/caveat validation, generated widget references, import/firmware hashing, WebMCP schema/safety checks; no browser launch. |
| Generated freshness | Hash every manifest-listed generated file and compare the contract hash. |
| Runtime | TypeScript typecheck and Node tests. |
| WASM | Emscripten-build the portable C codec and compare CRC/COBS behavior in Node; additionally build and check each declared module. |
| Chromium | Run browser end-to-end projects, including the WebMCP-enabled project and Tauri-bridge tests; configuration has no `fullyParallel` execution. |
| Visual capture | Launch Chromium at desktop/mobile sizes, write PNGs and metadata, and fail on page errors or invalid/missing capture artifacts. |
| Servo | Start headless Servo/WebDriver, load generated output, check expected hardware API degradation and usable WebSocket route; only when a WebSocket transport exists. |

Because the phases are ordered, their operation timeouts should not be added
as a single guaranteed end-to-end deadline. Docker image startup/pull and
runtime setup may add additional time. `dashboard check` is the lower-cost
contract-only gate; full gates are the authoritative release-quality check.
