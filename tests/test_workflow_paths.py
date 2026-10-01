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


def test_publisher_retriggers_when_its_workflow_changes() -> None:
    publish = ROOT / ".github/workflows/publish-dashboard-images.yml"
    text = publish.read_text(encoding="utf-8")
    assert '".github/workflows/publish-dashboard-images.yml"' in text


def test_all_workflows_use_dashboard_runner_label() -> None:
    assert all("ubuntu-24.04" not in path.read_text(encoding="utf-8") for path in WORKFLOWS)


def test_release_lints_version_bump_and_install_smokes_plugin() -> None:
    release = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "workflow-lint.yml" in release
    assert "install-smoke:" in release
    assert "needs: [bump-version, verify, install-smoke]" in release
    assert "--repo VibeBB/dashboard-agent" in release
    assert "--repo-path plugins/dashboard" in release


def test_main_failure_report_tracks_default_branch_workflows() -> None:
    workflow = (ROOT / ".github/workflows/main-ci-failure-issue.yml").read_text(encoding="utf-8")
    assert "- Digest lock PR sweep" in workflow
    assert "- Workflow lint" in workflow
    assert "- PR branch cleanup" in workflow
    assert "actions: read # reads the completed run's jobs" in workflow


def test_image_smokes_use_ci_runners_and_upload_diagnostics() -> None:
    publish = (ROOT / ".github/workflows/publish-dashboard-images.yml").read_text(encoding="utf-8")
    locked = (ROOT / ".github/workflows/locked-image-check.yml").read_text(encoding="utf-8")

    assert publish.count("runs-on: ubuntu-26.04") == 1
    assert locked.count("runs-on: ubuntu-26.04") == 2
    for workflow in (publish, locked):
        assert "set +e" in workflow
        assert "status=$?" in workflow
        assert "diagnostics_status" in workflow
        assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
        assert "if: always()" in workflow
        assert "examples/*/out/*.dash-report.json" in workflow
        assert "examples/*/out/*.stdout.json" in workflow
        assert "examples/*/out/*.servo-smoke.log" in workflow
        assert "examples/*/out/*.screens/**" in workflow
