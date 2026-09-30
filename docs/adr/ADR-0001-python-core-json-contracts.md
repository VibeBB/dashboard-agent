# ADR-0001: Python core and JSON contracts

- Status: accepted
- Date: 2026-09-30

## Decision

Use a Python 3.12 core with Pydantic v2 to validate versioned JSON dashboard
contracts. Generate a dependency-free TypeScript browser runtime bundle from
those contracts.

## Consequences

Contracts are auditable, deterministic inputs shared by generation and gates.
Browser runtime logic stays small and does not acquire production npm
dependencies.
