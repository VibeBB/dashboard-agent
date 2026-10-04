from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
import scripts.check_dependency_updates as check_dependency_updates_module
from scripts.check_dependency_updates import (
    DependencyDeferral,
    DependencyStatus,
    apply_deferrals,
    check_dependency_updates,
    check_git_clones,
    check_workflow_downloads,
    load_deferrals,
    main,
    render_markdown,
)

ROOT = Path(__file__).resolve().parents[1]


def _fetch_json(url: str) -> object:
    if "pypi.org" in url:
        return {"info": {"version": "99.0.0"}}
    if "registry.npmjs.org" in url:
        return {"dist-tags": {"latest": "99.0.0", "next": "99.0.0"}}
    if "crates.io" in url:
        return {"crate": {"max_version": "99.0.0"}}
    if "servo/servo" in url:
        return {"tag_name": "v99.0.0"}
    return {}


def test_checker_covers_required_dependency_surfaces() -> None:
    statuses = check_dependency_updates(
        ROOT,
        fetch_json=_fetch_json,
        list_remote_tags=lambda _url: ["v99.0.0"],
        run_uv=lambda _command, _root: "Update transitive-lib v1.0.0 -> v2.0.0\n",
    )
    surfaces = {status.surface for status in statuses}

    assert {
        "pypi",
        "pypi-lock",
        "uv",
        "npm",
        "tauri-scaffold",
        "github-actions",
        "git-clone",
        "docker-base",
        "servo",
        "workflow-download",
    } <= surfaces
    assert any(status.name == "typescript" and status.surface == "npm" for status in statuses)
    assert any(status.name == "tauri" and status.surface == "tauri-scaffold" for status in statuses)
    assert any(
        status.name == "transitive-lib" and status.surface == "pypi-lock" for status in statuses
    )
    actions = {status.name for status in statuses if status.surface == "github-actions"}
    assert "github/codeql-action/upload-sarif" in actions
    downloads = {status.name for status in statuses if status.surface == "workflow-download"}
    assert {"rhysd/actionlint", "zizmor", "aquasecurity/trivy"} <= downloads


def test_current_dependency_deferrals_have_review_dates() -> None:
    deferrals = load_deferrals(ROOT)

    assert len(deferrals) == 4
    assert {item.review_by for item in deferrals} == {
        date(2026, 10, 7),
        date(2027, 1, 3),
        date(2027, 4, 1),
    }
    assert {item.name for item in deferrals} == {
        "*tauri*",
        "mcp",
        "emscripten/emsdk",
        "node",
    }
    mcp = next(item for item in deferrals if item.name == "mcp")
    assert mcp.latest == "2.3.0"
    assert "fastmcp>=3.2.0,<4" in mcp.reason


def test_deferrals_expire_back_into_update_candidates() -> None:
    status = DependencyStatus(
        "npm",
        "@types/node",
        "26.6.2",
        "26.6.3",
        "runtime/package.json",
        True,
    )
    deferral = DependencyDeferral(
        "npm",
        "@types/node",
        "26.6.3",
        date(2026, 10, 7),
        "scheduled review",
    )

    active = apply_deferrals([status], [deferral], date(2026, 10, 1))[0]
    expired = apply_deferrals([status], [deferral], date(2026, 10, 8))[0]

    assert active.deferred and not active.outdated
    assert expired.outdated and not expired.deferred


def test_nightly_deferral_matches_settled_build_series() -> None:
    status = DependencyStatus(
        "npm",
        "typescript",
        "7.1.0-dev.20260923.1",
        "7.1.0-dev.20260930.4",
        "runtime/package.json",
        True,
    )
    deferral = DependencyDeferral(
        "npm",
        "typescript",
        "7.1.0-dev.20260930.*",
        date(2026, 10, 7),
        "scheduled review",
    )

    active = apply_deferrals([status], [deferral], date(2026, 10, 1))[0]

    assert active.deferred and not active.outdated


def test_tauri_deferral_only_matches_tauri_scaffold_packages() -> None:
    deferrals = load_deferrals(ROOT)
    statuses = [
        DependencyStatus(
            "tauri-scaffold",
            "@tauri-apps/api",
            "2.12.0",
            "2.12.1",
            "src/dashboard/generate.py",
            True,
        ),
        DependencyStatus(
            "tauri-scaffold",
            "vite",
            "7.0.0",
            "8.0.0",
            "src/dashboard/generate.py",
            True,
        ),
    ]

    deferred = apply_deferrals(statuses, deferrals, date(2026, 10, 1))

    assert deferred[0].deferred and not deferred[0].outdated
    assert deferred[1].outdated and not deferred[1].deferred


def test_lynis_clone_pin_parsed() -> None:
    statuses = check_git_clones(ROOT, list_remote_tags=lambda _url: ["3.1.7"])

    lynis = next(status for status in statuses if status.name == "CISOfy/lynis")
    assert lynis.current == "3.1.7"
    assert lynis.latest == "3.1.7"
    assert lynis.outdated is False


def test_git_clones_report_outdated_and_fetch_failed() -> None:
    statuses = check_git_clones(ROOT, list_remote_tags=lambda _url: ["3.1.7", "3.2.0"])

    lynis = next(status for status in statuses if status.name == "CISOfy/lynis")
    assert lynis.latest == "3.2.0"
    assert lynis.outdated is True

    def failed_tags(url: str) -> list[str]:
        raise OSError(url)

    statuses = check_git_clones(ROOT, list_remote_tags=failed_tags)
    lynis = next(status for status in statuses if status.name == "CISOfy/lynis")
    assert lynis.latest == "?"
    assert lynis.fetch_failed is True
    assert lynis.outdated is False


def test_subpath_action_pins_track_the_parent_repo(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "lint.yml").write_text(
        "steps:\n"
        "  - uses: github/codeql-action/upload-sarif@"
        "2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2 # v4.38.2\n",
        encoding="utf-8",
    )
    seen: list[str] = []

    def remote_tags(url: str) -> list[str]:
        seen.append(url)
        return ["v4.38.2"]

    statuses = check_dependency_updates_module.check_action_pins(tmp_path, remote_tags)

    pin = next(status for status in statuses if status.name == "github/codeql-action/upload-sarif")
    assert pin.current == "v4.38.2"
    assert pin.latest == "v4.38.2"
    assert not pin.outdated
    assert seen == ["https://github.com/github/codeql-action.git"]


def test_workflow_download_pins_and_checksums(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "lint.yml").write_text(
        'tarball="actionlint_1.7.12_linux_amd64.tar.gz"\n'
        'curl "https://github.com/rhysd/actionlint/releases/download/v1.7.12/$tarball"\n'
        'echo "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8'
        '  $RUNNER_TEMP/$tarball" | sha256sum -c -\n'
        'wheel="zizmor-1.30.1-py3-none-manylinux_2_28_x86_64.whl"\n'
        'echo "eee12266b793cb87ad4a7e3af2e72404f8a63e3de5eb099b80bf7b1cfd232a8e'
        '  $RUNNER_TEMP/$wheel" | sha256sum -c -\n'
        "      - uses: aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25\n"
        "        with:\n"
        "          version: v0.75.0\n",
        encoding="utf-8",
    )

    statuses = check_workflow_downloads(
        tmp_path,
        fetch_json=_fetch_json,
        list_remote_tags=lambda _url: ["v99.0.0"],
    )

    by_name = {status.name: status for status in statuses}
    assert by_name["rhysd/actionlint"].current == "v1.7.12"
    assert by_name["rhysd/actionlint"].outdated is True
    assert by_name["zizmor"].current == "1.30.1"
    assert by_name["zizmor"].latest == "99.0.0"
    assert by_name["aquasecurity/trivy"].current == "v0.75.0"
    assert by_name["actionlint download checksum"].outdated is False
    assert by_name["zizmor download checksum"].outdated is False


def test_workflow_download_checksum_must_be_sha256(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "lint.yml").write_text(
        'tarball="actionlint_1.7.12_linux_amd64.tar.gz"\n'
        'echo "deadbeef  $RUNNER_TEMP/$tarball" | sha256sum -c -\n',
        encoding="utf-8",
    )

    statuses = check_workflow_downloads(
        tmp_path,
        fetch_json=_fetch_json,
        list_remote_tags=lambda _url: [],
    )

    checksum = next(status for status in statuses if status.name.endswith("checksum"))
    assert checksum.outdated is True
    assert checksum.latest == "invalid"


def test_markdown_report_includes_surface_and_status() -> None:
    report = render_markdown(
        [
            DependencyStatus(
                "npm",
                "playwright",
                "1.63.0",
                "1.64.0",
                "runtime/package.json",
                True,
            )
        ]
    )

    assert "## npm" in report
    assert "playwright" in report
    assert "update available" in report


def test_json_report_counts_fetch_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def failed_fetch(_root: Path) -> list[DependencyStatus]:
        return [
            DependencyStatus(
                "pypi",
                "example",
                "1.0.0",
                "?",
                "pyproject.toml",
                False,
                fetch_failed=True,
            )
        ]

    def no_deferrals(_root: Path) -> list[DependencyDeferral]:
        return []

    monkeypatch.setattr(check_dependency_updates_module, "check_dependency_updates", failed_fetch)
    monkeypatch.setattr(check_dependency_updates_module, "load_deferrals", no_deferrals)
    report = tmp_path / "report.json"

    assert main(["--repo-root", str(tmp_path), "--json", str(report)]) == 0
    assert json.loads(report.read_text(encoding="utf-8"))["unknown_count"] == 1
