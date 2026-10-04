---
name: dashboard-sibling-cooperation
description: Exchange pinned protocol and change-request artifacts with sibling agents.
version: 0.1.1
license: BSD-3-Clause
triggers:
  - firmware handoff
  - sibling request
  - protocol interchange
---

# Dashboard sibling cooperation

Do not import sibling code or modify sibling repository files. Link copied
contracts through `imports[]` with SHA-256, use `dashboard protocol-export` for
firmware handoff, and create a `<name>.dash-request.json` with `dashboard
request` for requested changes. High-risk requests must state their rationale
and failing gate IDs.
