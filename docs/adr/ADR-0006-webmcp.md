# ADR-0006: WebMCP tools

- Status: accepted
- Date: 2026-09-30

## Decision

Feature-detect `document.modelContext` and register dashboard status,
telemetry, and optionally command tools using the imperative WebMCP API.
Registration shares one `AbortController` signal for teardown. Device
selection is never exposed.

Command tools are consequential when they operate a hazardous widget, fail
closed while disconnected, use the UI's confirmation flow, and wait for
configured acknowledgements. Device telemetry is marked untrusted content.

## Consequences

WebMCP is optional and Chromium-only. Browsers without the API continue to
operate as normal dashboards and report WebMCP as unavailable.
