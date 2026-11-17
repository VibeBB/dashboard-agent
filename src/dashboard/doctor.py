"""Probe the pinned dashboard toolchain."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
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


def _uv_version(root: Path) -> str:
    try:
        with (root / "pyproject.toml").open("rb") as stream:
            data = tomllib.load(stream)
    except (OSError, ValueError):
        return ""
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return ""
    uv = cast(dict[str, object], tool).get("uv")
    if not isinstance(uv, dict):
        return ""
    required = cast(dict[str, object], uv).get("required-version")
    if not isinstance(required, str):
        return ""
    return required.removeprefix("==").removeprefix("v")


def _emsdk_version(root: Path) -> str:
    # The Dockerfile is the checker-covered pin source. Inside the tools image
    # it is only reachable through the launcher's workspace mount
    # (OPENHANDS_PROJECT_DIR); a bare container falls back to the vendored
    # toolchain's own version file.
    candidates = [root / "docker" / "dashboard-tools.Dockerfile"]
    project_dir = os.environ.get("OPENHANDS_PROJECT_DIR")
    if project_dir:
        candidates.append(Path(project_dir) / "docker" / "dashboard-tools.Dockerfile")
    for dockerfile in candidates:
        try:
            for line in dockerfile.read_text(encoding="utf-8").splitlines():
                if line.startswith("FROM emscripten/emsdk:"):
                    return line.split(":", 1)[1].split("@", 1)[0].split()[0]
        except OSError:
            continue
    try:
        return (
            Path("/emsdk/upstream/emscripten/emscripten-version.txt")
            .read_text(encoding="utf-8")
            .strip()
            .strip('"')
        )
    except OSError:
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
        ("uv", ["uv", "--version"], True, _uv_version(root)),
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
        ("emcc", ["emcc", "--version"], True, _emsdk_version(root)),
        ("servo", [servo, "--version"], True, "0.8.0"),
    )
    return [
        _probe(name, argv, required=required, expected=expected)
        for name, argv, required, expected in probes
    ]
