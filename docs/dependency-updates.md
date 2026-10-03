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
cover `@types/node` 26.6.3, the TypeScript 7.1.0 nightly dated 2026-09-30, and
the Tauri API/CLI and Rust crate releases available on 2026-09-30. Recheck all
three groups by 2026-10-07.

To generate a report locally:

```bash
uv run python scripts/check_dependency_updates.py \
  --markdown report.md --json report.json
```

Review the complete upstream changelog before accepting a version update.
