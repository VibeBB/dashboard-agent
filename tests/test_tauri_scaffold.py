from __future__ import annotations

import json
import re
import struct
import tomllib
from pathlib import Path
from typing import Any, cast

from plugins.dashboard.hooks.scripts.protect_generated import is_protected

from dashboard.contract import DashboardContract, load_contract
from dashboard.generate import build_tauri_scaffold, manifest_file_hashes, write_artifacts
from dashboard.interchange import sha256_file

ROOT = Path(__file__).resolve().parents[1]
KETTLE = ROOT / "examples/smart-kettle/smart-kettle.dash.json"
BENCH = ROOT / "examples/bench-meter/bench-meter.dash.json"


def _websocket_only_contract() -> DashboardContract:
    contract = load_contract(KETTLE)
    value: dict[str, Any] = contract.model_dump(mode="json")
    websocket = next(
        transport for transport in value["transports"] if transport["kind"] == "websocket"
    )
    value["transports"] = [websocket]
    platforms: list[dict[str, Any]] = []
    for platform in value["platforms"]:
        routes = [route for route in platform["routes"] if route["transport"] == websocket["id"]]
        if platform["status"] == "unsupported" or routes:
            platforms.append({**platform, "routes": routes})
    value["platforms"] = platforms
    return DashboardContract.model_validate(value)


def test_smart_kettle_tauri_scaffold_is_pinned_complete_and_deterministic() -> None:
    contract = load_contract(KETTLE)
    first = build_tauri_scaffold(contract)
    second = build_tauri_scaffold(contract)

    assert set(first) == {
        "README.md",
        "package.json",
        "src/bridge.ts",
        "scripts/prepare-web.mjs",
        "rust-toolchain.toml",
        "src-tauri/Cargo.toml",
        "src-tauri/build.rs",
        "src-tauri/icons/icon.ico",
        "src-tauri/icons/icon.png",
        "src-tauri/src/main.rs",
        "src-tauri/src/lib.rs",
        "src-tauri/tauri.conf.json",
        "src-tauri/capabilities/default.json",
        "src-tauri/Info.ios.plist",
    }
    assert first == second

    package = json.loads(first["package.json"])
    assert package["private"] is True
    assert package["type"] == "module"
    assert package["scripts"] == {
        "build:web": "node scripts/prepare-web.mjs",
        "tauri": "tauri",
    }
    assert package["dependencies"] == {
        "@mnlphlp/plugin-blec": "0.17.0",
        "@tauri-apps/api": "2.11.1",
        "tauri-plugin-serialplugin-api": "3.0.7",
    }
    assert package["devDependencies"] == {
        "@tauri-apps/cli": "2.11.5",
        "esbuild": "0.28.2",
    }

    cargo = tomllib.loads(first["src-tauri/Cargo.toml"].decode())
    assert cargo["dependencies"] == {
        "tauri": {"version": "=2.11.6"},
        "tauri-runtime": {"version": "=2.11.3"},
        "tauri-runtime-wry": {"version": "=2.11.4"},
        "tauri-macros": {"version": "=2.6.3"},
        "tauri-plugin-blec": {"version": "=0.17.0"},
        "tauri-plugin-serialplugin": {"version": "=3.0.7"},
    }
    assert cargo["build-dependencies"] == {"tauri-build": {"version": "=2.6.3"}}
    assert cargo["lib"]["crate-type"] == ["staticlib", "cdylib", "rlib"]
    assert first["rust-toolchain.toml"] == b'[toolchain]\nchannel = "1.98.1"\n'

    capabilities = json.loads(first["src-tauri/capabilities/default.json"])
    assert capabilities["windows"] == ["main"]
    assert capabilities["permissions"] == [
        "core:default",
        "blec:default",
        "serialplugin:default",
    ]
    assert "NSBluetoothAlwaysUsageDescription" in first["src-tauri/Info.ios.plist"].decode()
    assert "plugin-blec" in first["src/bridge.ts"].decode()
    assert "serialplugin-api" in first["src/bridge.ts"].decode()
    assert is_protected("out/smart-kettle/tauri/src-tauri/Cargo.toml")


def test_tauri_placeholder_icons_are_valid_and_deterministic() -> None:
    contract = load_contract(KETTLE)
    first = build_tauri_scaffold(contract)
    second = build_tauri_scaffold(contract)
    png = first["src-tauri/icons/icon.png"]
    ico = first["src-tauri/icons/icon.ico"]

    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">I", png[8:12])[0] == 13
    assert png[12:16] == b"IHDR"
    assert struct.unpack(">II", png[16:24]) == (32, 32)
    assert struct.unpack("<HHH", ico[:6]) == (0, 1, 1)
    width, height, color_count, reserved, planes, bit_depth, size, offset = struct.unpack(
        "<BBBBHHII", ico[6:22]
    )
    assert (width, height, color_count, reserved, planes, bit_depth) == (32, 32, 0, 0, 1, 32)
    assert (size, offset) == (len(png), 22)
    assert ico[offset:] == png
    assert png == second["src-tauri/icons/icon.png"]
    assert ico == second["src-tauri/icons/icon.ico"]


def test_websocket_only_tauri_scaffold_omits_native_plugins() -> None:
    files = build_tauri_scaffold(_websocket_only_contract())
    package = json.loads(files["package.json"])
    cargo = tomllib.loads(files["src-tauri/Cargo.toml"].decode())
    capabilities = json.loads(files["src-tauri/capabilities/default.json"])
    bridge = files["src/bridge.ts"].decode()

    assert package["dependencies"] == {"@tauri-apps/api": "2.11.1"}
    assert set(cargo["dependencies"]) == {
        "tauri",
        "tauri-runtime",
        "tauri-runtime-wry",
        "tauri-macros",
    }
    assert capabilities["permissions"] == ["core:default"]
    assert "blec:default" not in bridge
    assert "serialplugin-api" not in bridge
    assert "src-tauri/Info.ios.plist" not in files


def test_contract_without_tauri_shell_has_no_scaffold_files() -> None:
    assert build_tauri_scaffold(load_contract(BENCH)) == {}


def test_manifest_hashes_nested_scaffold_paths(tmp_path: Path) -> None:
    artifact = tmp_path / "tauri/src-tauri/Cargo.toml"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"[package]\n")
    dashboard = tmp_path / "dashboard.js"
    dashboard.write_bytes(b"bundle")
    unrelated = tmp_path / "tauri/node_modules/x"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_bytes(b"not generated")

    assert manifest_file_hashes(tmp_path, ["tauri/src-tauri/Cargo.toml"]) == {
        "dashboard.js": sha256_file(dashboard),
        "tauri/src-tauri/Cargo.toml": sha256_file(artifact),
    }


def test_write_artifacts_preserves_user_state_and_hashes_only_written_files(
    tmp_path: Path,
) -> None:
    output = tmp_path / "app"
    user_files = {
        "tauri/node_modules/x": b"node module",
        "tauri/dist/x": b"build output",
        "tauri/src-tauri/target/x": b"rust target",
        "tauri/src-tauri/gen/android/x": b"android project",
    }
    for name, content in user_files.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    artifacts = {"index.html": b"new dashboard", "tauri/package.json": b"{}"}
    write_artifacts(output, artifacts, ["index.html"])
    (output / "dashboard.js").write_bytes(b"bundle")

    for name, content in user_files.items():
        assert (output / name).read_bytes() == content
    assert set(manifest_file_hashes(output, artifacts)) == {
        "dashboard.js",
        *artifacts,
    }


def test_write_artifacts_removes_stale_ble_plist_for_shell_without_ble(
    tmp_path: Path,
) -> None:
    output = tmp_path / "app"
    stale_name = "tauri/src-tauri/Info.ios.plist"
    stale_plist = output / stale_name
    stale_plist.parent.mkdir(parents=True)
    stale_plist.write_text("old BLE usage description", encoding="utf-8")
    artifacts = {
        f"tauri/{name}": content
        for name, content in build_tauri_scaffold(_websocket_only_contract()).items()
    }

    write_artifacts(output, artifacts, [stale_name])

    assert not stale_plist.exists()


def test_write_artifacts_ignores_previous_manifest_path_traversal(
    tmp_path: Path,
) -> None:
    output = tmp_path / "app"
    output.mkdir()
    escaped = tmp_path / "escape"
    escaped.write_text("keep", encoding="utf-8")

    write_artifacts(output, {}, ["../escape"])

    assert escaped.read_text(encoding="utf-8") == "keep"


def test_tauri_config_matches_contract_and_allows_only_local_ipc_http_url() -> None:
    contract = load_contract(KETTLE)
    assert contract.shell is not None and contract.shell.tauri is not None
    files = build_tauri_scaffold(contract)
    config = json.loads(files["src-tauri/tauri.conf.json"])
    csp = cast(str, config["app"]["security"]["csp"])

    assert config["identifier"] == contract.shell.tauri.identifier
    assert config["version"] == contract.shell.tauri.version
    assert config["productName"] == contract.shell.tauri.product_name
    assert config["build"]["frontendDist"] == "../dist"
    assert "devUrl" not in config["build"]
    assert config["app"]["windows"] == [
        {
            "label": "main",
            "title": contract.shell.tauri.product_name,
            "width": 1280,
            "height": 800,
        }
    ]
    assert re.findall(r"https?://[^\s\";]+", files["src-tauri/tauri.conf.json"].decode()) == [
        "http://ipc.localhost"
    ]
    assert "ipc:" in csp
