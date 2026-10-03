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
    } <= surfaces
    assert any(status.name == "typescript" and status.surface == "npm" for status in statuses)
    assert any(status.name == "tauri" and status.surface == "tauri-scaffold" for status in statuses)
    assert any(
        status.name == "transitive-lib" and status.surface == "pypi-lock" for status in statuses
    )


def test_current_dependency_deferrals_have_review_dates() -> None:
    deferrals = load_deferrals(ROOT)

    assert len(deferrals) == 6
    assert {item.review_by for item in deferrals} == {
        date(2026, 10, 7),
        date(2027, 1, 3),
        date(2027, 4, 1),
    }
    assert {item.name for item in deferrals} == {
        "@types/node",
        "typescript",
        "*tauri*",
        "mcp",
        "emscripten/emsdk",
        "node",
    }
    mcp = next(item for item in deferrals if item.name == "mcp")
    assert mcp.latest == "2.2.0"
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
