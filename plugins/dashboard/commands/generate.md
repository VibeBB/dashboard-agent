---
description: Generate a dashboard application and protocol projections.
allowed-tools:
  - terminal
---

Run `dashboard generate <contract>` through the plugin launcher. Review the
manifest and generated route configuration; do not edit generated files by
hand. When the contract declares `shell.tauri`, the manifest also covers the
optional scaffold under `out/<name>/tauri/`. See its generated README before
installing dependencies or building the shell.
