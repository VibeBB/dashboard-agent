# ADR-0017: mruby/c device-API stubs for the WASM leg

Status: Accepted
Date: 2026-10-12

## Context

UX-creator-agent authors device APIs as `*.mruby-api.json`
(VibeBB/UX-creator-agent#154), firmware-agent generates real C bindings
(VibeBB/firmware-agent#127), and simulation-agent stubs them for its
mruby/c WASM leg (VibeBB/simulation-agent#123, ADR-0013 there). A
dashboard contract whose `wasm.mrubyc` leg runs UX `.rb` that calls a
device class fails in a bare VM — `LED.set` is undefined.

## Decision

- `WasmMrubyc` gains optional `api_spec` (contract-relative
  `*.mruby-api.json`) and `expect` (transcript substrings).
- `src/dashboard/mruby_stub.py` renders `dash_api_stub.{c,h}` next to
  the build output (sister copy of `sim.mruby_stub` — the JSON is the
  contract, never shared code): the same class/module surface, constants
  via `mrbc_set_class_const`, instance classes via `mrbc_instance_new` +
  `mrbc_define_destructor`, `system_task` vm_id gate, positional decode
  with the OpenBlink do-while(0) idiom (`argc < i` required /
  `argc >= i` optional — argc excludes the receiver), `MRBC_KW_*`
  keyword decode + `MRBC_KW_DICT(rest)`, trailing blocks at
  `v[argc + 1]`/`v[argc + 2]`, `ArgumentError` on decode failure when
  `arg_errors: "raise"` (with the `mrbc_class_ArgumentError` extern),
  `expert` methods under `#if defined(<expert_define>)`.
- Each stub logs `API <Class>.<method>(<arg>=<value>)` and returns a
  deterministic neutral value of the declared type (typed arrays filled
  to `cap`); `expect` entries assert against the node transcript in the
  existing `wasm.mrubyc` check.
- An unparsable or missing spec fails `wasm.mrubyc` (fail-closed); the
  stub schema ignores unknown fields so a newer UX schema keeps working.

## Consequences

Dashboard contracts can now prove that UX logic exercises the device
API (`expect: ["API LED.set(part=led1, state=true)"]`) before the
firmware image runs it on hardware — the stub proves the calling
convention, never device behavior.
