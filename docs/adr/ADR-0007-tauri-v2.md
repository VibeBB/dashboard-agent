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
`btleplug`, which is MIT/Apache-2.0/BSD-3-Clause licensed. PR A types only the
plugin API subsets locally and adds no runtime npm dependencies.

Model Tauri as browser `tauri`, with `tauri_ble` and `tauri_serial`
transports. Native device selection stays in the dashboard behind an
accessible picker and an explicit user action. WebMCP never exposes
connection or device-selection tools. Tauri's iOS target covers iPadOS;
serial is not offered on iOS or iPadOS.

Keep macOS and Xcode out of Docker. Native Apple builds require the appropriate
host toolchain and are not part of the containerized gates. Repository CI
builds unsigned artifacts only and does not upload to TestFlight.

## Consequences

The runtime remains dependency-free and transport selection remains
user-controlled. Tauri shell generation is deferred; contracts can validate
and gate shell metadata while dashboard generation projects only routes and
transports. Platform support remains fail-closed, including the Linux
WebKitGTK WebRTC build caveat.
