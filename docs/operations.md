# Operations

## Author and validate

Contracts are the source of truth. Validate the contract before generating
static projections:

```bash
uv run python -m dashboard validate examples/smart-kettle/smart-kettle.dash.json
uv run python -m dashboard generate examples/smart-kettle/smart-kettle.dash.json
uv run python -m dashboard check examples/smart-kettle/smart-kettle.dash.json
```

The generator writes the application, normalized runtime config, protocol
header and interchange JSON, WebMCP projection, and SHA-256 manifest into
`examples/<name>/out/<name>/`. If the contract declares `shell.tauri`, it
also writes a pinned Tauri v2 project to `out/<name>/tauri/`; otherwise no
Tauri scaffold is generated. The generated README documents prerequisites and
desktop/mobile commands.

## Local verification

Run Python tests, strict static checks, plugin loading, documentation checks,
and the dependency-free runtime tests as documented in [AGENTS.md](../AGENTS.md).
The full gate command additionally requires the generated app, Chromium,
Emscripten, and Servo:

```bash
uv run python -m dashboard gates examples/smart-kettle/smart-kettle.dash.json --full
```

The `dashboard-tools` image pins those tools and runs full gates without
network access. Its build downloads and checksum-verifies Servo and installs
Playwright Chromium; the gate run itself uses `--network none`.

## Device and WebMCP safety

Browser transport selection occurs only from an explicit user click. The
runtime does not expose device-selection operations through WebMCP. Hazardous
commands require browser confirmation and ACK-enabled commands wait for the
matching command ID and sequence number. Keep untrusted telemetry visibly
separate from control state.
