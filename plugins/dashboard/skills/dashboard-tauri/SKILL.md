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
device-selection or connection tools to WebMCP. The browser runtime remains
dependency-free; the optional generated shell injects its native plugin
backends separately.

## Generate and run the optional scaffold

When `shell.tauri` is present, `dashboard generate <contract>` writes a
standalone project to `out/<name>/tauri/`. Install its pinned dependencies and
run it with:

```bash
cd out/<name>/tauri
npm install
npx tauri dev
```

The generated README documents desktop and mobile build commands and links to
the official Tauri v2 OS prerequisites. The scaffold includes only the BLE
and serial plugins used by the contract; signing and store distribution remain
out of scope.

Files under `src-tauri/gen/` created by Tauri's Android or iOS init commands
are user-owned and preserved on regeneration.
