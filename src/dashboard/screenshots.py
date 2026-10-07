"""Deterministic Chromium screenshots of generated dashboards."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict

_ROOT = Path(__file__).resolve().parents[2]
SCREENSHOT_SCRIPT = _ROOT / "runtime" / "scripts" / "screenshot.mjs"
PLAYWRIGHT_PACKAGE = _ROOT / "runtime" / "node_modules" / "@playwright" / "test"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_VIEWPORTS = {"desktop": (1280, 800), "mobile": (390, 844)}


class ScreenImage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    path: Path
    width: int
    height: int
    sha256: str
    bytes: int


class CaptureResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool
    detail: str
    images: list[ScreenImage]


def _failure(detail: str, images: list[ScreenImage] | None = None) -> CaptureResult:
    return CaptureResult(ok=False, detail=detail, images=images or [])


def _object(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return cast(dict[str, object], value)


def _string_list(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    items = cast(list[object], value)
    if any(not isinstance(item, str) for item in items):
        return None
    return cast(list[str], items)


def _contained_image(output: Path, value: str) -> Path | None:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    try:
        path = (output / relative).resolve()
    except (OSError, RuntimeError):
        return None
    try:
        path.relative_to(output.resolve())
    except ValueError:
        return None
    return path


def _run_screenshot_once(node: str, app: Path, output: Path, timeout: int) -> str | None:
    """Run one screenshot subprocess; return its failure detail or None."""
    try:
        result = subprocess.run(
            [node, str(SCREENSHOT_SCRIPT), "--app", str(app), "--out", str(output)],
            cwd=_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return str(exc)
    if result.returncode != 0:
        return (result.stderr + result.stdout).strip() or f"exit code {result.returncode}"
    return None


def capture(generated_dir: Path, out_dir: Path, *, timeout: int = 180) -> CaptureResult:
    node = shutil.which("node")
    if node is None:
        return _failure("required tool not found: node")
    if not PLAYWRIGHT_PACKAGE.is_dir():
        return _failure(
            "required runtime dependency not found: runtime/node_modules/@playwright/test"
        )
    if not SCREENSHOT_SCRIPT.is_file():
        return _failure(f"screenshot runtime not found: {SCREENSHOT_SCRIPT}")

    app = generated_dir.resolve()
    if not (app / "index.html").is_file():
        return _failure(f"generated dashboard not found: {app / 'index.html'}")
    manifest_path = app / "dash-manifest.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = _object(json.loads(manifest_bytes))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _failure(f"cannot load generation manifest: {exc}")
    if manifest is None:
        return _failure("generation manifest must be a JSON object")
    contract_sha256 = manifest.get("contract_sha256")
    if (
        not isinstance(contract_sha256, str)
        or len(contract_sha256) != 64
        or any(character not in "0123456789abcdef" for character in contract_sha256)
    ):
        return _failure("generation manifest has no valid contract_sha256")

    output = out_dir.resolve() / f"{app.name}.screens"
    # A transient Chromium driver failure (protocol error, process crash)
    # earns one retry; content-level validation failures stay single-attempt.
    errors: list[str] = []
    for _ in range(2):
        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return _failure(f"Chromium screenshot failed: {exc}")
        error = _run_screenshot_once(node, app, output, timeout)
        if error is None:
            break
        errors.append(error)
    else:
        detail = (
            errors[-1]
            if len(errors) == 1
            else "; ".join(
                f"attempt {number}: {error}" for number, error in enumerate(errors, start=1)
            )
        )
        return _failure(f"Chromium screenshot failed: {detail}")

    screens_path = output / "screens.json"
    try:
        screens_value: object = json.loads(screens_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _failure(f"cannot load screenshot metadata: {exc}")
    screens = _object(screens_value)
    if screens is None or screens.get("browser") != "chromium":
        return _failure("screenshot metadata must describe Chromium")
    browser_version = screens.get("browser_version")
    viewports_value = screens.get("viewports")
    if not isinstance(browser_version, str) or not browser_version:
        return _failure("screenshot metadata has no browser_version")
    if not isinstance(viewports_value, list):
        return _failure("screenshot metadata viewports must be a list")

    viewports = cast(list[object], viewports_value)
    by_name: dict[str, dict[str, object]] = {}
    for value in viewports:
        viewport = _object(value)
        if viewport is None:
            return _failure("screenshot metadata contains an invalid viewport")
        name = viewport.get("name")
        if not isinstance(name, str) or name in by_name:
            return _failure("screenshot metadata contains an invalid viewport name")
        by_name[name] = viewport
    if set(by_name) != set(_VIEWPORTS):
        return _failure("screenshot metadata must include desktop and mobile viewports")

    images: list[ScreenImage] = []
    enriched: list[dict[str, object]] = []
    page_errors: list[str] = []
    console_counts: dict[str, int] = {}
    for name, (expected_width, expected_height) in _VIEWPORTS.items():
        viewport = by_name[name]
        width = viewport.get("width")
        height = viewport.get("height")
        file_name = viewport.get("file")
        page_errors_value = _string_list(viewport.get("page_errors"))
        console_errors_value = _string_list(viewport.get("console_errors"))
        if (
            viewport.get("browser") != "chromium"
            or viewport.get("browser_version") != browser_version
            or not isinstance(width, int)
            or isinstance(width, bool)
            or not isinstance(height, int)
            or isinstance(height, bool)
            or width != expected_width
            or height != expected_height
            or not isinstance(file_name, str)
            or page_errors_value is None
            or console_errors_value is None
        ):
            return _failure(f"{name} screenshot metadata is invalid", images)
        image_path = _contained_image(output, file_name)
        if image_path is None or not image_path.is_file():
            return _failure(f"{name} screenshot is missing or outside the output directory", images)
        try:
            image_bytes = image_path.read_bytes()
        except OSError as exc:
            return _failure(f"cannot read {name} screenshot: {exc}", images)
        if len(image_bytes) < 24 or image_bytes[:8] != _PNG_SIGNATURE:
            return _failure(f"{name} screenshot has an invalid PNG signature", images)
        actual_width = int.from_bytes(image_bytes[16:20], "big")
        actual_height = int.from_bytes(image_bytes[20:24], "big")
        if actual_width != expected_width or actual_height < expected_height:
            return _failure(
                f"{name} screenshot dimensions are {actual_width}x{actual_height}; "
                f"expected {expected_width}x at least {expected_height}",
                images,
            )
        digest = hashlib.sha256(image_bytes).hexdigest()
        images.append(
            ScreenImage(
                name=name,
                path=image_path,
                width=actual_width,
                height=actual_height,
                sha256=digest,
                bytes=len(image_bytes),
            )
        )
        viewport["sha256"] = digest
        viewport["bytes"] = len(image_bytes)
        if page_errors_value:
            page_errors.extend(f"{name}: {error}" for error in page_errors_value)
        console_counts[name] = len(console_errors_value)
        enriched.append(viewport)

    screens["viewports"] = enriched
    screens["contract_sha256"] = contract_sha256
    screens["generated_manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    try:
        screens_path.write_text(
            json.dumps(screens, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        return _failure(f"cannot write screenshot metadata: {exc}", images)

    detail = "captured desktop and mobile Chromium screenshots"
    console_summary = ", ".join(f"{name}={count}" for name, count in console_counts.items())
    if any(console_counts.values()):
        detail += f"; console errors recorded ({console_summary})"
    if page_errors:
        return _failure(f"{detail}; page errors: {'; '.join(page_errors)}", images)
    return CaptureResult(ok=True, detail=detail, images=images)
