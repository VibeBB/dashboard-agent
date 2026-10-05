"""Deterministic static dashboard projection."""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
import zlib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

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


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    chunk = kind + data
    return struct.pack(">I", len(data)) + chunk + struct.pack(">I", zlib.crc32(chunk))


def _placeholder_icon_png() -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    header = struct.pack(">IIBBBBB", 32, 32, 8, 6, 0, 0, 0)
    pixel = bytes((47, 111, 237, 255))
    image_data = zlib.compress(b"".join(b"\x00" + pixel * 32 for _ in range(32)), level=9)
    return (
        signature
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", image_data)
        + _png_chunk(b"IEND", b"")
    )


def _placeholder_icon_ico(png: bytes) -> bytes:
    directory = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 32, 32, 0, 0, 1, 32, len(png), 22)
    return directory + entry + png


def manifest_file_hashes(output: Path, names: Iterable[str]) -> dict[str, str]:
    artifact_names = sorted(set(names) | {"dashboard.js"})
    return {name: sha256_file(output / name) for name in artifact_names}


def _resolves_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return False
    return True


def write_artifacts(
    output: Path,
    artifacts: Mapping[str, bytes],
    previous_names: Iterable[str],
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    output_root = output.resolve()
    current_names = set(artifacts) | {"dashboard.js", "dash-manifest.json"}
    for name in sorted(set(previous_names) - current_names):
        artifact_path = output / name
        if (
            _resolves_within(artifact_path, output_root)
            and not artifact_path.is_dir()
            and (artifact_path.exists() or artifact_path.is_symlink())
        ):
            artifact_path.unlink()
    for name, content in artifacts.items():
        artifact_path = output / name
        if not _resolves_within(artifact_path, output_root):
            raise ValueError(f"generated artifact path escapes output: {name}")
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(content)


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


def build_config(contract: DashboardContract, contract_sha256: str) -> dict[str, object]:
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


def _connect_sources(contract: DashboardContract, *, include_tauri_ipc: bool = False) -> str:
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
    if include_tauri_ipc:
        connect_hosts.update({"ipc:", "http://ipc.localhost"})
    return " ".join(sorted(connect_hosts))


def _content_security_policy(
    contract: DashboardContract, *, include_tauri_ipc: bool = False
) -> str:
    return (
        "default-src 'self'; "
        f"connect-src {_connect_sources(contract, include_tauri_ipc=include_tauri_ipc)}; "
        "script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "object-src 'none'; base-uri 'none'"
    )


def _tauri_bridge(*, has_ble: bool, has_serial: bool) -> str:
    lines: list[str] = []
    if has_ble:
        lines.extend(
            [
                "import {",
                "  checkPermissions as checkBlePermissions,",
                "  connect as connectBleDevice,",
                "  disconnect as disconnectBle,",
                "  send as sendBleData,",
                "  startScan as startBleScan,",
                "  stopScan as stopBleScan,",
                "  subscribe as subscribeBle,",
                "  unsubscribe as unsubscribeBle,",
                '} from "@mnlphlp/plugin-blec";',
                "",
            ]
        )
    if has_serial:
        lines.extend(
            [
                'import { SerialPort as SerialPluginPort } from "tauri-plugin-serialplugin-api";',
                "",
            ]
        )
    lines.extend(
        [
            "type TauriBleDevice = {",
            "  address: string;",
            "  name: string;",
            "  services: string[];",
            "};",
            "",
            "type TauriBleBackend = {",
            "  checkPermissions(askIfDenied?: boolean): Promise<boolean>;",
            "  startScan(",
            "    handler: (devices: TauriBleDevice[]) => void,",
            "    timeout: number,",
            "  ): Promise<void>;",
            "  stopScan(): Promise<void>;",
            "  connect(address: string, onDisconnect: (() => void) | null): Promise<void>;",
            "  disconnect(): Promise<void>;",
            "  subscribe(",
            "    characteristic: string,",
            "    service: string | null,",
            "    handler: (data: number[]) => void,",
            "  ): Promise<void>;",
            "  unsubscribe(characteristic: string, service?: string): Promise<void>;",
            "  send(",
            "    characteristic: string,",
            "    data: number[],",
            '    writeType?: "withResponse" | "withoutResponse",',
            "    service?: string,",
            "  ): Promise<void>;",
            "};",
            "",
            "type TauriPortInfo = {",
            "  path: string;",
            "  manufacturer: string;",
            "  pid: string;",
            "  product: string;",
            "  serial_number: string;",
            "  type: string;",
            "  vid: string;",
            "};",
            "",
            "type TauriSerialPort = {",
            "  open(): Promise<string>;",
            "  watch(",
            "    handlers: {",
            "      onData: (data: string | Uint8Array) => void;",
            "      onDisconnect?: (reason: string) => void;",
            "      onError?: (message: string) => void;",
            "    },",
            "    options?: { decode?: boolean },",
            "  ): Promise<{ unwatch(): Promise<void> }>;",
            "  close(): Promise<void>;",
            "  writeBinary(value: Uint8Array | number[]): Promise<number>;",
            "};",
            "",
            "type TauriBackends = {",
            "  ble?: TauriBleBackend;",
            "  serial?: {",
            "    SerialPort: {",
            "      new(options: { path: string; baudRate: number }): TauriSerialPort;",
            "      available_ports(): Promise<Record<string, TauriPortInfo>>;",
            "    };",
            "  };",
            "};",
            "",
            "declare global {",
            "  var __TAURI_BACKENDS__: TauriBackends | undefined;",
            "}",
            "",
            "const backends: TauriBackends = {};",
        ]
    )
    if has_ble:
        lines.extend(
            [
                "",
                "backends.ble = {",
                "  checkPermissions: checkBlePermissions,",
                "  startScan: (handler, timeout) => startBleScan(handler, timeout),",
                "  stopScan: stopBleScan,",
                "  connect: connectBleDevice,",
                "  disconnect: disconnectBle,",
                "  subscribe: subscribeBle,",
                "  unsubscribe: unsubscribeBle,",
                "  send: sendBleData,",
                "};",
            ]
        )
    if has_serial:
        lines.extend(
            [
                "",
                "backends.serial = { SerialPort: SerialPluginPort };",
            ]
        )
    lines.extend(["", "globalThis.__TAURI_BACKENDS__ = backends;", ""])
    return "\n".join(lines)


def _tauri_readme(contract: DashboardContract, *, has_serial: bool) -> str:
    assert contract.shell is not None and contract.shell.tauri is not None
    product_name = contract.shell.tauri.product_name
    serial_notes = (
        "\nFor Android serial, add your USB VID/PID to the app's `device_filter.xml` "
        "and request USB permission at runtime before opening a port.\n"
        if has_serial
        else ""
    )
    return (
        f"# {product_name}\n\n"
        f"This Tauri v2 shell was generated for `{contract.name}`. "
        "Regenerate it with `dashboard generate <contract>`.\n\n"
        "Files under `src-tauri/gen/` created by Tauri's Android or iOS init "
        "commands are user-owned and preserved on regeneration.\n\n"
        "## Prerequisites\n\n"
        "Install Node.js 26 and Rust. Follow the "
        "[official Tauri v2 prerequisites](https://v2.tauri.app/start/prerequisites/) "
        "for the selected target:\n\n"
        "- Windows: Microsoft C++ Build Tools and WebView2.\n"
        "- macOS: Xcode for iOS targets; desktop-only development can use "
        "Xcode Command Line Tools.\n"
        "- Linux: the distribution's Tauri system packages, including WebKitGTK.\n"
        "- Android: Android Studio, a Java JDK (`JAVA_HOME`), the Android "
        "SDK/NDK, and the required Rust target.\n"
        "- iOS: macOS and Xcode.\n\n"
        "## Desktop\n\n"
        "```bash\n"
        "npm install\n"
        "npx tauri dev\n"
        "npx tauri build\n"
        "```\n\n"
        "The included application icons are deterministic placeholders. Before creating bundles, "
        "replace them with branded icons using `npx tauri icon ./app-icon.png`. "
        "For a compile-only build, "
        "`npx tauri build --debug --no-bundle` skips bundling.\n\n"
        "## Mobile\n\n"
        "```bash\n"
        "npx tauri android init\n"
        "npx tauri android build\n"
        "npx tauri ios init\n"
        "npx tauri ios build\n"
        "```\n\n"
        "Apple builds require macOS and Xcode.\n"
        f"{serial_notes}\n"
        "Signing, notarization, store submission, and TestFlight are out of scope.\n"
    )


def build_tauri_scaffold(contract: DashboardContract) -> dict[str, bytes]:
    shell = contract.shell.tauri if contract.shell is not None else None
    if shell is None:
        return {}

    transport_kinds = {transport.kind for transport in contract.transports}
    has_ble = "tauri_ble" in transport_kinds
    has_serial = "tauri_serial" in transport_kinds
    dependencies: dict[str, str] = {"@tauri-apps/api": "2.11.1"}
    if has_ble:
        dependencies["@mnlphlp/plugin-blec"] = "0.17.0"
    if has_serial:
        dependencies["tauri-plugin-serialplugin-api"] = "3.0.7"
    package = {
        "name": contract.name,
        "version": shell.version,
        "private": True,
        "type": "module",
        "scripts": {
            "build:web": "node scripts/prepare-web.mjs",
            "tauri": "tauri",
        },
        "dependencies": dependencies,
        "devDependencies": {
            "@tauri-apps/cli": "2.11.5",
            "esbuild": "0.28.2",
        },
    }
    permissions = ["core:default"]
    if has_ble:
        permissions.append("blec:default")
    if has_serial:
        permissions.append("serialplugin:default")
    cargo_dependencies = [
        'tauri = { version = "=2.11.6" }',
        'tauri-runtime = { version = "=2.11.3" }',
        'tauri-runtime-wry = { version = "=2.11.4" }',
        'tauri-macros = { version = "=2.6.3" }',
    ]
    if has_ble:
        cargo_dependencies.append('tauri-plugin-blec = { version = "=0.17.0" }')
    if has_serial:
        cargo_dependencies.append('tauri-plugin-serialplugin = { version = "=3.0.7" }')
    crate_name = contract.name.replace("-", "_")
    if not crate_name[0].isalpha():
        crate_name = f"dashboard_{crate_name}"
    library_name = f"{crate_name}_lib"
    lib_lines = [
        "#[cfg_attr(mobile, tauri::mobile_entry_point)]",
        "pub fn run() {",
        "    let builder = tauri::Builder::default()",
    ]
    plugins: list[str] = []
    if has_ble:
        plugins.append("        .plugin(tauri_plugin_blec::init())")
    if has_serial:
        plugins.append("        .plugin(tauri_plugin_serialplugin::init())")
    if plugins:
        lib_lines.extend(plugins)
    lib_lines[-1] += ";"
    lib_lines.extend(
        [
            "",
            "    builder",
            "        .run(tauri::generate_context!())",
            '        .expect("error while running Tauri application");',
            "}",
            "",
        ]
    )
    icon_png = _placeholder_icon_png()
    files: dict[str, bytes] = {
        "README.md": _tauri_readme(contract, has_serial=has_serial).encode(),
        "package.json": _json(package).encode(),
        "src/bridge.ts": _tauri_bridge(has_ble=has_ble, has_serial=has_serial).encode(),
        "scripts/prepare-web.mjs": b"""import { build } from "esbuild";
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const source = resolve(root, "..");
const dist = resolve(root, "dist");
const files = [
  "dashboard.config.json",
  "dashboard.js",
  "index.html",
  "manifest.webmanifest",
  "styles.css",
];

await mkdir(dist, { recursive: true });
for (const file of files) {
  await copyFile(resolve(source, file), resolve(dist, file));
}
await build({
  entryPoints: [resolve(root, "src/bridge.ts")],
  bundle: true,
  format: "iife",
  target: "es2022",
  outfile: resolve(dist, "bridge.js"),
});
const indexPath = resolve(dist, "index.html");
const html = await readFile(indexPath, "utf8");
const dashboardTag = '<script type="module" src="dashboard.js"></script>';
if (html.split(dashboardTag).length - 1 !== 1) {
  throw new Error("expected exactly one dashboard module script tag");
}
await writeFile(
  indexPath,
  html.replace(dashboardTag, `<script src="bridge.js"></script>\\n${dashboardTag}`),
);
""",
        "rust-toolchain.toml": b'[toolchain]\nchannel = "1.98.1"\n',
        "src-tauri/Cargo.toml": (
            "[package]\n"
            f'name = "{contract.name}"\n'
            f'version = "{shell.version}"\n'
            'edition = "2021"\n'
            'build = "build.rs"\n'
            "\n"
            "[lib]\n"
            f'name = "{library_name}"\n'
            'crate-type = ["staticlib", "cdylib", "rlib"]\n'
            "\n"
            "[build-dependencies]\n"
            'tauri-build = { version = "=2.6.3" }\n'
            "\n"
            "[dependencies]\n" + "\n".join(cargo_dependencies) + "\n"
        ).encode(),
        "src-tauri/build.rs": b"fn main() {\n    tauri_build::build()\n}\n",
        "src-tauri/icons/icon.png": icon_png,
        "src-tauri/icons/icon.ico": _placeholder_icon_ico(icon_png),
        "src-tauri/src/main.rs": (
            '#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]\n'
            "\n"
            "fn main() {\n"
            f"    {library_name}::run();\n"
            "}\n"
        ).encode(),
        "src-tauri/src/lib.rs": "\n".join(lib_lines).encode(),
        "src-tauri/tauri.conf.json": _json(
            {
                "productName": shell.product_name,
                "version": shell.version,
                "identifier": shell.identifier,
                "build": {
                    "beforeBuildCommand": "npm run build:web",
                    "beforeDevCommand": "npm run build:web",
                    "frontendDist": "../dist",
                },
                "app": {
                    "windows": [
                        {
                            "label": "main",
                            "title": shell.product_name,
                            "width": 1280,
                            "height": 800,
                        }
                    ],
                    "security": {"csp": _content_security_policy(contract, include_tauri_ipc=True)},
                },
                "bundle": {"active": True, "targets": "all"},
            }
        ).encode(),
        "src-tauri/capabilities/default.json": _json(
            {
                "identifier": "default",
                "description": "Default dashboard window permissions",
                "windows": ["main"],
                "permissions": permissions,
            }
        ).encode(),
    }
    if has_ble:
        product_name = escape(shell.product_name)
        files["src-tauri/Info.ios.plist"] = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n'
            "<dict>\n"
            "<key>NSBluetoothAlwaysUsageDescription</key>\n"
            f"<string>{product_name} uses Bluetooth to connect to your device.</string>\n"
            "</dict>\n"
            "</plist>\n"
        ).encode()
    return files


def _html(contract: DashboardContract) -> str:
    has_tauri = contract.shell is not None and contract.shell.tauri is not None
    content_security_policy = _content_security_policy(contract, include_tauri_ipc=has_tauri)
    token = (
        f'<meta http-equiv="origin-trial" content="{contract.webmcp.origin_trial_token}">\n'
        if contract.webmcp and contract.webmcp.origin_trial_token
        else ""
    )
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{content_security_policy}">\n'
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
    manifest_path = output / "dash-manifest.json"
    previous_names: list[str] = []
    if manifest_path.is_file():
        previous_manifest: object = json.loads(manifest_path.read_text(encoding="utf-8"))
        previous_files = (
            cast(dict[str, object], previous_manifest).get("files")
            if isinstance(previous_manifest, dict)
            else None
        )
        if isinstance(previous_files, dict):
            previous_names = [
                name for name in cast(dict[object, object], previous_files) if isinstance(name, str)
            ]
    source_root = Path(__file__).resolve().parents[2]
    artifacts: dict[str, bytes] = {
        "index.html": _html(contract).encode(),
        "dashboard.config.json": _json(build_config(contract, contract_sha)).encode(),
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
            b".control{display:grid;gap:.35rem;margin:.75rem 0}"
            b".range-control{grid-template-columns:minmax(0,1fr) auto;align-items:center}"
            b".range-control label{grid-column:1/-1}.range-control input{width:100%;padding:0}"
            b".range-control output{display:block;min-width:5rem;text-align:right;"
            b"font-variant-numeric:tabular-nums}"
            b".widget.hazard{border:2px solid #ff8f70;box-shadow:0 0 0 1px #6b211b}"
            b".hazard-badge{margin:.5rem 0;padding:.4rem .65rem;border:1px solid #ffb39f;"
            b"border-radius:.35rem;background:#4a1916;color:#fff;font-weight:700}"
            b"button.hazard{background:#8f241b;border:2px solid #ffb39f;color:#fff;font-weight:700}"
            b"button.hazard:disabled{background:#3a2724;border-color:#7a5650;color:#b8a8a5;"
            b"cursor:not-allowed}"
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
    artifacts.update(
        {f"tauri/{name}": content for name, content in build_tauri_scaffold(contract).items()}
    )
    write_artifacts(output, artifacts, previous_names)
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
    files = manifest_file_hashes(output, artifacts)
    manifest: dict[str, Any] = {
        "contract_sha256": contract_sha,
        "generator_version": __version__,
        "files": files,
    }
    manifest_path.write_text(_json(manifest), encoding="utf-8")
    return output, [*(output / name for name in files), manifest_path]
