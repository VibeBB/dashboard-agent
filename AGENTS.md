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
- `ensure_llm_profiles.py`, `_provenance.py`, and `safety_rail.py` are shared
  canonical hooks; keep their normalized ASTs synchronized across VibeBB agents.

## Voice and commit policy

- Code, comments, docs, and commit messages are English. README ends with a
  Japanese section.
- Commit style is `feat(scope): imperative summary`, at most 72 characters.

## Verification

```bash
uv sync --locked
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest --cov --cov-report=term-missing:skip-covered
uv run python scripts/check_shared_hooks.py
uv run --group sdk-check python scripts/check_plugin_load.py
uv run python scripts/verify_docs.py
cd runtime && npm ci && npx tsc -p . && node --test test/
```

The dashboard-tools image runs Chromium E2E, Emscripten parity, and Servo
WebDriver smoke checks in an internal Docker network without Internet egress
after build.

Shared workflows are canonical across the family; change all 11 copies together and update `EXPECTED` in `scripts/check_shared_workflows.py`.

## CI/CD

Digest-lock PRs use `scripts/publish_image_pin_pr.sh`: the publisher
dispatches `ci.yml` and `workflow-lint.yml` on the lock branch, then polls
the authoritative required-check set for up to 30 minutes. Non-required
failures do not block publishing; a concluded required-check failure or a PR
closed without merge fails the job. A PR merged externally triggers the
existing post-merge main workflows. If required checks are still pending at
the deadline, the publisher arms squash auto-merge with branch deletion and
exits successfully.

SPDX SBOM generation prefers registry pulls, uses runner temporary storage,
and disables file metadata. The attested SBOM is package-level SPDX 2.3;
file entries and relationships involving files are omitted to stay below
16 MiB. The full Syft SBOM is attached to the workflow run as a 90-day
artifact.
