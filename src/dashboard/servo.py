"""Headless Servo WebDriver smoke checks for generated dashboards."""

from __future__ import annotations

import base64
import json
import os
import shutil
import signal
import socket
import subprocess
import threading
import time
from contextlib import suppress
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast
from urllib.error import URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict

_SCREENSHOT_TIMEOUT_S = 30


class SmokeResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool
    detail: str
    screenshot: Path | None = None


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
    timeout: float = 5,
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


def save_screenshot(base: str, app: Path) -> tuple[Path | None, str | None]:
    try:
        value = _webdriver_value(_request(f"{base}/screenshot", timeout=_SCREENSHOT_TIMEOUT_S))
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


def smoke(generated_dir: Path) -> SmokeResult:
    binary = os.environ.get("SERVO_BIN") or shutil.which("servoshell") or shutil.which("servo")
    if not binary:
        return SmokeResult(ok=False, detail="required tool not found: servo")
    app = generated_dir.resolve()
    if not (app / "index.html").is_file():
        return SmokeResult(ok=False, detail=f"generated dashboard not found: {app / 'index.html'}")
    log_path = app.parent / f"{app.name}.servo-smoke.log"
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
    with log_path.open("w", encoding="utf-8") as log:
        process: subprocess.Popen[bytes] | None = None
        session_id: str | None = None
        try:
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
            )
            webdriver = f"http://127.0.0.1:{webdriver_port}"
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    return SmokeResult(
                        ok=False,
                        detail=f"Servo exited with code {process.returncode}; log: {log_path}",
                    )
                try:
                    _request(f"{webdriver}/status")
                    break
                except (OSError, URLError, TimeoutError, ValueError):
                    time.sleep(0.25)
            else:
                return SmokeResult(
                    ok=False,
                    detail=f"Servo WebDriver did not become ready; log: {log_path}",
                )

            created = _request(
                f"{webdriver}/session",
                method="POST",
                payload={"capabilities": {"alwaysMatch": {"browserName": "servo"}}},
            )
            value = _webdriver_value(created)
            value_object = _as_object(value)
            session_id_value = value_object.get("sessionId") if value_object is not None else None
            if not isinstance(session_id_value, str):
                raise RuntimeError(f"WebDriver did not return a session id: {created}")
            session_id = session_id_value
            base = f"{webdriver}/session/{session_id}"
            _request(f"{base}/url", method="POST", payload={"url": page_url})
            deadline = time.monotonic() + 30
            diagnostics: dict[str, object] | None = None
            while time.monotonic() < deadline:
                try:
                    result = _webdriver_value(
                        _request(
                            f"{base}/execute/sync",
                            method="POST",
                            payload={
                                "script": "return window.__dashboard ?? null;",
                                "args": [],
                            },
                        )
                    )
                    result_object = _as_object(result)
                    if result_object is not None:
                        diagnostics = result_object
                        break
                except (OSError, RuntimeError, URLError, ValueError):
                    pass
                time.sleep(0.25)
            if diagnostics is None:
                raise RuntimeError("generated dashboard did not initialize in Servo")
            rendered = _webdriver_value(
                _request(
                    f"{base}/execute/sync",
                    method="POST",
                    payload={
                        "script": "return document.querySelector('h1')?.textContent ?? null;",
                        "args": [],
                    },
                )
            )
            if rendered != app.name:
                raise RuntimeError(f"Servo rendered unexpected dashboard heading: {rendered}")
            capabilities = _as_object(diagnostics.get("capabilities"))
            if capabilities is None:
                raise RuntimeError("dashboard diagnostics do not expose capabilities")
            hardware_apis = ("web_bluetooth", "webusb", "web_serial")
            available = [name for name in hardware_apis if capabilities.get(name) is True]
            if available:
                raise RuntimeError(
                    f"Servo unexpectedly exposed hardware APIs: {', '.join(available)}"
                )
            if capabilities.get("websocket") is not True:
                raise RuntimeError("Servo did not expose WebSocket")
            routes = _as_object(diagnostics.get("routes"))
            if routes is None:
                raise RuntimeError("dashboard diagnostics do not expose route selection")
            usable = _as_array(routes.get("usable"))
            if usable is None or not any(_has_route_kind(route, "websocket") for route in usable):
                raise RuntimeError("Servo did not expose a usable WebSocket route")
            unavailable = _as_array(routes.get("unavailable"))
            if unavailable is None or not all(
                any(_has_route_kind(route, kind) for route in unavailable)
                for kind in ("web_bluetooth", "web_serial")
            ):
                raise RuntimeError("Servo did not report its hardware routes as unavailable")
            buttons = _as_array(
                _webdriver_value(
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
                    )
                )
            )
            if buttons is None or not any(
                isinstance(label, str) and "websocket" in label.lower() for label in buttons
            ):
                raise RuntimeError("Servo dashboard UI does not show the WebSocket route")
            if any(
                isinstance(label, str)
                and any(kind in label.lower() for kind in ("bluetooth", "webusb", "serial"))
                for label in buttons
            ):
                raise RuntimeError("Servo dashboard UI exposed an unavailable hardware route")
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
            return SmokeResult(ok=False, detail=f"{exc}; log: {log_path}")
        finally:
            if session_id:
                with suppress(OSError, URLError, TimeoutError, ValueError):
                    _request(
                        f"http://127.0.0.1:{webdriver_port}/session/{session_id}",
                        method="DELETE",
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
