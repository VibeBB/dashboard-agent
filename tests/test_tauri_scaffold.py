from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any, cast

from plugins.dashboard.hooks.scripts.protect_generated import is_protected

from dashboard.contract import DashboardContract, load_contract
from dashboard.generate import build_tauri_scaffold, manifest_file_hashes
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


def test_websocket_only_tauri_scaffold_omits_native_plugins() -> None:
    files = build_tauri_scaffold(_websocket_only_contract())
    package = json.loads(files["package.json"])
    cargo = tomllib.loads(files["src-tauri/Cargo.toml"].decode())
    capabilities = json.loads(files["src-tauri/capabilities/default.json"])
    bridge = files["src/bridge.ts"].decode()

    assert package["dependencies"] == {"@tauri-apps/api": "2.11.1"}
    assert set(cargo["dependencies"]) == {"tauri"}
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

    assert manifest_file_hashes(tmp_path) == {"tauri/src-tauri/Cargo.toml": sha256_file(artifact)}


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
