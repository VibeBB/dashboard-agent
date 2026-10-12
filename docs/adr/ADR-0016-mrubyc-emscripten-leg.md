# ADR-0016: mruby/c Emscripten WASM leg

Status: Accepted
Date: 2026-10-12

## Context

firmware-agent gained a mruby/c runtime for embedded UX logic
(VibeBB/firmware-agent#125): UX-creator authors `ux/*.rb` and seals them
into a `*.mruby-manifest.json`; the firmware contract pins that manifest
and gates bytecode freshness. The same Ruby UX logic should also run in
the dashboard-tools image so operators can exercise it without hardware —
Emscripten is already present for the codec parity leg.

## Decision

- New tools: `mrbc` built from mruby 4.0.0 and the upstream mruby/c tree
  at master `2dec4802` (the pin firmware-agent uses; it carries the
  `hal/emscripten` backend), fetched as sha256-verified tarballs in a
  dedicated `mruby` Dockerfile stage.
- Contract: `wasm.mrubyc` declares `sources` (workspace-relative `.rb`
  files) and an optional `memory_size` (default 64 KiB).
- Gate `wasm.mrubyc`: `build_mrubyc_module` compiles each source with
  `mrbc -B`, generates a C shim exporting `mruby_ux_init`/`mruby_ux_run`,
  links it with every mruby/c core source except `hal.c` plus
  `hal/emscripten/hal.c` via emcc (`-sASYNCIFY` for `sleep_ms`), then the
  node runner `wasm-mruby-run.mjs` boots the VM and runs all tasks to
  completion. Missing tools or a VM failure fail the gate; absent
  `wasm.mrubyc` reports `not_applicable`.

## Consequences

The image grows one build stage (ruby + build-essential + bison, mruby
sources discarded) and two runtime payloads (`/opt/mruby/bin/mrbc`,
`/opt/mrubyc`). Ruby UX logic parity between firmware and dashboard is
checked by compiling the same sources on both sides.
