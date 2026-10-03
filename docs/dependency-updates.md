# Dependency update reports

The weekly `Dependency update check` workflow writes a Markdown and JSON report
to the `dependency-updates` tracking issue. It does not modify dependency pins.
Review candidates in their source manifests and update the related
`THIRD_PARTY_NOTICES.md` entries when tool versions change.

Workflow reports are written under the runner's temporary directory and
include the run URL in both the issue and step summary. The workflow exposes
outdated and unknown counts; an issue remains open while either count is
nonzero. Dependabot applies a seven-day cooldown to all ecosystems and groups
GitHub Actions updates.

The checker covers:

- Direct Python package pins, transitive drift from `uv lock --upgrade
  --dry-run`, and the `uv` required-version in `pyproject.toml`.
- Digest-pinned `FROM` references and Servo's `SERVO_URL`/`SERVO_SHA256`
  arguments in `docker/*.Dockerfile`.
- Exact dependencies in `runtime/package.json`.
- npm and Rust crate pins emitted by `src/dashboard/generate.py` for Tauri
  scaffolds.
- SHA-pinned GitHub Actions in `.github/workflows/`.
- `git clone --branch` pins in `.github/workflows/` (e.g. the pinned
  CISOfy/lynis checkout in `container-audit.yml`) against the upstream
  repository's highest semver tag.

Short-lived reviewed exceptions are recorded in
`scripts/dependency_update_deferrals.json`. Each exception has a review date;
expired entries stop suppressing candidates automatically. Current deferrals
cover `mcp` 2.x (blocked by the SDK's `fastmcp<4` requirement; recheck
2027-04-01), the Tauri API/CLI and Rust crate releases available on 2026-09-30
(recheck 2026-10-07), and the digest-pinned `emscripten/emsdk` and `node` base
images awaiting re-scan on their next releases (2027-01-03).

To generate a report locally:

```bash
uv run python scripts/check_dependency_updates.py \
  --markdown report.md --json report.json
```

Review the complete upstream changelog before accepting a version update.

## 2026-10-03 update (sdk 1.51.0, uv 0.12.22, runtime pins)

| Component | From -> to | Changelog review decision |
| --- | --- | --- |
| openhands-sdk / openhands-tools | 1.50.1 -> 1.51.0 | All 18 commits in `v1.50.1..v1.51.0` reviewed. Bug fixes (prompt_cache_key via real provider, `/switch_llm` provider resolution, direct-routing classifier messages, `find_dotenv` assertion, `ACPAgentSettings.llm` deprecation) adopted automatically by the bump; plugin-load check passes unchanged. Not adopted: agent-profiles "tools-only control / persona replacement / resolve-and-finalize launch" (the plugin ships hooks and markdown agents, no agent-profiles wiring), tool-supplied system-prompt guidance (plugin registers only default SDK tools), OpenRouter verified provider (LLM profiles stay user-configured). SDK's pydantic bump lands transitively. |
| uv | 0.12.21 -> 0.12.22 | Adopted; relock hash-verification fix benefits `uv sync --locked` in CI. Not adopted: `UV_PYTHON_ARCH` (unused), `uv audit` preview flags (not wired into workflows), workspace-member lockfile recording (not a workspace repo). CPython 3.12.15 is available for future managed installs; no pin change. |
| ruff | 0.16.10 (unchanged) | Already resolved at 0.16.10 in the previous lock; zero diagnostics on this codebase. |
| anchore/sbom-action | v0.24.3 (unchanged) | Already pinned at the v0.24.3 commit since #54; verified, no change needed. |
| `@types/node` | 26.6.3 -> 26.6.4 | Types-only patch on the 26.x line; `tsc -p .` passes. |
| typescript | 7.1.0-dev.20261001.1 -> 7.1.0-dev.20261003.1 | Nightly channel (`next` dist-tag), no release notes by design; `tsc -p .` and `node --test test/` pass. |
| mcp | stays <2 (latest 2.3.0) | Still deferred: openhands-sdk 1.51.0 requires `fastmcp>=3.2.0,<4`, which caps `mcp<2.0`. Deferral entry refreshed, `review_by` kept at 2027-04-01. |
| transitive drift | various | `uv lock --upgrade` within constraints: boto3/botocore 1.43.108, cyclopts 5.1.1, fakeredis 2.39.0, filelock 4.0.9, google-auth-httplib2 0.4.4, litellm 1.103.2, markupsafe 3.0.4, openapi-pydantic 0.6.0, posthog 7.62.1, python-dotenv 1.2.4. No cap widenings required. |
