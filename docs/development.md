# Development

## Setup

The Python package is managed by `uv`; source requires Python 3.12 or newer.
Runtime TypeScript/JavaScript dependencies are pinned under `runtime/`.

```bash
uv sync --locked
cd runtime
npm ci
cd ..
```

The pinned Docker image is the default launcher environment and is required
for the full Chromium/Emscripten/Servo gate path. Check its tools with
`python -m dashboard doctor` through `plugins/dashboard/scripts/
dashboard_launcher.py`. For explicit local development only,
`DASHBOARD_LAUNCH_MODE=host` requires `DASHBOARD_SRC`; it is never an automatic
fallback. See [Operations](operations.md).

## Verification

The repository's full pre-review command set is:

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pyright
env -u BASH_ENV -u "BASH_FUNC_gh%%" uv run pytest --cov --cov-report=term-missing:skip-covered
uv run python scripts/check_shared_hooks.py
uv run --group sdk-check python scripts/check_plugin_load.py
uv run python scripts/verify_docs.py
cd runtime && npm ci && npx tsc -p . && node --test test/
```

For a documentation-only change, run the docs verifier, the targeted plugin
asset test and any docs/README guard tests, then Ruff:

```bash
uv run python scripts/verify_docs.py
env -u BASH_ENV -u "BASH_FUNC_gh%%" uv run pytest -q tests/test_plugin_assets.py
uv run ruff check .
```

Use `uv run python` for AST-hash-sensitive checks so the Python version is the
one resolved by the project rather than an older host interpreter. For the
smallest relevant test while iterating, select its individual test file; do
not weaken tests or gate assertions to obtain a pass.

## Test layout

- `tests/test_contract.py`, `test_platform_matrix.py`, `test_gates.py`,
  `test_generate.py`-related generation coverage, `test_protocol*`,
  `test_webmcp.py`, `test_tauri_scaffold.py`: Python contract, projection,
  matrix, protocol, gate, and scaffold behavior.
- `tests/test_cli.py`, `test_service.py`, `test_mcp_server.py`,
  `test_requests.py`, `test_liaison.py`, `test_records.py`: public CLI/service
  APIs, MCP routing, outbound requests, SLP inbox/respond, and VRP writers.
- `tests/test_screenshots.py`, `test_servo.py`, `test_vision_hooks.py`,
  `test_report_dashboard_status.py`, `test_ensure_llm_profiles_vision.py`:
  capture/smoke/record hooks and session/status integration.
- Launcher and tooling tests include `test_launcher.py`,
  `test_launcher_attestation.py`, `test_image_locks.py`,
  `test_doctor.py`, `test_plugin_assets.py`, `test_workflow_paths.py`, and
  dependency/release/publish/report tests.
- `runtime/test/` uses Node's built-in test runner for capabilities, codec,
  session, Tauri, WebMCP, and WASM parity/exports.
- `runtime/e2e/` contains Playwright Chromium tests for dashboard behavior,
  WebMCP enabled/disabled, and the Tauri bridge.

## Shared hooks, workflows, and generated files

`scripts/check_shared_hooks.py` compares normalized AST hashes for shared
family hooks. For any intentional shared-hook change, update the canonical
copy across the VibeBB family and its `EXPECTED` digest; run it with `uv run
python` so the AST parser is consistent. Repository-specific hooks such as
attachment intake, generated-file protection, record image observation, and
dashboard status reporting are not copied as canonical shared hooks.

Shared workflow files are checked separately by
`scripts/check_shared_workflows.py`; update all canonical copies together and
refresh its expected digest map. `scripts/check_plugin_load.py` verifies
plugin assets and hook registration. AgentDefinitions must declare their own
required per-tool hooks because plugin hooks do not propagate to tasks.

The `.dash.json` contract is the editable source of truth. Do not edit
`examples/*/out/`, `out/`, manifest, protocol header/JSON, reports, or
screenshots by hand. Regenerate projections and record VRP evidence through
the writers. Never edit sibling agent inputs or response artifacts manually.
