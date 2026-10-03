"""Probe the pinned dashboard toolchain."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict


class ToolCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    status: Literal["ok", "warn", "fail"]
    version: str = ""


def _probe(name: str, argv: list[str], *, required: bool, expected: str | None = None) -> ToolCheck:
    if expected == "":
        return ToolCheck(name=name, status="fail" if required else "warn")
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


def _runtime_version(root: Path, package_name: str) -> str:
    try:
        package_data = json.loads((root / "runtime" / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    if not isinstance(package_data, dict):
        return ""
    package = cast(dict[str, object], package_data)
    for section in ("devDependencies", "dependencies"):
        dependencies = package.get(section)
        if not isinstance(dependencies, dict):
            continue
        dependency_map = cast(dict[str, object], dependencies)
        version = dependency_map.get(package_name)
        if isinstance(version, str) and version:
            return version
    return ""


def checks() -> list[ToolCheck]:
    root = Path(__file__).resolve().parents[2]
    runtime_bin = root / "runtime" / "node_modules" / ".bin"
    servo = shutil.which("servoshell") or "servoshell"
    runtime_versions = {
        "typescript": _runtime_version(root, "typescript"),
        "esbuild": _runtime_version(root, "esbuild"),
        "playwright": _runtime_version(root, "@playwright/test"),
    }
    probes = (
        ("uv", ["uv", "--version"], True, "0.12.22"),
        ("node", ["node", "--version"], True, "v26."),
        (
            "typescript",
            [str(runtime_bin / "tsc"), "--version"],
            True,
            runtime_versions["typescript"],
        ),
        ("esbuild", [str(runtime_bin / "esbuild"), "--version"], True, runtime_versions["esbuild"]),
        (
            "playwright",
            [str(runtime_bin / "playwright"), "--version"],
            True,
            runtime_versions["playwright"],
        ),
        ("emcc", ["emcc", "--version"], True, "6.0.10"),
        ("servo", [servo, "--version"], True, "0.6.0"),
    )
    return [
        _probe(name, argv, required=required, expected=expected)
        for name, argv, required, expected in probes
    ]
