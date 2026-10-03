from __future__ import annotations

import base64
import subprocess
from pathlib import Path
from typing import cast
from urllib.error import URLError

from pytest import MonkeyPatch

from dashboard import servo


def _stub_smoke_attempts(
    monkeypatch: MonkeyPatch,
    outcomes: list[servo.SmokeResult],
) -> list[int]:
    calls: list[int] = []

    def smoke_once(
        _generated_dir: Path,
        _log_path: Path,
        attempt: int,
    ) -> servo.SmokeResult:
        calls.append(attempt)
        return outcomes[attempt - 1]

    def log_tail(_path: Path) -> str:
        return "last Servo log line"

    monkeypatch.setattr(servo, "_smoke_once", smoke_once)
    monkeypatch.setattr(servo, "_servo_log_tail", log_tail)
    return calls


def test_servo_smoke_navigation_timeout_and_private_xdg_environment(
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
    popen_environments: list[dict[str, str]] = []

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
        env: dict[str, str],
    ) -> FakeProcess:
        del stdout, stderr, start_new_session
        popen_environments.append(env)
        runtime_dir = Path(env["XDG_RUNTIME_DIR"])
        cache_dir = Path(env["XDG_CACHE_HOME"])
        assert runtime_dir.stat().st_mode & 0o777 == 0o700
        assert cache_dir.is_dir()
        (cache_dir / "write-test").write_text("writable", encoding="utf-8")
        return FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", popen)

    navigation_timeouts: list[float] = []
    heading_timeouts: list[float] = []
    controls_timeouts: list[float] = []

    def request(
        url: str,
        *,
        method: str = "GET",
        payload: object | None = None,
        timeout: float = 5,
        **_kwargs: object,
    ) -> object:
        if url.endswith("/status"):
            return {}
        if url.endswith("/session") and method == "POST":
            return {"value": {"sessionId": "session-1"}}
        if url.endswith("/url"):
            navigation_timeouts.append(timeout)
            if len(navigation_timeouts) == 1:
                raise TimeoutError("timed out")
            return {"value": None}
        if url.endswith("/screenshot"):
            raise OSError("screenshots are unsupported")
        if url.endswith("/session/session-1") and method == "DELETE":
            return {}
        if url.endswith("/execute/sync"):
            script = cast(dict[str, object], payload)["script"]
            if "button[data-transport]" in cast(str, script):
                controls_timeouts.append(timeout)
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
                heading_timeouts.append(timeout)
                return {"value": "smart-kettle"}
            return {"value": ["WebSocket"]}
        raise AssertionError(f"unexpected WebDriver request: {method} {url}")

    monkeypatch.setattr(servo, "_request", request)

    def kill_process_group(_pid: int, _signal: int) -> None:
        raise OSError

    monkeypatch.setattr(servo.os, "killpg", kill_process_group)

    result = servo.smoke(generated)

    assert result.ok is True
    assert result.attempts == 2
    assert result.screenshot is None
    assert "attempt 1 timed out: navigate timed out after 30s: timed out" in result.detail
    assert (
        "servo screenshot unavailable: screenshot failed: screenshots are unsupported"
        in result.detail
    )
    assert navigation_timeouts == [30, 30]
    assert heading_timeouts == [30]
    assert controls_timeouts == [30]
    assert len(popen_environments) == 2
    assert len({env["XDG_RUNTIME_DIR"] for env in popen_environments}) == 2
    assert len({env["XDG_CACHE_HOME"] for env in popen_environments}) == 2
    for env in popen_environments:
        assert "XDG_RUNTIME_DIR" in env
        assert "XDG_CACHE_HOME" in env
        assert not Path(env["XDG_RUNTIME_DIR"]).exists()
        assert not Path(env["XDG_CACHE_HOME"]).exists()


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


def test_servo_smoke_retries_once_after_timeout(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = _stub_smoke_attempts(
        monkeypatch,
        [
            servo.SmokeResult(ok=False, detail="WebDriver timed out", timed_out=True),
            servo.SmokeResult(ok=True, detail="Servo rendered dashboard"),
        ],
    )

    result = servo.smoke(tmp_path / "smart-kettle")

    assert result.ok is True
    assert result.attempts == 2
    assert calls == [1, 2]
    assert "attempt 1 timed out" in result.detail
    assert "attempt 2 passed" in result.detail
    assert "last Servo log line" in result.detail


def test_servo_smoke_fails_after_second_timeout(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = _stub_smoke_attempts(
        monkeypatch,
        [
            servo.SmokeResult(ok=False, detail="timed out", timed_out=True),
            servo.SmokeResult(ok=False, detail="timed out again", timed_out=True),
        ],
    )

    result = servo.smoke(tmp_path / "smart-kettle")

    assert result.ok is False
    assert result.attempts == 2
    assert calls == [1, 2]
    assert "attempt 1 timed out" in result.detail
    assert "attempt 2 timed out" in result.detail


def test_servo_smoke_does_not_retry_non_timeout_failure(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = _stub_smoke_attempts(
        monkeypatch,
        [servo.SmokeResult(ok=False, detail="Servo exited with code 1")],
    )

    result = servo.smoke(tmp_path / "smart-kettle")

    assert result.ok is False
    assert result.attempts == 1
    assert calls == [1]
    assert "attempt 1 failed" in result.detail
    assert "last Servo log line" in result.detail


def test_servo_smoke_retries_transient_page_failure(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = _stub_smoke_attempts(
        monkeypatch,
        [
            servo.SmokeResult(
                ok=False,
                detail=(
                    "execute(transport controls) failed: "
                    "Servo dashboard UI does not show the WebSocket route"
                ),
                transient=True,
            ),
            servo.SmokeResult(ok=True, detail="Servo rendered dashboard"),
        ],
    )

    result = servo.smoke(tmp_path / "smart-kettle")

    assert result.ok is True
    assert result.attempts == 2
    assert calls == [1, 2]
    assert "attempt 1 failed" in result.detail
    assert "attempt 2 passed" in result.detail


def test_servo_smoke_retries_wrapped_url_timeout(
    monkeypatch: MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[int] = []

    def smoke_once(
        _generated_dir: Path,
        _log_path: Path,
        attempt: int,
    ) -> servo.SmokeResult:
        calls.append(attempt)
        if attempt == 1:
            raise URLError(TimeoutError("timed out"))
        return servo.SmokeResult(ok=True, detail="Servo rendered dashboard")

    def log_tail(_path: Path) -> str:
        return "last Servo log line"

    monkeypatch.setattr(servo, "_smoke_once", smoke_once)
    monkeypatch.setattr(servo, "_servo_log_tail", log_tail)

    result = servo.smoke(tmp_path / "smart-kettle")

    assert result.ok is True
    assert result.attempts == 2
    assert calls == [1, 2]
    assert "attempt 1 timed out" in result.detail
    assert "attempt 2 passed" in result.detail
