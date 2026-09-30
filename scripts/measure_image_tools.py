#!/usr/bin/env python3
"""Measure tool versions and preserve each probe command and output."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

_IMAGE_REF = re.compile(r"[^@\s]+@sha256:[0-9a-f]{64}\Z")
_LOCAL_IMAGE_REF = re.compile(r"[a-z0-9][a-z0-9_.-]*:[a-z0-9][a-z0-9_.-]*\Z")
_PROBES = {
    "python": ["python", "--version"],
    "uv": ["uv", "--version"],
    "dashboard_agent": [
        "python",
        "-c",
        "import importlib.metadata as m; print(m.version('dashboard-agent'))",
    ],
    "node": ["node", "--version"],
    "npm": ["npm", "--version"],
    "typescript": ["./runtime/node_modules/.bin/tsc", "--version"],
    "playwright": [
        "node",
        "-p",
        "require('./runtime/node_modules/playwright/package.json').version",
    ],
    "chromium": [
        "node",
        "--input-type=module",
        "-e",
        (
            'import { chromium } from "./runtime/node_modules/playwright/index.mjs"; '
            "const browser = await chromium.launch(); "
            "console.log(await browser.version()); await browser.close();"
        ),
    ],
    "emcc": ["emcc", "--version"],
    "servoshell": ["servoshell", "--version"],
}


def measure(image_ref: str) -> dict[str, object]:
    if _IMAGE_REF.fullmatch(image_ref) is None and _LOCAL_IMAGE_REF.fullmatch(image_ref) is None:
        raise ValueError("image ref must be digest-pinned or a local tag")
    measurements: dict[str, dict[str, str]] = {}
    for name, command in _PROBES.items():
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--entrypoint",
                "",
                image_ref,
                *command,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
        if result.returncode:
            raise RuntimeError(f"{name} probe failed: {output or 'no output'}")
        if not output:
            raise ValueError(f"{name} probe returned no output")
        measurements[name] = {"command": " ".join(command), "output": output}
    return {
        "image_ref": image_ref,
        "measurements": measurements,
        "tools": {name: record["output"] for name, record in measurements.items()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-ref", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        value = measure(args.image_ref)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, UnicodeDecodeError, ValueError, RuntimeError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"WROTE {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
