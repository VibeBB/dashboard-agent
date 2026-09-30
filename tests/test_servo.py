from __future__ import annotations

import base64
import subprocess
from pathlib import Path
from typing import cast

from pytest import MonkeyPatch

from dashboard import servo


def test_servo_screenshot_failure_does_not_change_smoke_verdict(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    generated = tmp_path / "smart-kettle"
    generated.mkdir()
    (generated / "index.html").write_text("<h1>smart-kettle</h1>", encoding="utf-8")
    monkeypatch.setenv("SERVO_BIN", "/usr/bin/servo")

    def missing_servo(_binary: str) -> None:
        return None

    monkeypatch.setattr(servo.shutil, "which", missing_servo)

    class FakeProcess:
        pid = 999_999_999
        returncode: int | None = None

        def poll(self) -> int | None:
            return None

        def wait(self, timeout: float | None = None) -> int:
            del timeout
            self.returncode = 0
            return 0

    def popen(
        _command: list[str],
        *,
        stdout: object,
        stderr: int,
        start_new_session: bool,
    ) -> FakeProcess:
        del stdout, stderr, start_new_session
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", popen)

    def request(
        url: str,
        *,
        method: str = "GET",
        payload: object | None = None,
        timeout: float = 5,
        **_kwargs: object,
    ) -> object:
        del timeout
        if url.endswith("/status"):
            return {}
        if url.endswith("/session") and method == "POST":
            return {"value": {"sessionId": "session-1"}}
        if url.endswith("/url"):
            return {"value": None}
        if url.endswith("/screenshot"):
            raise OSError("screenshots are unsupported")
        if url.endswith("/session/session-1") and method == "DELETE":
            return {}
        if url.endswith("/execute/sync"):
            script = cast(dict[str, object], payload)["script"]
            if "window.__dashboard" in cast(str, script):
                return {
                    "value": {
                        "capabilities": {
                            "web_bluetooth": False,
                            "webusb": False,
                            "web_serial": False,
                            "websocket": True,
                        },
                        "routes": {
                            "usable": [{"kind": "websocket"}],
                            "unavailable": [
                                {"kind": "web_bluetooth"},
                                {"kind": "web_serial"},
                            ],
                        },
                    }
                }
            if "querySelector('h1')" in cast(str, script):
                return {"value": "smart-kettle"}
            return {"value": ["WebSocket"]}
        raise AssertionError(f"unexpected WebDriver request: {method} {url}")

    monkeypatch.setattr(servo, "_request", request)

    def kill_process_group(_pid: int, _signal: int) -> None:
        raise OSError

    monkeypatch.setattr(servo.os, "killpg", kill_process_group)

    result = servo.smoke(generated)

    assert result.ok is True
    assert result.screenshot is None
    assert "servo screenshot unavailable: screenshots are unsupported" in result.detail


def test_servo_screenshot_decodes_webdriver_png(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    image = b"\x89PNG\r\n\x1a\nservo"

    def request(_url: str, **_kwargs: object) -> object:
        return {"value": base64.b64encode(image).decode("ascii")}

    monkeypatch.setattr(servo, "_request", request)
    app = tmp_path / "generated"
    app.mkdir()

    path, error = servo.save_screenshot("http://127.0.0.1:4444/session/id", app)

    assert error is None
    assert path == tmp_path / "generated.screens" / "servo.png"
    assert path is not None
    assert path.read_bytes() == image


def test_servo_screenshot_uses_long_request_timeout(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    image = b"\x89PNG\r\n\x1a\nservo"
    timeouts: list[float] = []

    def request(_url: str, *, timeout: float = 5, **_kwargs: object) -> object:
        timeouts.append(timeout)
        return {"value": base64.b64encode(image).decode("ascii")}

    monkeypatch.setattr(servo, "_request", request)
    app = tmp_path / "generated"
    app.mkdir()

    path, error = servo.save_screenshot("http://127.0.0.1:4444/session/id", app)

    assert error is None
    assert path is not None
    assert timeouts == [30]
