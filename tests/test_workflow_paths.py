from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github/workflows").glob("*.yml"))
PLUGIN_PATH = re.compile(r"plugins/dashboard/[\w\-/*{}.,]+")
GENERATED = {"plugins/dashboard/tools-image.json"}


def test_workflows_exist() -> None:
    assert WORKFLOWS


def test_plugin_paths_referenced_exist() -> None:
    missing: list[str] = []
    for workflow in WORKFLOWS:
        for literal in PLUGIN_PATH.findall(workflow.read_text(encoding="utf-8")):
            path = literal.rstrip(".,'\"")
            if path in GENERATED:
                continue
            if "*" in path:
                if not list(ROOT.glob(path)):
                    missing.append(f"{workflow.name}: {path}")
            elif not (ROOT / path).exists():
                missing.append(f"{workflow.name}: {path}")
    assert not missing, f"workflow references missing paths: {missing}"


def test_ci_is_dispatchable_and_reusable_with_a_ref() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "  workflow_dispatch:" in ci
    assert "  workflow_call:" in ci
    assert "      ref:" in ci
    assert ci.count("ref: ${{ inputs.ref || github.sha }}") == 3


def test_publisher_builds_the_locked_dashboard_image() -> None:
    publish = ROOT / ".github/workflows/publish-dashboard-images.yml"
    text = publish.read_text(encoding="utf-8")
    assert "docker/dashboard-tools.Dockerfile" in text
    assert "IMAGE_REVISION" in text
    assert "dashboard_tools" in text
    assert "plugins/dashboard/tools-image.json" in text
