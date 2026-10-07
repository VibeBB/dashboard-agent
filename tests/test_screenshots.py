from __future__ import annotations

import json
import struct
import subprocess
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from dashboard import screenshots


def _png(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR" + struct.pack(">II", width, height)


def _setup(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> tuple[Path, Path]:
    generated = tmp_path / "generated-app"
    generated.mkdir()
    (generated / "index.html").write_text("<h1>Generated</h1>", encoding="utf-8")
    (generated / "dash-manifest.json").write_text(
        json.dumps({"contract_sha256": "a" * 64, "files": {}}),
        encoding="utf-8",
    )
    package = tmp_path / "node_modules" / "@playwright" / "test"
    package.mkdir(parents=True)
    script = tmp_path / "screenshot.mjs"
    script.write_text("", encoding="utf-8")

    def node_path(_name: str) -> str:
        return "/usr/bin/node"

    monkeypatch.setattr(screenshots.shutil, "which", node_path)
    monkeypatch.setattr(screenshots, "PLAYWRIGHT_PACKAGE", package)
    monkeypatch.setattr(screenshots, "SCREENSHOT_SCRIPT", script)
    return generated, tmp_path / "screens"


def _fake_runtime(
    monkeypatch: MonkeyPatch,
    generated: Path,
    *,
    page_errors: list[str] | None = None,
    console_errors: list[str] | None = None,
    invalid_png: bool = False,
    missing_png: bool = False,
    invalid_json: bool = False,
) -> None:
    def run(
        command: list[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, capture_output, text, timeout, check
        output = Path(command[command.index("--out") + 1])
        screens = output
        screens.mkdir(parents=True, exist_ok=True)
        if invalid_json:
            (screens / "screens.json").write_text("{", encoding="utf-8")
        else:
            viewports: list[dict[str, object]] = []
            for name, width, height in (("desktop", 1280, 800), ("mobile", 390, 844)):
                file_name = f"{name}.png"
                if not (missing_png and name == "mobile"):
                    image = (
                        b"not a PNG" if invalid_png and name == "desktop" else _png(width, height)
                    )
                    (screens / file_name).write_bytes(image)
                viewports.append(
                    {
                        "name": name,
                        "browser": "chromium",
                        "browser_version": "test-version",
                        "width": width,
                        "height": height,
                        "file": file_name,
                        "page_errors": (page_errors or []) if name == "desktop" else [],
                        "console_errors": (console_errors or []) if name == "mobile" else [],
                    }
                )
            (screens / "screens.json").write_text(
                json.dumps(
                    {
                        "browser": "chromium",
                        "browser_version": "test-version",
                        "viewports": viewports,
                    }
                ),
                encoding="utf-8",
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(screenshots.subprocess, "run", run)


def test_capture_enriches_screens_and_records_console_errors(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    generated, output = _setup(tmp_path, monkeypatch)
    _fake_runtime(monkeypatch, generated, console_errors=["network warning"])

    result = screenshots.capture(generated, output)

    assert result.ok is True
    assert [image.name for image in result.images] == ["desktop", "mobile"]
    assert all(image.path.parent == output / "generated-app.screens" for image in result.images)
    screens = json.loads((output / "generated-app.screens" / "screens.json").read_text())
    assert screens["contract_sha256"] == "a" * 64
    assert len(screens["generated_manifest_sha256"]) == 64
    assert screens["viewports"][0]["browser"] == "chromium"
    assert screens["viewports"][0]["browser_version"] == "test-version"
    assert screens["viewports"][1]["console_errors"] == ["network warning"]
    assert screens["viewports"][0]["sha256"] == result.images[0].sha256
    assert screens["viewports"][1]["bytes"] == result.images[1].bytes
    assert "console errors recorded" in result.detail


@pytest.mark.parametrize(
    ("page_errors", "invalid_png", "missing_png", "invalid_json", "detail"),
    [
        (["uncaught"], False, False, False, "page errors"),
        (None, True, False, False, "invalid PNG signature"),
        (None, False, True, False, "screenshot is missing"),
        (None, False, False, True, "cannot load screenshot metadata"),
    ],
)
def test_capture_fails_closed_for_bad_capture_results(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    page_errors: list[str] | None,
    invalid_png: bool,
    missing_png: bool,
    invalid_json: bool,
    detail: str,
) -> None:
    generated, output = _setup(tmp_path, monkeypatch)
    _fake_runtime(
        monkeypatch,
        generated,
        page_errors=page_errors,
        invalid_png=invalid_png,
        missing_png=missing_png,
        invalid_json=invalid_json,
    )

    result = screenshots.capture(generated, output)

    assert result.ok is False
    assert detail in result.detail


def test_capture_rejects_wrong_png_dimensions(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    generated, output = _setup(tmp_path, monkeypatch)

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        screens = Path(command[command.index("--out") + 1])
        screens.mkdir(parents=True, exist_ok=True)
        (screens / "desktop.png").write_bytes(_png(1279, 800))
        (screens / "mobile.png").write_bytes(_png(390, 844))
        (screens / "screens.json").write_text(
            json.dumps(
                {
                    "browser": "chromium",
                    "browser_version": "test",
                    "viewports": [
                        {
                            "name": name,
                            "browser": "chromium",
                            "browser_version": "test",
                            "width": width,
                            "height": height,
                            "file": f"{name}.png",
                            "page_errors": [],
                            "console_errors": [],
                        }
                        for name, width, height in (
                            ("desktop", 1280, 800),
                            ("mobile", 390, 844),
                        )
                    ],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(screenshots.subprocess, "run", run)

    result = screenshots.capture(generated, output)

    assert result.ok is False
    assert "dimensions are 1279x800" in result.detail


def test_capture_fails_when_node_or_playwright_is_missing(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    generated, output = _setup(tmp_path, monkeypatch)

    def missing_node(_name: str) -> None:
        return None

    def node_path(_name: str) -> str:
        return "/usr/bin/node"

    monkeypatch.setattr(screenshots.shutil, "which", missing_node)
    assert screenshots.capture(generated, output).detail == "required tool not found: node"

    monkeypatch.setattr(screenshots.shutil, "which", node_path)
    monkeypatch.setattr(screenshots, "PLAYWRIGHT_PACKAGE", tmp_path / "missing-package")
    assert "runtime dependency not found" in screenshots.capture(generated, output).detail


@pytest.mark.parametrize("failure", ["timeout", "nonzero", "oserror"])
def test_capture_fails_for_subprocess_timeout_or_error(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    failure: str,
) -> None:
    generated, output = _setup(tmp_path, monkeypatch)

    def run(
        command: list[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, capture_output, text, check
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, timeout)
        if failure == "oserror":
            raise OSError("node could not start")
        return subprocess.CompletedProcess(command, 2, "", "browser failed")

    monkeypatch.setattr(screenshots.subprocess, "run", run)

    result = screenshots.capture(generated, output)

    assert result.ok is False
    assert "failed" in result.detail


def test_capture_retries_transient_screenshot_failure(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    generated, output = _setup(tmp_path, monkeypatch)
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if len(calls) == 1:
            return subprocess.CompletedProcess(command, 1, "", "protocol error")
        screens = Path(command[command.index("--out") + 1])
        screens.mkdir(parents=True, exist_ok=True)
        for name, width, height in (("desktop", 1280, 800), ("mobile", 390, 844)):
            (screens / f"{name}.png").write_bytes(_png(width, height))
        viewports: list[dict[str, object]] = [
            {
                "name": name,
                "browser": "chromium",
                "browser_version": "test-version",
                "width": width,
                "height": height,
                "file": f"{name}.png",
                "page_errors": [],
                "console_errors": [],
            }
            for name, width, height in (("desktop", 1280, 800), ("mobile", 390, 844))
        ]
        (screens / "screens.json").write_text(
            json.dumps(
                {
                    "browser": "chromium",
                    "browser_version": "test-version",
                    "viewports": viewports,
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(screenshots.subprocess, "run", run)

    result = screenshots.capture(generated, output)

    assert result.ok is True
    assert len(calls) == 2
    assert [image.name for image in result.images] == ["desktop", "mobile"]


def test_capture_reports_both_attempts_when_retry_exhausted(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    generated, output = _setup(tmp_path, monkeypatch)

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "protocol error")

    monkeypatch.setattr(screenshots.subprocess, "run", run)

    result = screenshots.capture(generated, output)

    assert result.ok is False
    assert "attempt 1" in result.detail
    assert "attempt 2" in result.detail


def _chromium_available() -> bool:
    node = screenshots.shutil.which("node")
    if node is None or not screenshots.PLAYWRIGHT_PACKAGE.is_dir():
        return False
    try:
        result = subprocess.run(
            [
                node,
                "--input-type=module",
                "-e",
                "import { chromium } from '@playwright/test'; "
                "console.log(chromium.executablePath())",
            ],
            cwd=screenshots.SCREENSHOT_SCRIPT.parents[1],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and Path(result.stdout.strip()).is_file()


@pytest.mark.skipif(
    not _chromium_available(),
    reason="Playwright runtime dependencies and Chromium are required",
)
def test_real_chromium_capture(tmp_path: Path) -> None:
    generated = tmp_path / "generated-app"
    generated.mkdir()
    (generated / "index.html").write_text(
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<main id="connection-panel"><h1>Generated dashboard</h1></main>',
        encoding="utf-8",
    )
    (generated / "dash-manifest.json").write_text(
        json.dumps({"contract_sha256": "a" * 64, "files": {}}),
        encoding="utf-8",
    )

    result = screenshots.capture(generated, tmp_path / "output")

    assert result.ok is True, result.detail
    assert {image.name for image in result.images} == {"desktop", "mobile"}
