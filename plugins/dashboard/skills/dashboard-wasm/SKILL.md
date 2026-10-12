---
name: dashboard-wasm
description: Build and verify portable codec and declared C modules with Emscripten.
version: 0.1.0
license: BSD-3-Clause
triggers:
  - WebAssembly
  - WASM
  - emscripten
---

# Dashboard WASM

The portable C codec is built with the pinned Emscripten SDK inside the
dashboard-tools image. Full gates compare its CRC16/COBS results with the
TypeScript implementation and verify exported symbols for every declared WASM
module. Missing emcc is a gate failure, never a skip.

## mruby/c UX leg (`wasm.mrubyc`)

When a product embeds the mruby/c VM (firmware `mrubyc` contract), the same
`ux/*.rb` sources can run in this image: declare
`wasm.mrubyc.sources` (paths relative to the `.dash.json`) and an optional
`memory_size` (default 64 KiB). The `wasm.mrubyc` gate compiles each source
with the pinned `mrbc`, links it into the mruby/c WASM VM
(`hal/emscripten`), and boots it under Node — the same toolchain CI uses.

When the UX logic calls device APIs authored by UX-creator as
`*.mruby-api.json`, declare `wasm.mrubyc.api_spec` (path relative to the
`.dash.json`): `dash_api_stub` bindings are generated next to the module,
log `API <Class>.<method>(<args>)` transcript lines, honor the spec's
`system_task` vm_id gate and `arg_errors` semantics, and return neutral
values. `wasm.mrubyc.expect` lists transcript substrings the gate asserts
(e.g. `API LED.set(part=led1, state=true)`).

Bytecode is generated into `out/`; never commit `*_bytecode.c` or the shim.
