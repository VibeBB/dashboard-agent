# AGENTS.md — VibeBB dashboard-agent

## Authoring rules

- Python 3.12 code under `src/dashboard/` owns contract validation, generation,
  gates, reports, protocol export, and sibling requests.
- A `<name>.dash.json` contract is the source of truth. Files under
  `examples/*/out/` and `out/` are generated projections; do not edit them by
  hand.
- The browser runtime under `runtime/src/` is dependency-free in production.
  Hardware device selection must follow a user gesture and hazardous commands
  must fail closed behind in-page confirmation.
- Gates fail closed: missing tools, files, and unparseable output are failures.
- Sibling cooperation uses JSON request and protocol-export artifacts. Never
  edit sibling repository inputs.
- External tools run as subprocesses. Tool versions and downloaded artifacts
  are pinned and documented in `THIRD_PARTY_NOTICES.md`.

## Voice and commit policy

- Code, comments, docs, and commit messages are English. README ends with a
  Japanese section.
- Commit style is `feat(scope): imperative summary`, at most 72 characters.

## Verification

```bash
uv sync --locked
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest
uv run --group sdk-check python scripts/check_plugin_load.py
uv run python scripts/verify_docs.py
cd runtime && npm ci && npx tsc -p . && node --test test/
```

The dashboard-tools image runs Chromium E2E, Emscripten parity, and Servo
WebDriver smoke checks with network access disabled after build.
