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
