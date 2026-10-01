# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |

## Reporting a vulnerability

Please do not open public issues for security vulnerabilities. Report them
via GitHub's private vulnerability reporting on this repository, or by
contacting the maintainer directly. Include:

- the affected version/commit,
- a minimal reproduction (contract JSON, command, or payload),
- impact assessment if known.

You can expect an acknowledgement within a few days. We will coordinate a
fix and disclosure with you before publishing details.

## Scope notes

dashboard executes contract validation, gate evaluation, and dashboard
generation locally. The `protect-generated` hook and fail-closed gates
defend projection integrity but are not a sandbox: do not run untrusted
contracts in environments where a crafted file could reach other tooling —
generated dashboards render external data in a browser context. The MCP
server speaks stdio only and never opens network listeners.

Secrets must never be written to logs, inputs, contracts, or commits; see
the invariants in [AGENTS.md](AGENTS.md).
