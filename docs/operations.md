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

The launcher accepts `DASHBOARD_LAUNCH_MODE=docker|host|auto` (default
`docker`). Docker mode requires Docker and a resolvable tools image; if either
is unavailable, set `DASHBOARD_LAUNCH_MODE=host` to run on the host. Auto mode
retains Docker-when-available behavior. `prewarm` continues to pull the
configured image independently of launch mode.

The `dashboard-tools` image pins those tools and runs full gates in an internal
Docker network without Internet egress. Its build downloads and checksum-verifies
Servo and installs Playwright Chromium; the launcher creates or verifies the
internal network before each container run. MCP contract and output paths are
resolved under `OPENHANDS_PROJECT_DIR`; paths outside the workspace or through
symlink components are rejected.

## CI and image provenance

Workflow lint runs actionlint and zizmor on workflow changes and during weekly
scheduled checks. Release automation dispatches and waits for CI and workflow
lint on the version-bump branch, then validates the remotely installed plugin.
The dashboard image publisher attaches GitHub build provenance and records the
attestation URL in new digest locks. Locked-image checks verify present
attestations against this repository's publisher workflow; existing pins
without metadata continue with a warning until the next publish.

## Device and WebMCP safety

Browser transport selection occurs only from an explicit user click. The
runtime does not expose device-selection operations through WebMCP. Hazardous
commands require browser confirmation and ACK-enabled commands wait for the
matching command ID and sequence number. Keep untrusted telemetry visibly
separate from control state.
