# AGENTS.md — VibeBB dashboard-agent

## Authoring rules

- Python 3.12 code under `src/dashboard/` owns contract validation, generation,
  gates, reports, protocol export, sibling requests, the dashboard-local SLP v2
  liaison implementation, and VRP v1 record writers.
- A `<name>.dash.json` contract is the source of truth. Files under
  `examples/*/out/` and `out/` are generated projections; do not edit them by
  hand.
- The browser runtime under `runtime/src/` is dependency-free in production.
  Hardware device selection must follow a user gesture and hazardous commands
  must fail closed behind in-page confirmation.
- Gates fail closed: missing tools, files, and unparseable output are failures.
- Sibling cooperation uses hash-pinned JSON imports/requests, protocol exports,
  and dashboard-local SLP v2 liaison responses. Never edit sibling repository
  inputs or hand-edit UX response artifacts.
- VRP decisions, impressions, and vision reviews are advisory evidence only;
  deterministic gates alone determine pass/fail.
- External tools run as subprocesses. Tool versions and downloaded artifacts
  are pinned and documented in `THIRD_PARTY_NOTICES.md`.
- `ensure_llm_profiles.py`, `_provenance.py`, `safety_rail.py`, `_records.py`,
  and `require_records.py` are shared canonical hooks; keep their normalized
  ASTs synchronized across VibeBB agents.
- `DASHBOARD_LAUNCH_MODE` accepts only `docker` (the default) or explicit
  developer-only `host`; `host` requires `DASHBOARD_SRC` and is never an
  automatic fallback. `DASHBOARD_VERIFY_ATTESTATION=auto|require|off` is a
  separate image-attestation setting.

## Layout

```text
src/dashboard/             # Python contract, generator, CLI/MCP, and gates
├── contract.py            # versioned DashboardContract and submodels
├── generate.py            # generated app, protocol, manifest, optional Tauri scaffold
├── gates.py, report.py    # deterministic static/full checks and reports
├── matrix.py              # OS/browser/transport support and caveats
├── screenshots.py, servo.py, wasm.py
├── service.py, cli.py, mcp_server.py
├── requests.py, liaison.py, records.py
└── workspace.py, protocol.py, interchange.py, webmcp.py, doctor.py
runtime/                   # dependency-free production TypeScript and browser tests
plugins/dashboard/         # AgentCanvas/OpenHands plugin assets
├── agents/                # architect, developer, independent reviewer
├── commands/              # six /dashboard:* command prompts
├── skills/                # ten domain/workflow skills plus two path rules
├── hooks/                 # lifecycle hooks, scripts, records policy
├── scripts/dashboard_launcher.py
├── .mcp.json
└── .plugin/plugin.json
tests/                     # Python unit/integration and plugin guard tests
scripts/                   # verification, dependency, image, workflow, and release tooling
docker/                    # pinned tools-image build and digest lock
docs/adr/ docs/research/   # design decisions and implementation research
```

The plugin launcher is the entry point for MCP and plugin commands. Docker
mode uses the pinned tools image; `prewarm` pulls it. Host mode is opt-in and
requires `DASHBOARD_SRC`. The image's full gates cover runtime, Chromium,
Emscripten, and Servo work.

## Voice and commit policy

- Code, comments, docs, and commit messages are English. README ends with a
  Japanese section.
- Use `feat(scope): imperative summary` for implementation changes and
  `docs: imperative summary` for documentation-only changes, at most 72
  characters.

## Verification

```bash
uv sync --locked
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run python scripts/structural_coverage.py run
uv run python scripts/check_shared_hooks.py
uv run --group sdk-check python scripts/check_plugin_load.py
uv run python scripts/verify_docs.py
cd runtime && npm ci && npx tsc -p . && node --test test/
```

For pytest in environments with inherited shell startup hooks, use
`env -u BASH_ENV -u "BASH_FUNC_gh%%" uv run pytest ...`.

The dashboard-tools image runs Chromium E2E, Emscripten parity, and Servo
WebDriver smoke checks in an internal Docker network without Internet egress
after build.

Shared workflows are canonical across the family; change all 11 copies together and update `EXPECTED` in `scripts/check_shared_workflows.py`.

## CI/CD

The release bump/dispatch/watch/merge state machine is script-backed
(`scripts/release_bump.sh`) with stubbed-`gh`/`git` pytest coverage,
so `release.yml`'s `dry_run` rehearsal can be exercised and maintained under
test. The publisher's `dry_run` dispatch input rehearses the Trivy/SBOM/
measure/smoke gates against a locally loaded image without pushing tags,
attesting, uploading SARIF, or opening the digest-lock PR.

Digest-lock PRs use `scripts/publish_image_pin_pr.sh`: the publisher
dispatches `ci.yml`, `workflow-lint.yml`, and `locked-image-check.yml` on the
lock branch, then polls the authoritative required-check set for up to 30
minutes. Non-required
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
