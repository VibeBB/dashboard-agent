# Skills

The plugin defines ten keyword-triggered skills under
`plugins/dashboard/skills/`. Their trigger phrases come from each `SKILL.md`
frontmatter; each skill supplies focused process guidance for its topic.

| Skill | Trigger phrases | Content summary |
| --- | --- | --- |
| `dashboard-contract` | `dashboard contract`, `telemetry schema`, `device command` | Author and validate the versioned dashboard JSON contract, typed protocol, widget bindings, and device command surface. |
| `dashboard-platform-matrix` | `platform support`, `browser compatibility`, `Bluefy`, `BSD` | Choose only supported browser/transport routes, acknowledge route caveats, and explain unsupported platforms. |
| `dashboard-protocol` | `COBS`, `CRC16`, `protocol export` | Specify the COBS/CRC16 framing contract and protocol interchange/header outputs. |
| `dashboard-servo` | `Servo`, `browser smoke`, `WebDriver` | Run and interpret the Servo WebDriver smoke check without weakening its assertions. |
| `dashboard-sibling-cooperation` | `firmware handoff`, `sibling request`, `protocol interchange` | Exchange hash-pinned firmware/protocol artifacts and sibling requests without editing sibling inputs. Includes SLP v2 inbox/respond guidance. |
| `dashboard-tauri` | `Tauri`, `native BLE`, `native serial`, `shell.tauri` | Declare and gate the optional Tauri v2 shell and native BLE/serial routes. |
| `dashboard-transports` | `Web Bluetooth`, `WebUSB`, `Web Serial`, `WebSocket`, `WebRTC` | Configure browser and network transports, permissions, protocol framing, and safe user-gesture device selection. |
| `dashboard-wasm` | `WebAssembly`, `WASM`, `emscripten` | Build and test the shared C codec and contract-declared C modules with Emscripten. |
| `dashboard-webmcp` | `WebMCP`, `model context`, `browser agent tool` | Expose dashboard status, telemetry, and optional safety-aware commands via WebMCP. |
| `dashboard-workflow` | `dashboard`, `connected device`, `telemetry` | Coordinate the complete contract → generation → gates → visual review → liaison → handoff workflow and required records. |

Skills do not replace the contract schema or gate implementation. The
deterministic checks in `src/dashboard/` remain the authority for accepted
inputs and verdicts.
