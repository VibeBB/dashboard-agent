"""Probe the pinned dashboard toolchain."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ToolCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    status: Literal["ok", "warn", "fail"]
    version: str = ""


def _probe(name: str, argv: list[str], *, required: bool, expected: str | None = None) -> ToolCheck:
    candidate = Path(argv[0])
    executable = (
        str(candidate)
        if candidate.is_absolute() or candidate.parent != Path(".")
        else shutil.which(argv[0])
    )
    if executable is None or not Path(executable).is_file():
        return ToolCheck(name=name, status="fail" if required else "warn")
    try:
        result = subprocess.run(
            [executable, *argv[1:]],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ToolCheck(name=name, status="fail" if required else "warn")
    output = (result.stdout or result.stderr).strip().splitlines()
    version = output[0] if output else ""
    matches = result.returncode == 0 and (expected is None or expected in version)
    return ToolCheck(
        name=name,
        status="ok" if matches else "fail" if required else "warn",
        version=version,
    )


def checks() -> list[ToolCheck]:
    root = Path(__file__).resolve().parents[2]
    runtime_bin = root / "runtime" / "node_modules" / ".bin"
    servo = shutil.which("servoshell") or "servoshell"
    probes = (
        ("uv", ["uv", "--version"], True, "0.12.21"),
        ("node", ["node", "--version"], True, "v26."),
        ("typescript", [str(runtime_bin / "tsc"), "--version"], True, "7.1.0-dev.20260922.1"),
        ("esbuild", [str(runtime_bin / "esbuild"), "--version"], True, "0.28.2"),
        ("playwright", [str(runtime_bin / "playwright"), "--version"], True, "1.63.0"),
        ("emcc", ["emcc", "--version"], True, "6.0.10"),
        ("servo", [servo, "--version"], True, "0.6.0"),
    )
    return [
        _probe(name, argv, required=required, expected=expected)
        for name, argv, required, expected in probes
    ]
