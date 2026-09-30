# ADR-0010: Screenshot vision lane

- Status: accepted
- Date: 2026-09-30

## Context

Full gates prove contract and runtime behavior but do not show an agent the
rendered dashboard. Visual review can catch layout and legibility problems
that deterministic behavior checks do not judge.

## Decision

Capture full-page Chromium screenshots at desktop (1280x800) and mobile
(390x844) after browser E2E. Record browser version, console and page errors,
image hashes and byte sizes, and contract and generated-manifest hashes.
Page errors fail the visual capture; console errors are recorded without
failing it. A fresh generated app is required for the `dashboard_screenshot`
CLI and MCP tool. Full gates and smoke MCP results attach their generated
images inline, with a maximum of eight images and four MiB per image. When
Servo supports WebDriver screenshots, save one after a successful smoke.

The screenshots are deterministic evidence, not an appearance score. Human or
vision-capable review is advisory and never changes a gate verdict or supplies
measured values.

## Consequences

The Chromium capture is a deterministic gate after E2E; it verifies that a
generated page renders without uncaught page errors, without judging visual
quality. Console errors remain visible in capture metadata. Servo screenshot
failure does not change the Servo smoke verdict, and oversized or excess MCP
images are represented by metadata without being attached.
