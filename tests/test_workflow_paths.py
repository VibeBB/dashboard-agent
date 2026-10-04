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
    assert ci.count("ref: ${{ inputs.ref || github.sha }}") == ci.count("uses: actions/checkout")


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
    assert "needs: [bump-version, install-smoke]" in release
    assert "--repo VibeBB/dashboard-agent" in release
    assert "--repo-path plugins/dashboard" in release


def test_publish_dispatch_builds_without_publishing() -> None:
    publish = (ROOT / ".github/workflows/publish-dashboard-images.yml").read_text(encoding="utf-8")
    assert "push: ${{ github.event_name == 'push' }}" in publish
    gated_steps = [
        "Scan tools image (Trivy JSON)",
        "Scan tools image (Trivy SARIF)",
        "Promote :latest",
        "Attest dashboard tools image provenance",
        "Generate tools SPDX SBOM",
        "Attest tools SBOM",
        "Measure published tools",
        "Smoke published tools through the launcher",
        "Update digest lock and merge PR",
    ]
    for step_name in gated_steps:
        block = publish.split(f"- name: {step_name}", 1)[1].split("\n      - name:", 1)[0]
        assert "if: github.event_name == 'push'" in block, step_name


def test_sweep_reports_merge_decisions_and_dispatches_audit() -> None:
    sweep = (ROOT / ".github/workflows/digest-lock-sweep.yml").read_text(encoding="utf-8")
    assert "dry_run:" in sweep
    assert "clean|blocked|behind|unstable" in sweep
    assert "container-audit.yml" in sweep


def test_container_audit_reruns_when_its_inputs_change() -> None:
    audit = (ROOT / ".github/workflows/container-audit.yml").read_text(encoding="utf-8")
    assert '".github/workflows/container-audit.yml"' in audit
    assert '".trivyignore"' in audit
    assert '"docker/image-digests.json"' in audit
    assert "container_hardening_report.py" in audit
    assert "--check-cis" in audit


def test_main_failure_report_tracks_default_branch_workflows() -> None:
    workflow = (ROOT / ".github/workflows/main-ci-failure-issue.yml").read_text(encoding="utf-8")
    assert '- "Container hardening audit"' in workflow
    assert "- Digest lock PR sweep" in workflow
    assert "- Workflow lint" in workflow
    assert "- PR branch cleanup" in workflow
    assert "actions: read # reads the completed run's jobs" in workflow


def test_image_smokes_use_ci_runners_and_upload_diagnostics() -> None:
    publish = (ROOT / ".github/workflows/publish-dashboard-images.yml").read_text(encoding="utf-8")
    locked = (ROOT / ".github/workflows/locked-image-check.yml").read_text(encoding="utf-8")
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert publish.count("runs-on: ubuntu-26.04") == 1
    assert locked.count("runs-on: ubuntu-26.04") == 2
    for workflow in (publish, locked):
        assert "set +e" in workflow
        assert "status=$?" in workflow
        assert "diagnostics_status" in workflow
        assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
        assert "if: always()" in workflow
    for workflow in (publish, locked, ci):
        assert "examples/*/out/*.dash-report.json" in workflow
        assert "examples/*/out/*.stdout.json" in workflow
        assert "examples/*/out/*.servo-smoke.log" in workflow
        assert "examples/*/out/*.screens/**" in workflow


def test_ci_prints_gate_report_before_enforcing_gate_status() -> None:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    start = ci.index("- name: Full gates in the image")
    end = ci.index("- name: Upload reports", start)
    step = ci[start:end]

    assert 'if python3 "$launcher" gates "$contract"' in step
    assert "gate_status=$?" in step
    assert 'python3 - "$out/$design.dash-report.json"' in step
    assert "Dashboard gate report unavailable" in step
    assert step.index('python3 - "$out/$design.dash-report.json"') < step.index(
        'if [ "$gate_status" -ne 0 ]'
    )
