from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "plugins/dashboard/app"
MANIFEST_PATH = APP / "canvas-extension.json"
ENTRYPOINT_PATH = APP / "extension.js"

KEBAB_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
PAGE_PATH = re.compile(r"^/[a-z0-9]+(?:-[a-z0-9]+)*(/[a-z0-9]+)*$")


def _manifest() -> Any:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_canvas_manifest_schema_1_shape() -> None:
    manifest = _manifest()
    assert manifest["schema_version"] == 1
    assert KEBAB_NAME.match(manifest["name"])
    assert manifest["display_name"]
    assert SEMVER.match(manifest["version"])
    assert manifest["description"]
    assert manifest["entrypoint"] == "extension.js"
    assert manifest["icon"].endswith(".svg")


def test_canvas_manifest_pages_contribution() -> None:
    manifest = _manifest()
    pages = manifest["contributes"]["pages"]
    assert len(pages) == len({page["id"] for page in pages}) >= 1
    for page in pages:
        assert KEBAB_NAME.match(page["id"])
        assert PAGE_PATH.match(page["path"])
        assert page["title"]
        assert page["nav_label"]


def test_canvas_manifest_paths_stay_inside_app() -> None:
    manifest = _manifest()
    for key in ("entrypoint", "icon"):
        relative = manifest[key]
        assert not relative.startswith("/")
        assert ".." not in Path(relative).parts
        assert (APP / relative).resolve().is_relative_to(APP.resolve())
        assert (APP / relative).is_file()


def test_canvas_entrypoint_is_static_esm() -> None:
    source = ENTRYPOINT_PATH.read_text(encoding="utf-8")
    assert "export function activate" in source
    assert not re.search(r"\bimport\s*\(", source)  # no dynamic imports
    assert not re.search(r"\brequire\s*\(", source)  # no CommonJS
    for specifier in re.findall(r"(?:from|import)\s+[\"']([^\"']+)[\"']", source):
        assert specifier.startswith("./") or specifier.startswith("../")


def test_canvas_registered_pages_match_manifest() -> None:
    manifest = _manifest()
    declared = {page["id"] for page in manifest["contributes"]["pages"]}
    source = ENTRYPOINT_PATH.read_text(encoding="utf-8")
    registered = set(re.findall(r"registerPage\(\s*[\"']([a-z0-9-]+)[\"']", source))
    if re.search(r"registerPage\(\s*PAGE_ID", source):
        match = re.search(r'const PAGE_ID = "([a-z0-9-]+)"', source)
        assert match
        registered.add(match.group(1))
    assert registered
    assert registered <= declared


def test_canvas_app_package_is_esm() -> None:
    package = json.loads((APP / "package.json").read_text(encoding="utf-8"))
    assert package["type"] == "module"
    assert package["private"] is True
