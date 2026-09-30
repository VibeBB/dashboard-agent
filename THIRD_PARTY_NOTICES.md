# Third-party notices

This project is distributed under BSD-3-Clause. The dashboard-tools container
includes or invokes the following third-party software:

| Component | Pin or source | License / use |
| --- | --- | --- |
| Debian 13 (`node:26-trixie-slim`) | `sha256:ec7758ee051e457b468b32bde57b0879010b325bb9862718e9615225ce4aaae1` | Debian packages; see Debian copyright files |
| Node.js | 26.10.0 image line | MIT |
| CPython | 3.12, installed by pinned uv | PSF-2.0 |
| uv | 0.12.21 | MIT / Apache-2.0 |
| Pydantic | `pydantic>=2` | MIT |
| MCP Python SDK | `mcp>=1.29,<2` | MIT |
| OpenHands SDK and tools | 1.50.0 (development plugin check) | MIT |
| TypeScript | 7.1.0-dev.20260922.1 | Apache-2.0 |
| esbuild | 0.28.2 | MIT |
| Playwright | 1.63.0 | Apache-2.0 |
| Chromium | Playwright 1.63.0 browser build | BSD-3-Clause and bundled notices |
| `@types/node` | 26.6.2 | MIT |
| `@types/web-bluetooth` | 0.0.21 | MIT |
| `@types/w3c-web-usb` | 1.0.14 | MIT |
| `@types/w3c-web-serial` | 1.0.8 | MIT |
| Emscripten SDK | 6.0.10, image digest `sha256:e077d54e2b8970575ebc4f185ac1de0b95c05f2b266134d4ba27449af7aebf65` | MIT / UIUC |
| Servo | v0.6.0, SHA-256 `ad951ede1a1a73899b822c9464f6bdb3ec25b531b27cd806671d79ac8b6a60d0` | MPL-2.0; unmodified binary invoked as a subprocess |
| GStreamer runtime packages | Debian 13 | LGPL-2.1-or-later |

Container package copyright and license texts are provided by Debian under
`/usr/share/doc`. Chromium's licenses are installed with the Playwright browser
cache.

## Optional generated Tauri scaffold dependencies

These packages are emitted only in a generated `out/<name>/tauri/` project;
they are not bundled in this repository. BLE and serial packages are included
only when the matching transport is declared.

| Component | Pin | License / use |
| --- | --- | --- |
| `@tauri-apps/api` | 2.11.1 | Apache-2.0 OR MIT; generated scaffold only |
| `@tauri-apps/cli` | 2.11.5 | Apache-2.0 OR MIT; generated scaffold only |
| `esbuild` | 0.28.2 | MIT; generated scaffold only |
| `@mnlphlp/plugin-blec` | 0.17.0 | MIT OR Apache-2.0; generated scaffold only, BLE |
| `tauri-plugin-serialplugin-api` | 3.0.7 | Apache-2.0 OR MIT; generated scaffold only, serial |
| Rust crate `tauri` | 2.11.6 | Apache-2.0 OR MIT; generated scaffold only |
| Rust crate `tauri-runtime` | 2.11.3 | Apache-2.0 OR MIT; generated scaffold only |
| Rust crate `tauri-runtime-wry` | 2.11.4 | Apache-2.0 OR MIT; generated scaffold only |
| Rust crate `tauri-macros` | 2.6.3 | Apache-2.0 OR MIT; generated scaffold only |
| Rust crate `tauri-build` | 2.6.3 | Apache-2.0 OR MIT; generated scaffold only |
| Rust crate `tauri-plugin-blec` | 0.17.0 | MIT OR Apache-2.0; generated scaffold only, BLE |
| Rust crate `tauri-plugin-serialplugin` | 3.0.7 | Apache-2.0 OR MIT; generated scaffold only, serial |
