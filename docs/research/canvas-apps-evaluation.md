# AgentCanvas Apps (canvas extensions) evaluation (dashboard-agent)

Scope: the **Apps** surface shipped with AgentCanvas 1.25.0 — installed npm
package `@openhands/agent-canvas` on the VibeBB OpenHands host plus
`openhands-agent-server` 1.53.0 canvas-extension routers and manifest schema —
evaluated as the delivery vehicle for in-Canvas dashboard/report viewing. All
facts below were verified against installed source (dist types, bundled
`canvas-extension-api` skill contract, pydantic manifest validators, FastAPI
routers, live `/openapi.json`), not documentation alone.

Primary sources: installed `@openhands/agent-canvas` 1.25.0
(`dist/types/canvas-extension.d.ts`, `dist/api/canvas-extensions-service.js`,
bundled `skills/canvas-extension-api/references/v1-contract.md`,
`scripts/validate-extension.mjs`), installed `openhands-agent-server` 1.53.0
(`openhands/agent_server/canvas_extensions/`, `file_router.py`,
`workspace_router.py`, `conversation_router.py`, `bash_router.py`).

## Verified contract surface

| Surface | Verified behavior |
| --- | --- |
| Manifest | `canvas-extension.json` at the app package root; required `schema_version: 1`, kebab-case `name` (`^[a-z0-9]+(?:-[a-z0-9]+)*$`), `display_name`, semver `version`, package-relative `entrypoint` (containment-checked, no `..`), optional `.svg` `icon`; `contributes.pages[]` entries `{id, title, path, nav_label?, description?}` with `path` matching `^/[a-z0-9]+(?:-[a-z0-9]+)*(/[a-z0-9]+)*$` |
| Entrypoint | Self-contained ESM module exporting `activate(host)`; the bundled validator rejects dynamic/bare/remote imports, CommonJS, sourcemaps, and `registerPage` ids not declared in the manifest |
| Host API 1 | `host.apiVersion === "1"`, `host.extension`, `host.backend`, `host.registerPage(id, mount)` returning a disposer, `host.navigate(path)`, and `host.agentServer.request({method, path, body, headers})` — a same-origin fetch wrapper restricted to single-root-relative paths with automatic JSON/text response parsing (`responseType` is not plumbed through) |
| Routing | Pages mount at `/extensions/{extension-name}/{declared-page-path}`; `mount` receives `{container, path, navigate}` where `path` is the route remainder |
| Install | `POST /api/canvas-extensions/install` `{source: "github:owner/repo" | absolute path, ref, repo_path, force}`; installed under `~/.openhands/canvas-extensions/installed/`; plugin installation does **not** register canvas extensions — the app is a separate artifact |
| Enable model | Installs always land `enabled: false`; enabling is the user's consent to run trusted same-realm extension JS |
| Constraints | Apps must not create iframes or Workers; the only host-owned frame (`host.appBackendView`) requires unreleased managed-backend SDK support; no tab/panel/header contribution points, no theme tokens beyond inherited CSS custom properties, no WebSocket helper |

## Gaps against the "view generated dashboards in-canvas" goal

| Goal | Constraint found in source | Resolution |
| --- | --- | --- |
| Render `out/<design>/index.html` inside a Canvas page | Extension-created iframes are forbidden and `host.appBackendView` needs unreleased managed-backend support | Ship a structured `dash-report.json` viewer page — closest supported contribution |
| Link out to the workspace static file server | Apps cannot derive the Agent Server origin (no `window.location` assumption) and `agentServer.request` only returns parsed bodies, not navigable URLs | Surface generated-app directories as badges; the files remain reachable via the Agent Server API/CLI outside Canvas |
| List report files under `out/` | `GET /api/file/search_subdirs` returns **directories only**; no file-listing endpoint exists in 1.53.0 | Convention-based probe: `<out>/<design>.dash-report.json` for each directory inside `out/` plus the contract-directory name — matches `src/dashboard/generate.py`/`report.py` output layout |
| Remote workspaces | `/api/conversations/{id}/workspace` and `search_subdirs` cover `LocalWorkspace` only | Filter to `kind === "LocalWorkspace"` |

## Decision

Ship `plugins/dashboard/app/` — a schema-1 canvas extension contributing one
page (`/reports`) that renders gate reports in place. The `backend`/managed-backend
contribution was not used (unreleased SDK dependencies). Re-verify manifest and
host API on every AgentCanvas upgrade; both are versioned Beta surfaces.

## Compatibility deferrals

- Managed `backend` contribution (`host.appBackendView`, backend-process
  hosting): pending unreleased SDK PRs; re-evaluate when they land.
- Tab/panel/header contribution points: not present in host API 1.
