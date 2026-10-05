---
name: dashboard-sibling-cooperation
description: Exchange pinned protocol and change-request artifacts with sibling agents.
version: 0.1.0
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

## UX liaison (SLP v2)

At session start, call `dashboard_ux_inbox` and answer each dashboard-targeted
request using `dashboard_ux_respond` only. Progress through `accepted`,
`in_progress`, then `done`, `needs_info`, `rejected`, or `deferred`. A `done`
response cites VRP decision and impression `event_id` values and attaches the
passing full gate report. Ask user questions via `questions_for_user`, re-read
stale inputs, and never edit `.ux-response.json` files by hand.
