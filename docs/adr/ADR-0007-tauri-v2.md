# ADR-0007: Tauri v2 native shell

- Status: accepted
- Date: 2026-09-30

## Context

The browser runtime needs native BLE and serial access in desktop and mobile
WebViews that do not expose browser hardware APIs. WebSocket and WebRTC remain
usable webview routes. Tauri 2.x is stable and has official iOS and Android
support; Wails v3 remains beta, with mobile support described as experimental.

## Decision

Use Tauri v2 as the native shell. The BLE integration uses
`tauri-plugin-blec` 0.17.0; the serial integration uses
`tauri-plugin-serialplugin` 3.0.7. Tauri is Apache-2.0 or MIT licensed, and
both plugin crates are MIT or Apache-2.0 licensed. The BLE backend uses
`btleplug`, which is MIT/Apache-2.0/BSD-3-Clause licensed. The browser runtime
types only the plugin API subsets it needs and adds no runtime npm
dependencies; the optional scaffold bundles a separate typed bridge.

Model Tauri as browser `tauri`, with `tauri_ble` and `tauri_serial`
transports. Native device selection stays in the dashboard behind an
accessible picker and an explicit user action. WebMCP never exposes
connection or device-selection tools. Tauri's iOS target covers iPadOS;
serial is not offered on iOS or iPadOS.

Keep macOS and Xcode out of Docker. Native Apple builds require the appropriate
host toolchain and are not part of the containerized gates. Repository CI
builds unsigned artifacts only and does not upload to TestFlight.

## Scaffold dependencies

When `shell.tauri` is present, dashboard generation writes a minimal Tauri
project under `out/<name>/tauri/`. The generated project pins its dependencies;
BLE and serial plugin packages are included only when their transport is
declared. These dependencies are not added to the dashboard runtime.

| Package | Pin | License |
| --- | --- | --- |
| `@tauri-apps/api` | 2.11.1 | Apache-2.0 or MIT |
| `@tauri-apps/cli` | 2.11.5 | Apache-2.0 or MIT |
| `esbuild` | 0.28.2 | MIT |
| `@mnlphlp/plugin-blec` | 0.17.0, BLE only | MIT or Apache-2.0 |
| `tauri-plugin-serialplugin-api` | 3.0.7, serial only | Apache-2.0 or MIT |
| Rust crate `tauri` | 2.11.6 | Apache-2.0 or MIT |
| Rust crate `tauri-build` | 2.6.3 | Apache-2.0 or MIT |
| Rust crate `tauri-plugin-blec` | 0.17.0, BLE only | MIT or Apache-2.0 |
| Rust crate `tauri-plugin-serialplugin` | 3.0.7, serial only | Apache-2.0 or MIT |

## Consequences

The runtime remains dependency-free and transport selection remains
user-controlled. The optional shell scaffold is generated separately from
the web runtime and remains a source project rather than a signed installer.
Platform support remains fail-closed, including the Linux WebKitGTK WebRTC
build caveat.
