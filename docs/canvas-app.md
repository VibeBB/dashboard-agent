# Agent Canvas app: dashboard reports

`plugins/dashboard/app/` ships a Beta canvas extension (`canvas-extension.json`
schema 1) that adds a **Dashboard reports** page to AgentCanvas 1.25.0. The
page scans local workspaces on the active Agent Server for dashboard artifacts
under `out/` and renders `*.dash-report.json` gate reports inside Canvas —
verdict banner, per-check status/detail/evidence, contract metadata, the
Markdown projection, and the raw JSON — instead of opening files by hand.

The app is a separate install artifact from the `dashboard` plugin:
installing the plugin does **not** register the canvas extension, and
uninstalling one does not affect the other.

> **Beta caveat.** The canvas-extension manifest format is versioned
> (`schema_version: 1`) and the host API is pinned (`activate` requires
> `host.apiVersion === "1"`). Both may change across AgentCanvas releases;
> re-verify against the installed agent-canvas/agent-server sources before
> upgrading the app. See [AgentCanvas Apps evaluation](research/canvas-apps-evaluation.md).

## Install and enable

New installs always land **disabled** — enabling is an explicit consent step
because extension code runs as same-realm JavaScript in Canvas.

1. In AgentCanvas open **Customize → Apps → Install** and provide:
   - `source`: `github:VibeBB/dashboard-agent` (or an absolute path to a local
     checkout on the Agent Server host, e.g.
     `/home/devin/repos/dashboard-agent/plugins/dashboard/app`)
   - `repo_path`: `plugins/dashboard/app` — selects the app package inside the
     repository (omit when installing from a local path that is already the
     app directory)
   - `ref`: branch or tag to install from (optional)
2. Enable the app in **Customize → Apps** (toggle next to
   `dashboard-reports`).

Equivalent API call against the Agent Server:

```bash
curl -X POST http://127.0.0.1:18000/api/canvas-extensions/install \
  -H 'Content-Type: application/json' \
  -d '{"source": "github:VibeBB/dashboard-agent", "repo_path": "plugins/dashboard/app", "ref": "main"}'
```

The page then appears in the app navigation as **Dashboard reports** at
`/extensions/dashboard-reports/reports`. Uninstall from the same Apps panel.

## What the page does

- Lists local workspaces (`GET /api/conversations/search`, `LocalWorkspace`
  only, plus `GET /api/workspaces` registrations).
- Finds generated `out/` trees (`GET /api/file/search_subdirs`), then probes
  `<out>/<design>.dash-report.json` for each directory name inside `out/` and
  the owning contract-directory name (`GET /api/file/download`).
- Renders the report list (design, verdict, check counts, workspace) and a
  per-report detail view.

All requests are GETs through `host.agentServer.request` — the app is
read-only and carries no credentials of its own.

## Limitations (host API 1)

- **The generated dashboard app cannot be embedded in-canvas.** Host API 1
  forbids extension-created iframes/Workers and offers no way to derive a
  navigable workspace-file URL with credentials, so the interactive
  `out/<design>/index.html` view remains outside Canvas. The page surfaces
  generated-app directories as badges instead; this is the closest
  contribution the verified format supports. Revisit when a managed-backend
  or frame contribution point ships.
- **Local workspaces only.** Remote workspaces have no directory-listing or
  static-file surface on the local Agent Server and are filtered out.
- **Discovery is convention-based.** Reports are found only under `out/`
  directories that follow the plugin's `<design>/` + `<design>.dash-report.json`
  layout (the names the generator writes). Arbitrary paths are not searched.
- **Point-in-time snapshot.** The page reads files at scan time; use Rescan
  after running gates again.
