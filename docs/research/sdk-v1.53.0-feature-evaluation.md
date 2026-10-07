# OpenHands SDK v1.53.0 feature evaluation (dashboard-agent)

Scope: `openhands-sdk` and `openhands-tools` move from 1.52.0 to 1.53.0 (GitHub
release 2026-10-05; both packages published on PyPI). The complete 6-PR upstream
range `v1.52.0..v1.53.0` was reviewed against the release notes and the source
diff of both tags. Servo moves from v0.6.0 to v0.7.0 in the same round.

Primary sources: [OpenHands SDK v1.53.0 release](https://github.com/OpenHands/software-agent-sdk/releases/tag/v1.53.0),
[Servo v0.7.0 release](https://github.com/servo/servo/releases/tag/v0.7.0).

## SDK 1.52.0 -> 1.53.0

| Upstream change | Decision | Evaluation |
| --- | --- | --- |
| #5024 fix(skills): exclude installed packages from the user skills scan | adopted implicitly | SDK-internal fix in `openhands/sdk/skills/skill.py`; skills inside the managed installed-packages directory no longer leak into the user-skill merge. Plugin skills and `Plugin.load` are unaffected; plugin-load check passes unchanged. |
| #5479 feat(agent-server): serve a manifest-declared SVG icon for canvas extensions | not adopted | New optional `icon` field on `CanvasExtensionManifest` (package-root-relative `.svg` path, containment-checked), served at `GET /canvas_extensions/installed/{name}/icon` with a CSP-sandboxed `FileResponse`. VibeBB plugins are AgentCanvas plugins (`.plugin/plugin.json`), not canvas extensions; nothing declares a canvas-extension entrypoint manifest. Revisit only if a repo ships a canvas extension. |
| #5476 fix(ci): pin the TypeScript client's Agent Server in the release PR | not applicable | Upstream release-CI change only; no repository behavior to adopt. |
| #5512 fix(ci): read the unreleased Agent Server contract from source on release PRs | not applicable | Upstream release-CI change only; no repository behavior to adopt. |
| #5513 docs: refresh AGENTS.md guidance | not applicable | Upstream documentation change; this repository maintains its own AGENTS.md. |
| #4782 chore: weekly test sweep removes low-value coverage | not applicable | Upstream test-only change; no repository behavior to adopt. |

Dependency constraint surface: `openhands-sdk`, `openhands-tools`, and
`openhands-agent-server` pyproject.tomls differ from v1.52.0 only in
`version = "1.53.0"` — `fastmcp >=3.2.0,<4`, `pydantic >=2.13.5`,
`pillow >=12.3.0`, and `requires-python >=3.12` are all unchanged (verified by
diffing the two tags).

## Servo 0.6.0 -> 0.7.0

Servo v0.7.0 ("all the changes from September", ~150 PRs, released 2026-10-05)
was reviewed via the release notes. The linux tarball
`servo-x86_64-linux-gnu.tar.gz` hashes to SHA-256
`728eba1be1cc1851e05dfaa90e18f98ab8644dd2355bedb0b8a5e89795ebe333`; its layout
is unchanged (top-level `servo/` containing `servoshell`) and its readelf
NEEDED shared-library set is identical to v0.6.0, so no new apt packages are
needed in `docker/dashboard-tools.Dockerfile`
(`libgstreamer-plugins-bad1.0-0` already provides `libgstplay-1.0` and
`libgstwebrtc-1.0`).

| Upstream change | Decision | Evaluation |
| --- | --- | --- |
| webdriver 0.54 upgrade; `webdriver: Use server shipped with crate` (#47628, #45316) | adopted with the pin | The dashboard smoke/screenshot path (`src/dashboard/servo.py`) uses standard WebDriver endpoints — no API change required. The `smoke.servo` gate and the `servoshell --version` doctor probe are the only version-coupled surfaces; both updated. |
| WebGL added to `default_web_features` (#47866) | adopted implicitly | Engine feature; no repository configuration needed. |
| CSS module scripts and text module scripts (#47813, #47863) | adopted implicitly | Script-loading correctness; generated dashboards benefit without changes. |
| Popup sandboxing (#47653) | adopted implicitly | Security hardening; applies to smoke-rendered pages transparently. |
| `getComposedRanges` on Selection (#47683) | adopted implicitly | DOM API addition; no dashboard call site needed. |
| icu4x 2.1, Stylo 2026-07-31, script/dom correctness fixes | adopted implicitly | Engine internals; picked up through the tarball bump. |

## Compatibility deferrals

MCP 2.x remains deferred: installed SDK 1.53.0 metadata continues to require
`fastmcp>=3.2.0,<4`, which caps `mcp<2`. The deferral reason was refreshed to
cite 1.53.0; `review_by` stays 2027-04-01.
