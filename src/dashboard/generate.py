"""Deterministic static dashboard projection."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import __version__
from .contract import (
    DashboardContract,
    WebRtcTransport,
    WebSocketTransport,
    load_contract,
)
from .interchange import sha256_file
from .matrix import CAVEATS, route_caveats, route_support
from .protocol import protocol_export
from .webmcp import definitions


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _protocol_header(contract: DashboardContract) -> str:
    lines = [
        "#ifndef DASH_PROTOCOL_H",
        "#define DASH_PROTOCOL_H",
        "#include <stdint.h>",
        '#include "dash_codec.h"',
        "",
        f"#define DASH_MAX_FRAME_BYTES {contract.protocol.max_frame_bytes}u",
    ]
    for message in contract.protocol.messages:
        prefix = f"DASH_{message.name.upper()}"
        lines.append(f"#define {prefix}_ID {message.id}u")
        field_sizes = [
            1 if field.type in ("u8", "i8", "bool") else 2 if field.type in ("u16", "i16") else 4
            for field in message.fields
        ]
        lines.append(f"#define {prefix}_PAYLOAD_BYTES {sum(field_sizes)}u")
        for index, field in enumerate(message.fields):
            lines.append(
                f"/* {message.name}.{field.name}: offset {sum(field_sizes[:index])}, "
                f"{field.type} */"
            )
    lines.extend(["", "#endif", ""])
    return "\n".join(lines)


def _config(contract: DashboardContract, contract_sha256: str) -> dict[str, object]:
    routes: list[dict[str, object]] = []
    by_id = {transport.id: transport for transport in contract.transports}
    for platform in contract.platforms:
        for route in platform.routes:
            transport = by_id[route.transport]
            url = (
                transport.url
                if isinstance(transport, WebSocketTransport)
                else transport.signaling_url
                if isinstance(transport, WebRtcTransport)
                else None
            )
            support = route_support(platform.os, route.browser, transport.kind)
            routes.append(
                {
                    "os": platform.os,
                    "browser": route.browser,
                    "transport": route.transport,
                    "kind": transport.kind,
                    "support": support[0] if support else "no",
                    "caveats": route_caveats(platform.os, route.browser, transport.kind, url),
                    "caveat_text": {
                        caveat: CAVEATS[caveat]
                        for caveat in route_caveats(platform.os, route.browser, transport.kind, url)
                    },
                }
            )
    return {
        "contract_sha256": contract_sha256,
        "contract": contract.model_dump(mode="json", exclude={"shell"}),
        "routes": routes,
        "webmcp_tools": definitions(contract),
    }


def _html(contract: DashboardContract) -> str:
    connect_hosts = {"'self'"}
    for transport in contract.transports:
        url = (
            transport.url
            if isinstance(transport, WebSocketTransport)
            else transport.signaling_url
            if isinstance(transport, WebRtcTransport)
            else None
        )
        if url:
            parsed = urlsplit(url)
            if parsed.scheme in {"ws", "wss"} and parsed.netloc:
                connect_hosts.add(f"{parsed.scheme}://{parsed.netloc}")
    connect_policy = " ".join(sorted(connect_hosts))
    token = (
        f'<meta http-equiv="origin-trial" content="{contract.webmcp.origin_trial_token}">\n'
        if contract.webmcp and contract.webmcp.origin_trial_token
        else ""
    )
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta http-equiv="Content-Security-Policy" content="default-src \'self\'; '
        f"connect-src {connect_policy}; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; object-src 'none'; base-uri 'none'\">\n"
        f"{token}"
        f"<title>{contract.name}</title>\n"
        '<link rel="manifest" href="manifest.webmanifest">\n'
        '<link rel="stylesheet" href="styles.css">\n'
        '</head>\n<body>\n<main id="dashboard" aria-live="polite">\n'
        f'<h1>{contract.name}</h1>\n<div id="platform-banner"></div>\n'
        '<section id="connection-panel" aria-label="Connection"></section>\n'
        '<section id="caveat-notices" aria-label="Compatibility notices"></section>\n'
        '<section id="widgets" aria-label="Dashboard controls"></section>\n'
        '<details><summary>Diagnostics</summary><pre id="diagnostics"></pre></details>\n'
        '</main>\n<script type="module" src="dashboard.js"></script>\n</body>\n</html>\n'
    )


def generate(contract_path: Path, out_root: Path) -> tuple[Path, list[Path]]:
    contract_path = contract_path.resolve()
    contract = load_contract(contract_path)
    contract_sha = sha256_file(contract_path)
    output = out_root.resolve() / contract.name
    output.mkdir(parents=True, exist_ok=True)
    source_root = Path(__file__).resolve().parents[2]
    artifacts: dict[str, bytes] = {
        "index.html": _html(contract).encode(),
        "dashboard.config.json": _json(_config(contract, contract_sha)).encode(),
        "manifest.webmanifest": _json(
            {
                "name": contract.name,
                "short_name": contract.name[:12],
                "start_url": "./",
                "display": "standalone",
                "background_color": "#101820",
                "theme_color": "#15252b",
            }
        ).encode(),
        "styles.css": (
            b":root{color-scheme:dark;font:16px system-ui;background:#101820;color:#eef4f4}"
            b"body{margin:0;padding:1rem}main{max-width:72rem;margin:auto}"
            b"section{display:grid;gap:1rem;margin:1rem 0}button,input{font:inherit;padding:.7rem}"
            b".notice,[role=alert]{border:1px solid #f0b35b;padding:.8rem}"
            b".widget{border:1px solid #53666e;padding:1rem;border-radius:.5rem}"
            b"#platform-banner.unsupported{position:fixed;inset:0;z-index:1000;display:grid;"
            b"place-content:center;padding:2rem;background:#301417;color:#fff;font-size:1.5rem;"
            b"text-align:center}"
            b"button:focus-visible,input:focus-visible{outline:3px solid "
            b"#70d6c7;outline-offset:2px}"
            b"canvas{max-width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere}"
        ),
        f"{contract.name}.dash-protocol.h": _protocol_header(contract).encode(),
        f"{contract.name}.dash-protocol.json": _json(
            protocol_export(contract, contract_sha)
        ).encode(),
        f"{contract.name}.dash-webmcp.json": _json(
            {
                "schema_version": 1,
                "system": "dashboard",
                "artifact_kind": "dashboard_webmcp_tools",
                "contract_sha256": contract_sha,
                "tools": definitions(contract),
            }
        ).encode(),
        "dash_codec.c": (source_root / "runtime/c/dash_codec.c").read_bytes(),
        "dash_codec.h": (source_root / "runtime/c/dash_codec.h").read_bytes(),
    }
    for name, content in artifacts.items():
        (output / name).write_bytes(content)
    esbuild = source_root / "runtime/node_modules/.bin/esbuild"
    command = str(esbuild) if esbuild.is_file() else shutil.which("esbuild")
    if command is None:
        raise RuntimeError("esbuild not found; install runtime dependencies before generating")
    result = subprocess.run(
        [
            command,
            "runtime/src/main.ts",
            "--bundle",
            "--format=esm",
            "--target=es2022",
            "--minify=false",
            f"--outfile={output / 'dashboard.js'}",
        ],
        cwd=source_root,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise RuntimeError((result.stdout + result.stderr).strip() or "esbuild failed")
    files: dict[str, str] = {
        path.name: sha256_file(path)
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != "dash-manifest.json"
    }
    manifest: dict[str, Any] = {
        "contract_sha256": contract_sha,
        "generator_version": __version__,
        "files": files,
    }
    manifest_path = output / "dash-manifest.json"
    manifest_path.write_text(_json(manifest), encoding="utf-8")
    return output, [*(output / name for name in files), manifest_path]
