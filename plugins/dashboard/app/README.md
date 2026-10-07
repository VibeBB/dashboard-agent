# dashboard-reports — Agent Canvas app (Beta)

Canvas extension (`canvas-extension.json`, schema 1) for AgentCanvas 1.25.0+.
Adds a **Dashboard reports** page that scans local workspaces on the active
Agent Server and renders `*.dash-report.json` gate reports in place — no raw
file handling. See `docs/canvas-app.md` for install/enable steps and known
limitations.

## Layout

- `canvas-extension.json` — app manifest (schema 1)
- `extension.js` — self-contained ESM entrypoint exporting `activate(host)`;
  dependency-free, uses only `host.registerPage` and `host.agentServer.request`
- `icon.svg` — manifest icon served by the Agent Server
- `extension.test.js` — `node --test` contract tests with a fake host/DOM
- `package.json` — marks the package as ESM for Node test runs (not shipped
  to Canvas)

## Local verification

```bash
node --test plugins/dashboard/app/extension.test.js
node <host-skill>/scripts/validate-extension.mjs plugins/dashboard/app
uv run pytest -q tests/test_canvas_app.py
```

The validator ships with the host's `@openhands/extensions` skill package
(`canvas-extension-api`), not this repo.
