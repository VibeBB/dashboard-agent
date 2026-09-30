"""Emscripten builds and runtime parity checks for portable C modules."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class WasmResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool
    detail: str


def _run(command: list[str], cwd: Path, timeout: int = 300) -> WasmResult:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return WasmResult(ok=False, detail=str(exc))
    detail = (result.stdout + result.stderr).strip() or f"exit code {result.returncode}"
    return WasmResult(ok=result.returncode == 0, detail=detail)


def build_codec_parity(root: Path, output: Path) -> WasmResult:
    emcc = shutil.which("emcc")
    node = shutil.which("node")
    if emcc is None or node is None:
        missing = [name for name, value in (("emcc", emcc), ("node", node)) if value is None]
        return WasmResult(ok=False, detail=f"required tool not found: {', '.join(missing)}")
    output.mkdir(parents=True, exist_ok=True)
    module = output / "dash-codec.mjs"
    built = _run(
        [
            emcc,
            "runtime/c/dash_codec.c",
            "-O2",
            "--no-entry",
            "-sMODULARIZE=1",
            "-sEXPORT_ES6=1",
            "-sEXPORT_NAME=createCodec",
            "-sALLOW_MEMORY_GROWTH=1",
            "-sEXPORTED_FUNCTIONS=['_dash_crc16','_dash_cobs_encode','_dash_cobs_decode','_malloc','_free']",
            "-sEXPORTED_RUNTIME_METHODS=['HEAPU8']",
            "-o",
            str(module),
        ],
        root,
    )
    if not built.ok:
        return built
    return _run([node, "runtime/test/wasm-parity.mjs", str(module)], root)


def build_module(
    root: Path,
    output: Path,
    sources: list[Path],
    exports: list[str],
) -> WasmResult:
    emcc = shutil.which("emcc")
    node = shutil.which("node")
    if emcc is None or node is None:
        missing = [name for name, value in (("emcc", emcc), ("node", node)) if value is None]
        return WasmResult(ok=False, detail=f"required tool not found: {', '.join(missing)}")
    output.mkdir(parents=True, exist_ok=True)
    module = output / "module.mjs"
    names = ",".join(f"_{name}" for name in exports)
    built = _run(
        [
            emcc,
            *(str(source) for source in sources),
            "--no-entry",
            "-sMODULARIZE=1",
            "-sEXPORT_ES6=1",
            "-sEXPORT_NAME=createModule",
            "-sALLOW_MEMORY_GROWTH=1",
            "-s",
            f"EXPORTED_FUNCTIONS=[{names}]",
            "-o",
            str(module),
        ],
        root,
    )
    if not built.ok:
        return built
    return _run(
        [
            node,
            "runtime/test/wasm-module-exports.mjs",
            str(module),
            *exports,
        ],
        root,
    )
