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
Bytecode is generated into `out/`; never commit `*_bytecode.c` or the shim.
