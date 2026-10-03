# Operations

## SBOM attestations

`publish-dashboard-images.yml` generates and attests a package-level SPDX-2.3
SBOM for the published tools digest and uploads the full Syft SBOM as a 90-day
workflow-run artifact. The lock stores the returned `sbom_attestation` URL,
which `locked-image-check.yml` verifies when
present; an absent URL warns and continues.
The attested SBOM omits file entries and relationships involving files to
stay below the 16 MiB limit.

## Launcher-side verification

`DASHBOARD_VERIFY_ATTESTATION` accepts `auto` (the default), `require`, or
`off`. Before pulling a lock-provided image, and on every `prewarm`, the
launcher uses `gh attestation verify` with the lock entry and publisher
workflow. `auto` prints one note and skips for an image override, missing
attestation, missing `gh`, or failed `gh auth status`; once verification
starts, failure or timeout prevents the pull. `require` makes skip conditions
errors, while `off` never verifies. Ordinary invocations do not re-verify a
locally present image, and `--warn` doctor paths never verify.

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
scheduled checks; zizmor runs from a sha256-verified wheel and switches to
offline mode on bot digest-lock branches. Release automation dispatches and
waits for CI and workflow lint on the version-bump branch, then validates the
remotely installed plugin; its `dry_run` input rehearses the path without
merging or tagging.
The dashboard image publisher pushes only the immutable `<sha>-tools` tag,
gates on the Trivy fixable-CVE scan of the pushed digest, and only then
promotes `:latest` server-side (`buildx imagetools create`) — a gate failure
leaves the previous good `:latest` untouched. Build provenance and the
attestation URL are recorded in new digest locks. Locked-image checks verify
present attestations against this repository's publisher workflow; existing
pins without metadata continue with a warning until the next publish.

## Device and WebMCP safety

Browser transport selection occurs only from an explicit user click. The
runtime does not expose device-selection operations through WebMCP. Hazardous
commands require browser confirmation and ACK-enabled commands wait for the
matching command ID and sequence number. Keep untrusted telemetry visibly
separate from control state.

## Container hardening

Three layers were adopted after a comparative evaluation of Lynis,
`docker build --check`, Trivy, Grype, Dockle, and hadolint:

- **Dockerfile lint** (`dockerfile-lint` job in `ci.yml`): hadolint
  v2.15.1 via `hadolint-action` v3.5.0 plus `docker build --check`
  (BuildKit built-in). `.hadolint.yaml` allows only docker.io and
  ghcr.io registries and waives DL3008 (exact deb pins rot when archives
  drop them; downloaded tools are already version+sha256 pinned).
- **Image scan on publish** (`publish-dashboard-images.yml`): Trivy
  v0.75.0 via `trivy-action` v0.36.0 scans the pushed digest for
  CRITICAL/HIGH fixable vulnerabilities, secrets, and misconfiguration,
  gated (`exit-code 1`), with SARIF uploaded to code scanning
  (`category: trivy-dashboard-tools`) and a full JSON report as an
  artifact. The action is SHA-pinned and `version:` is explicit — the
  March 2026 Trivy supply-chain compromise made both non-negotiable.
- **Weekly audit** (`container-audit.yml`, Mondays 03:27 UTC): pulls the
  pinned digest from `docker/image-digests.json` (`dashboard_tools`),
  re-scans with a fresh vulnerability DB (new CVEs against the frozen
  image) sharing one `TRIVY_CACHE_DIR` across its scans, runs the Docker
  CIS compliance report (its nested `MisconfSummary` totals are read
  recursively; a 0/0 result fails the run instead of masquerading as
  coverage), runs an informational in-image Lynis audit pinned to the
  3.1.7 commit `2e99f922` (a moved tag fails the checkout), aggregates
  `container-hardening.json` (artifact), and edits/creates a
  "Container hardening report" issue.
  The issue closes automatically when fixable HIGH/CRITICAL findings
  reach zero. The Lynis Hardening Index is recorded as a trend metric
  only — its denominator shifts with container-skipped tests, so it
  never gates.

Not adopted, with reasons: `lynis audit dockerfile` (~6 greps, frozen
since 2018, subset of hadolint, hardening index always 1);
Dockle (v0.4.15 stale; its CIS-derived checks are covered by Trivy's
`--compliance docker-cis` report); Grype (equivalent for the SBOM path,
kept as fallback); checkov (redundant third linter); `cisofy/lynis`
Docker image (does not exist — Lynis runs from a pinned git clone);
non-root USER enforcement and HEALTHCHECK enforcement (CI tools images —
deferred policy decisions).

Changelog evaluation for the adopted pins is in the introducing PR.
Suppressions: `.hadolint.yaml` waivers above; `.trivyignore` holds
time-boxed finding IDs — entries must carry an `exp:` date and a
rationale line here when added.

The uv-managed CPython's bundled `pip` payload (vendored urllib3,
msgpack, setuptools — never invoked; dependencies install via `uv` and
the shipped venv is pip-less) is stripped in the `uv python install`
layer, so the publish gate stays clean without `.trivyignore` waivers.

First publish-gate firing (2026-10-03): 58 findings on the pushed
`dashboard-tools` digest. One Debian finding — `libpcre2-8-0`
10.46-1~deb13u2→u3 (CVE-2026-103111) — is fixed by an
`apt-get install --only-upgrade` in the Dockerfile (the pinned base
digest keeps shipping the old deb, so the upgrade has to land inside
the build). The remaining 57 sit inside vendored trees no upstream
release has patched yet: npm's bundled node_modules in emsdk's own
node and in the node base image (where tar 7.5.16 was the CRITICAL),
emscripten's eslint/tooling node_modules that `emcc` invokes at
runtime, and emsdk's vendored TypeScript go binary (`tsc`, built with
stdlib v1.26.4). Those carry per-CVE `exp:2027-01-03` waivers in
`.trivyignore` and re-check entries in
`scripts/dependency_update_deferrals.json` (docker-base
`emscripten/emsdk`, `node`).

The weekly audit runs Lynis as container root (`--user 0`) with the
committed `docker/lynis-container.prf` profile, which skips tests that
are inapplicable inside a container (kernel/systemd/mounts/storage/
network/PAM/accounting are governed by the runtime flags below, not the
image fs). The profile keeps the Hardening Index meaningful as an
image-actionable metric instead of counting host-side state the image
cannot control; remaining suggestions are fixed in the Dockerfile
(`UMASK 027` in login.defs) or silenced only with a documented reason.

`dashboard_launcher.py` applies the runtime-hardening flags the
container profile defers to: `--network` on an internal
(no-egress) Docker network, `--user uid:gid`, `--cap-drop ALL`,
`--security-opt no-new-privileges`. A `--read-only` root filesystem
stays an optional hardening for callers that supply tmpfs for tools
that need scratch space.

## CI runner network auditing

Every workflow job starts with `step-security/harden-runner` in audit-only
mode. It observes network egress without blocking requests; per-run insights
are available in the GitHub Actions job summary.

## Digest-lock PR verification

The publisher dispatches `ci.yml`, `workflow-lint.yml`, and
`locked-image-check.yml` on the lock branch — the last validates the new pin
(attestation verify plus full gates against the new digest) before merge —
then polls the authoritative required-check set for up to 30 minutes.
Non-required failures do not block publishing; a concluded required-check
failure or a PR closed without merge fails the job. A PR merged externally
triggers the existing post-merge main workflows without waiting for their
results. If required checks remain pending at the deadline, the publisher
arms squash auto-merge with branch deletion and exits successfully so
branch protection can complete the merge.

Merges performed by the digest-lock sweep (or by armed auto-merge) run under
`GITHUB_TOKEN`, which suppresses the push events `ci.yml` and
`locked-image-check.yml` rely on. The sweep therefore dispatches both
workflows on main after each successful merge, and
`main-ci-failure-issue.yml` runs a scheduled reconcile that closes failure
issues whose workflow's latest main run is green (bot-dispatched runs never
emit `workflow_run` events, so the watcher alone cannot close them).

SPDX generation prefers the GHCR registry source, writes temporary data under
the runner's temporary directory, and disables file metadata. The publisher
removes file entries and relationships involving files to produce the
package-level SPDX-2.3 SBOM. A guard reports disk space and the attested SBOM
size after transformation and fails above 16 MiB; the full Syft SBOM is
uploaded as a 90-day workflow-run artifact.

## Repository settings

These checks depend on settings outside the workflow files:

- `dependency-review.yml` needs the dependency graph (and Dependabot
  security updates) enabled for its license gate to see manifests.
- Release rehearsal is manual: `release.yml` has never run a real
  `workflow_dispatch`; a `dry_run` pass exercises the bump/dispatch/watch
  path before the first real release.
