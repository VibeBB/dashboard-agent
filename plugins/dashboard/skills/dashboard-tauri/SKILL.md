---
name: dashboard-tauri
description: Declare and gate Tauri v2 native BLE and serial routes.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - Tauri
  - native BLE
  - native serial
  - shell.tauri
---

# Tauri v2 routes

Declare the native shell under `shell.tauri` with a reverse-DNS identifier,
semantic version, product name, and unique target list. Use browser `tauri`
and transport kinds `tauri_ble` or `tauri_serial`; the corresponding gates
are `tauri.identifier`, `tauri.targets-routes`, and
`tauri.transport-requires-shell`.

Tauri v2 targets are Windows, macOS, Linux, Android, and iOS. The iOS target
also covers iPadOS routes. Native BLE is supported on every target; native
serial is not supported on iOS or iPadOS. Keep WebSocket and WebRTC routes
available where the webview supports them. Linux WebRTC depends on the
WebKitGTK build.

Native transport selection belongs in an accessible in-page picker. Scan or
list devices first, then connect only after an explicit user click. Never add
device-selection or connection tools to WebMCP. PR A carries route and
transport declarations into runtime configuration, but does not generate a
Tauri app scaffold or add runtime npm dependencies.
