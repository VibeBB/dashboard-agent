# Architecture

## System boundary

The dashboard contract is the source of truth. Python validates it, generates
the browser application and interchange projections, and produces deterministic
gate reports. The TypeScript runtime is bundled into generated output; it has no
production npm dependencies. Vision notes and VibeBB Record Protocol (VRP)
records are advisory evidence and never alter a deterministic gate verdict.

## Python package

| Module | Responsibility |
| --- | --- |
| `src/dashboard/__init__.py`, `__main__.py` | Package version and `python -m dashboard` entry point. |
| `cli.py` | CLI argument parsing and JSON result/exit-code handling. |
| `contract.py` | Strict Pydantic dashboard contract models, JSON loading, and contract-relative path resolution. |
| `doctor.py` | Probes the pinned Python, Node, TypeScript, esbuild, Playwright, Emscripten, and Servo tools. |
| `matrix.py` | Browser/OS/transport support facts and route caveats. |
| `generate.py` | Builds the app, runtime configuration, protocol projections, WebMCP definitions, optional Tauri scaffold, and SHA-256 manifest. |
| `protocol.py`, `interchange.py` | Protocol interchange object and file hashing. |
| `webmcp.py` | Generates safety-aware WebMCP tool definitions and validates their schemas. |
| `gates.py`, `report.py` | Static/full deterministic gates and JSON/Markdown reports. |
| `screenshots.py` | Chromium desktop/mobile capture and metadata validation. |
| `servo.py`, `wasm.py` | Servo WebDriver smoke checks and Emscripten builds/parity checks. |
| `service.py` | JSON-returning application functions shared by the CLI and MCP server. |
| `mcp_server.py` | Stdio MCP tool declarations, dispatch, JSON responses, and inline screenshot attachments. |
| `requests.py` | Outbound DashboardRequest v2 creation for sister agents. |
| `liaison.py` | Dashboard-local SLP v2 inbox validation and response writing. |
| `records.py` | Typed VRP v1 records, hashing, append-only writers, and status summary. |
| `workspace.py` | Resolves workspace roots and prevents paths from escaping the workspace. |

See [Public function and CLI reference](reference.md) for every public function
and CLI subcommand.

## OpenHands plugin layout

`plugins/dashboard/` is the installable plugin:

- `.plugin/plugin.json` identifies the `dashboard` plugin, BSD-3-Clause
  license, VibeBB authorship, and `doctor` entry command.
- `.mcp.json` starts the stdio MCP server through the dashboard launcher.
- `agents/` defines `dashboard-architect`, `dashboard-developer`, and
  `dashboard-review`, each with the same dashboard MCP server and its own
  tool-hook declarations.
- `commands/` contains six `/dashboard:*` commands; `skills/` contains ten
  trigger-based knowledge packages.
- `hooks/hooks.json` configures plugin lifecycle hooks;
  `hooks/records-policy.json` configures VRP enforcement;
  `hooks/scripts/` contains shared and repository-specific hook scripts.
- `scripts/dashboard_launcher.py` resolves the installed plugin, source package,
  and dashboard-tools image.

## Launcher, image, MCP, and CLI

1. OpenHands starts the MCP server through `dashboard_launcher.py mcp_server`;
   command instructions use the same launcher for CLI requests.
2. The launcher accepts `DASHBOARD_LAUNCH_MODE=docker|host` and defaults to
   Docker. Docker mode requires a resolvable dashboard-tools image and the
   Docker executable. It creates or verifies the internal `dashboard-isolated`
   network, mounts the workspace, drops Linux capabilities, sets
   `no-new-privileges`, and runs as the caller's UID/GID.
3. The image pins the Python/Node/Chromium/Emscripten/Servo toolchain. A local
   source checkout, when resolved, is mounted read-only. The image execution
   network has no Internet egress.
4. Explicit developer-only host mode requires `DASHBOARD_SRC`; it is not an
   automatic fallback. `dashboard_launcher.py prewarm` pulls the configured
   image independently of launch mode.
5. The launcher maps `mcp_server` to `python -m dashboard.mcp_server`; other
   arguments are forwarded to `python -m dashboard`. MCP dispatch calls the
   same service functions that back the CLI.

The launcher also verifies published-image attestations according to
`DASHBOARD_VERIFY_ATTESTATION=auto|require|off`; that setting is distinct from
launch mode. See [Operations](operations.md).

## Contract-to-evidence data flow

1. **Contract:** `contract.py` validates a `<name>.dash.json` against the
   strict, versioned Pydantic schema.
2. **Generate:** `generate.py` emits the web app, runtime configuration,
   protocol JSON/header, WebMCP projection, C codec sources, optional Tauri
   scaffold, and `dash-manifest.json`. The manifest binds the contract and
   generated files by SHA-256.
3. **Static gates:** `gates.py` checks protocol, routes, widgets, hazards,
   imports, firmware bindings, and WebMCP. `dashboard check` writes
   `<name>.dash-report.json` and `.md`.
4. **Full gates:** the same deterministic checks are followed by generated-file
   freshness, runtime typecheck/tests, WASM parity and declared modules,
   Chromium end-to-end tests, screenshots, and a conditional Servo WebSocket
   smoke check. Missing tools and failed checks fail the report; inapplicable
   checks are explicitly `not_applicable`.
5. **Visual evidence:** `screenshots.py` captures desktop and mobile Chromium
   renders into `<name>.screens/`; Servo may add `servo.png`. MCP screenshot,
   full-gate, and smoke calls keep their JSON image-path list and can attach
   small PNG/JPEG files as MCP image content. Each image also receives a
   `vision_review` hint with a digest and checklist slug.
6. **Advisory records:** agents append VRP decisions, stage impressions, and
   vision reviews under `observations/dashboard/`. Post-tool hooks separately
   record which images and vision-tool responses were observed.
7. **Sister cooperation:** outbound requests are pinned to contract and
   firmware-contract hashes; inbound UX liaison requests and replies are
   validated locally by SLP v2.

Generated outputs are projections and must not be hand-edited. `protect-generated`
blocks protected writes, while the deterministic gates remain authoritative
even when a vision review or a record disagrees.
