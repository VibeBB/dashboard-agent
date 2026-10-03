"""Headless Servo WebDriver smoke checks for generated dashboards."""

from __future__ import annotations

import base64
import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast
from urllib.error import URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict

_SCREENSHOT_TIMEOUT_S = 30
_WEBDRIVER_READY_TIMEOUT_S = 40
_DASHBOARD_INIT_TIMEOUT_S = 30
_WEBDRIVER_REQUEST_TIMEOUT_S = 5
_LOG_TAIL_LINES = 20


class SmokeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool
    detail: str
    screenshot: Path | None = None
    attempts: int = 1
    timed_out: bool = False
    # Transient failures (WebDriver races, page-state assertions) earn one
    # retry; a Servo process crash stays single-attempt.
    transient: bool = False


class _Handler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _request(
    url: str,
    *,
    method: str = "GET",
    payload: object | None = None,
    timeout: float = _WEBDRIVER_REQUEST_TIMEOUT_S,
) -> object:
    data = None if payload is None else json.dumps(payload).encode()
    request = Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw) if raw else {}


def _as_object(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return cast(dict[str, object], value)


def _as_array(value: object) -> list[object] | None:
    if not isinstance(value, list):
        return None
    return cast(list[object], value)


def _webdriver_value(payload: object) -> object:
    response = _as_object(payload)
    if response is None:
        raise RuntimeError(f"invalid WebDriver response: {payload}")
    value = response.get("value")
    value_object = _as_object(value)
    if value_object is not None and value_object.get("error"):
        raise RuntimeError(f"WebDriver error: {value_object}")
    return value


def _has_route_kind(value: object, kind: str) -> bool:
    route = _as_object(value)
    return route is not None and route.get("kind") == kind


def _is_timeout(exc: BaseException) -> bool:
    if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)):
        return True
    if isinstance(exc, URLError):
        reason = exc.reason
        return isinstance(reason, (TimeoutError, subprocess.TimeoutExpired)) or (
            "timed out" in str(reason).lower()
        )
    message = str(exc).lower()
    return "timed out" in message or ("webdriver error" in message and "timeout" in message)


def _webdriver_step[T](
    name: str,
    operation: Callable[[], T],
    *,
    timeout: float | None = None,
) -> T:
    try:
        return operation()
    except Exception as exc:
        if _is_timeout(exc):
            duration = f" after {timeout:g}s" if timeout is not None else ""
            raise RuntimeError(f"{name} timed out{duration}: {exc}") from exc
        raise RuntimeError(f"{name} failed: {exc}") from exc


def _servo_log_tail(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "(log unavailable)"
    return "\n".join(lines[-_LOG_TAIL_LINES:]) if lines else "(log empty)"


def save_screenshot(base: str, app: Path) -> tuple[Path | None, str | None]:
    try:
        value = _webdriver_step(
            "screenshot",
            lambda: _webdriver_value(_request(f"{base}/screenshot", timeout=_SCREENSHOT_TIMEOUT_S)),
            timeout=_SCREENSHOT_TIMEOUT_S,
        )
        if not isinstance(value, str):
            raise RuntimeError("Servo screenshot response did not contain base64 data")
        image = base64.b64decode(value, validate=True)
        if not image.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("Servo screenshot response is not a PNG")
        path = app.parent / f"{app.name}.screens" / "servo.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image)
        return path, None
    except Exception as exc:
        return None, str(exc)


def _smoke_once(generated_dir: Path, log_path: Path, attempt: int) -> SmokeResult:
    binary = os.environ.get("SERVO_BIN") or shutil.which("servoshell") or shutil.which("servo")
    if not binary:
        return SmokeResult(ok=False, detail="required tool not found: servo")
    app = generated_dir.resolve()
    if not (app / "index.html").is_file():
        return SmokeResult(ok=False, detail=f"generated dashboard not found: {app / 'index.html'}")
    webdriver_port = _free_port()

    def make_handler(
        request: socket.socket,
        client_address: tuple[str, int],
        server: ThreadingHTTPServer,
    ) -> _Handler:
        return _Handler(request, client_address, server, directory=str(app))

    http_server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler)
    http_server.daemon_threads = True
    page_url = f"http://127.0.0.1:{http_server.server_port}/"
    threading.Thread(target=http_server.serve_forever, daemon=True).start()
    with log_path.open("w" if attempt == 1 else "a", encoding="utf-8") as log:
        log.write(f"--- Servo attempt {attempt} ---\n")
        log.flush()
        process: subprocess.Popen[bytes] | None = None
        session_id: str | None = None
        runtime_dir: Path | None = None
        cache_dir: Path | None = None
        try:
            runtime_dir = Path(tempfile.mkdtemp(prefix="dashboard-servo-runtime-"))
            runtime_dir.chmod(0o700)
            cache_dir = Path(tempfile.mkdtemp(prefix="dashboard-servo-cache-"))
            cache_dir.chmod(0o700)
            servo_env = os.environ.copy()
            servo_env["XDG_RUNTIME_DIR"] = str(runtime_dir)
            servo_env["XDG_CACHE_HOME"] = str(cache_dir)
            process = subprocess.Popen(
                [
                    binary,
                    "--headless",
                    "--window-size",
                    "900x300",
                    f"--webdriver={webdriver_port}",
                    page_url,
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=servo_env,
            )
            webdriver = f"http://127.0.0.1:{webdriver_port}"
            deadline = time.monotonic() + _WEBDRIVER_READY_TIMEOUT_S
            last_status_error: Exception | None = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    return SmokeResult(
                        ok=False,
                        detail=f"Servo exited with code {process.returncode}; log: {log_path}",
                    )
                try:
                    _webdriver_step(
                        "WebDriver status",
                        lambda: _request(f"{webdriver}/status"),
                        timeout=_WEBDRIVER_REQUEST_TIMEOUT_S,
                    )
                    break
                except (OSError, RuntimeError, URLError, TimeoutError, ValueError) as exc:
                    last_status_error = exc
                    time.sleep(0.25)
            else:
                detail = f"WebDriver status timed out after {_WEBDRIVER_READY_TIMEOUT_S}s"
                if last_status_error is not None:
                    detail += f"; last request error: {last_status_error}"
                raise TimeoutError(detail)

            created = _webdriver_step(
                "create session",
                lambda: _request(
                    f"{webdriver}/session",
                    method="POST",
                    payload={"capabilities": {"alwaysMatch": {"browserName": "servo"}}},
                ),
                timeout=_WEBDRIVER_REQUEST_TIMEOUT_S,
            )
            value = _webdriver_step("create session response", lambda: _webdriver_value(created))
            value_object = _as_object(value)
            session_id_value = value_object.get("sessionId") if value_object is not None else None
            if not isinstance(session_id_value, str):
                raise RuntimeError(
                    f"create session failed: WebDriver did not return a session id: {created}"
                )
            session_id = session_id_value
            base = f"{webdriver}/session/{session_id}"
            _webdriver_step(
                "navigate",
                lambda: _request(
                    f"{base}/url",
                    method="POST",
                    payload={"url": page_url},
                    timeout=_DASHBOARD_INIT_TIMEOUT_S,
                ),
                timeout=_DASHBOARD_INIT_TIMEOUT_S,
            )
            deadline = time.monotonic() + _DASHBOARD_INIT_TIMEOUT_S
            diagnostics: dict[str, object] | None = None
            last_init_error: Exception | None = None
            while time.monotonic() < deadline:
                try:
                    result = _webdriver_step(
                        "execute(__dashboard)",
                        lambda: _webdriver_value(
                            _request(
                                f"{base}/execute/sync",
                                method="POST",
                                payload={
                                    "script": "return window.__dashboard ?? null;",
                                    "args": [],
                                },
                            )
                        ),
                        timeout=_WEBDRIVER_REQUEST_TIMEOUT_S,
                    )
                    result_object = _as_object(result)
                    if result_object is not None:
                        diagnostics = result_object
                        break
                except (OSError, RuntimeError, URLError, ValueError) as exc:
                    last_init_error = exc
                time.sleep(0.25)
            if diagnostics is None:
                detail = f"execute(__dashboard) timed out after {_DASHBOARD_INIT_TIMEOUT_S}s"
                if last_init_error is not None:
                    detail += f"; last request error: {last_init_error}"
                raise TimeoutError(detail)
            rendered = _webdriver_step(
                "execute(dashboard heading)",
                lambda: _webdriver_value(
                    _request(
                        f"{base}/execute/sync",
                        method="POST",
                        payload={
                            "script": "return document.querySelector('h1')?.textContent ?? null;",
                            "args": [],
                        },
                        timeout=_DASHBOARD_INIT_TIMEOUT_S,
                    )
                ),
                timeout=_DASHBOARD_INIT_TIMEOUT_S,
            )
            if rendered != app.name:
                raise RuntimeError(
                    f"execute(dashboard heading) failed: "
                    f"Servo rendered unexpected dashboard heading: {rendered}"
                )
            capabilities = _as_object(diagnostics.get("capabilities"))
            if capabilities is None:
                raise RuntimeError(
                    "execute(__dashboard) failed: dashboard diagnostics do not expose capabilities"
                )
            hardware_apis = ("web_bluetooth", "webusb", "web_serial")
            available = [name for name in hardware_apis if capabilities.get(name) is True]
            if available:
                raise RuntimeError(
                    "execute(__dashboard) failed: "
                    f"Servo unexpectedly exposed hardware APIs: {', '.join(available)}"
                )
            if capabilities.get("websocket") is not True:
                raise RuntimeError("execute(__dashboard) failed: Servo did not expose WebSocket")
            routes = _as_object(diagnostics.get("routes"))
            if routes is None:
                raise RuntimeError(
                    "execute(__dashboard) failed: "
                    "dashboard diagnostics do not expose route selection"
                )
            usable = _as_array(routes.get("usable"))
            if usable is None or not any(_has_route_kind(route, "websocket") for route in usable):
                raise RuntimeError(
                    "execute(__dashboard) failed: Servo did not expose a usable WebSocket route"
                )
            unavailable = _as_array(routes.get("unavailable"))
            if unavailable is None or not all(
                any(_has_route_kind(route, kind) for route in unavailable)
                for kind in ("web_bluetooth", "web_serial")
            ):
                raise RuntimeError(
                    "execute(__dashboard) failed: "
                    "Servo did not report its hardware routes as unavailable"
                )
            buttons = _as_array(
                _webdriver_step(
                    "execute(transport controls)",
                    lambda: _webdriver_value(
                        _request(
                            f"{base}/execute/sync",
                            method="POST",
                            payload={
                                "script": (
                                    "return Array.from(document.querySelectorAll("
                                    "'#connection-panel button[data-transport]')).map(button => "
                                    "button.textContent);"
                                ),
                                "args": [],
                            },
                            timeout=_DASHBOARD_INIT_TIMEOUT_S,
                        )
                    ),
                    timeout=_DASHBOARD_INIT_TIMEOUT_S,
                )
            )
            if buttons is None or not any(
                isinstance(label, str) and "websocket" in label.lower() for label in buttons
            ):
                raise RuntimeError(
                    "execute(transport controls) failed: "
                    "Servo dashboard UI does not show the WebSocket route"
                )
            if any(
                isinstance(label, str)
                and any(kind in label.lower() for kind in ("bluetooth", "webusb", "serial"))
                for label in buttons
            ):
                raise RuntimeError(
                    "execute(transport controls) failed: "
                    "Servo dashboard UI exposed an unavailable hardware route"
                )
            screenshot, screenshot_error = save_screenshot(base, app)
            screenshot_detail = (
                f"servo screenshot: {screenshot}"
                if screenshot is not None
                else f"servo screenshot unavailable: {screenshot_error}"
            )
            return SmokeResult(
                ok=True,
                detail=(
                    f"Servo rendered {app.name}; hardware APIs unavailable; "
                    "WebSocket route available; diagnostics initialized; "
                    f"log: {log_path}; {screenshot_detail}"
                ),
                screenshot=screenshot,
            )
        except (OSError, RuntimeError, URLError, TimeoutError, ValueError) as exc:
            return SmokeResult(
                ok=False,
                detail=f"{exc}; log: {log_path}",
                timed_out=_is_timeout(exc),
                transient=True,
            )
        finally:
            try:
                if session_id:
                    with suppress(OSError, RuntimeError, URLError, TimeoutError, ValueError):
                        _webdriver_step(
                            "delete session",
                            lambda: _request(
                                f"http://127.0.0.1:{webdriver_port}/session/{session_id}",
                                method="DELETE",
                            ),
                            timeout=_WEBDRIVER_REQUEST_TIMEOUT_S,
                        )
                http_server.shutdown()
                if process is not None:
                    try:
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGTERM)
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        with suppress(OSError):
                            os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
                    except OSError:
                        pass
                http_server.server_close()
            finally:
                if cache_dir is not None:
                    shutil.rmtree(cache_dir, ignore_errors=True)
                if runtime_dir is not None:
                    shutil.rmtree(runtime_dir, ignore_errors=True)


def smoke(generated_dir: Path) -> SmokeResult:
    app = generated_dir.resolve()
    log_path = app.parent / f"{app.name}.servo-smoke.log"
    results: list[SmokeResult] = []
    for attempt in (1, 2):
        try:
            result = _smoke_once(app, log_path, attempt)
        except (
            OSError,
            RuntimeError,
            URLError,
            TimeoutError,
            ValueError,
            subprocess.TimeoutExpired,
        ) as exc:
            result = SmokeResult(
                ok=False,
                detail=str(exc),
                timed_out=_is_timeout(exc),
                transient=True,
            )
        results.append(result)
        if result.ok or not (result.timed_out or result.transient):
            break

    summaries: list[str] = []
    for number, result in enumerate(results, start=1):
        outcome = "passed" if result.ok else "timed out" if result.timed_out else "failed"
        summaries.append(f"attempt {number} {outcome}: {result.detail}")
    detail = (
        f"attempts={len(results)}; {'; '.join(summaries)}; "
        f"Servo log tail ({log_path}):\n{_servo_log_tail(log_path)}"
    )
    return results[-1].model_copy(update={"attempts": len(results), "detail": detail})
