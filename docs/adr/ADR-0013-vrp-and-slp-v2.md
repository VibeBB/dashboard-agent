# ADR-0013: VRP v1 records and SLP v2 liaison

- Status: accepted
- Date: 2026-10-01

## Context

Dashboard design decisions, visual review, and sister-agent handoffs need
structured evidence that is bound to the actual inputs and generated outputs.
Free-form model responses alone do not reliably show which artifacts were
reviewed or whether an inbound request became stale. At the same time, advisory
records and vision judgments must never override deterministic contract or
runtime gates.

## Decision

Implement a dashboard-local VibeBB Record Protocol v1 (VRP) writer and a strict
local Sister Liaison Protocol v2 (SLP) inbox/respond implementation. VRP stores
append-only decision, stage-impression, and vision-review events under
`observations/dashboard/`; writers bind files and directory trees with
SHA-256. A Stop hook revalidates required records and uses a bounded denial
budget.

SLP v2 validates UX-creator requests and dashboard responses without importing
UX-creator code. Inbox state is derived from request/response validity,
workspace-relative input hashes, response hashes, dependencies, and cycles.
The response tool is the only supported writer for `.ux-response.json`.
Outbound DashboardRequest v2 binds the dashboard contract and optional
firmware contract by SHA-256; high-risk requests cite a known VRP decision.

Deterministic dashboard gates remain the only source of pass/fail
determinations. A completed UX response must cite VRP evidence and a passing
full gate report; these requirements do not change the report verdict.

## Consequences

- Design choices and stages leave auditable records bound to artifact content,
  and images reviewed by the agent can be connected to hashes or tool events.
- Changed inputs make liaison responses stale instead of silently preserving
  an outdated completion.
- Dashboard can interoperate with sibling systems through versioned workspace
  JSON without a runtime dependency on their Python packages or repositories.
- Stop enforcement is bounded: after two denials, the hook records any
  remaining gap and permits the session to finish.
- Vision review and records improve traceability but remain advisory; static
  and full deterministic gate results stay authoritative.
- Plugin-level hooks do not propagate to sub-agents, so the family must decide
  separately whether sub-agent sessions should receive `require-records`
  Stop hooks.
