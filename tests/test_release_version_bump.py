from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import NamedTuple

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = f"VibeBB/{ROOT.name}"
SCRIPT = ROOT / "scripts/release_version_bump.sh"
PR_URL = f"https://github.com/{REPOSITORY}/pull/123"
HEAD_SHA = "0" * 40
MAIN_SHA = "f" * 40

GH_STUB = """#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >> "$GH_STUB_CALLS"
case "${1:-} ${2:-}" in
  "pr create")
    printf '%s\\n' "$GH_STUB_PR_URL"
    ;;
  "workflow run")
    ;;
  "run list")
    printf '424242\\n'
    ;;
  "run watch")
    ;;
  "run view")
    case "$GH_STUB_CASE" in
      gate-failure) printf 'failure\\n' ;;
      *) printf 'success\\n' ;;
    esac
    ;;
  "pr close" | "pr merge" | "pr view")
    ;;
  api\\ *)
    case "$GH_STUB_CASE" in
      merge-stalls) printf '\\n' ;;
      *) printf '2026-10-04T00:00:00Z\\n' ;;
    esac
    ;;
esac
"""

GIT_STUB = """#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >> "$GIT_STUB_CALLS"
case "${1:-}" in
  ls-remote)
    if [ "${GIT_STUB_TAG_EXISTS:-0}" = "1" ]; then
      printf 'deadbeef\\trefs/tags/v9.9.9\\n'
      exit 0
    fi
    exit 1
    ;;
  rev-parse)
    case "${2:-}" in
      HEAD) printf '%s\\n' "$GIT_STUB_HEAD_SHA" ;;
      *) printf '%s\\n' "$GIT_STUB_MAIN_SHA" ;;
    esac
    ;;
esac
"""


class Fixture(NamedTuple):
    repo: Path
    env: dict[str, str]
    gh_calls: Path
    git_calls: Path
    output: Path
    summary: Path


@pytest.fixture
def release_bump(tmp_path: Path) -> Fixture:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(GH_STUB, encoding="utf-8")
    gh.chmod(0o755)
    git = bin_dir / "git"
    git.write_text(GIT_STUB, encoding="utf-8")
    git.chmod(0o755)

    repo = tmp_path / "repo"
    (repo / "plugins/dashboard/.plugin").mkdir(parents=True)
    (repo / "plugins/dashboard/skills/alpha").mkdir(parents=True)
    (repo / "plugins/dashboard/.plugin/plugin.json").write_text(
        '{\n  "version": "1.2.3"\n}\n', encoding="utf-8"
    )
    (repo / "plugins/dashboard/skills/alpha/SKILL.md").write_text(
        "name: alpha\nversion: 1.2.3\n", encoding="utf-8"
    )
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "dashboard-agent"\nversion = "1.2.3"\n', encoding="utf-8"
    )
    (repo / "uv.lock").write_text('name = "dashboard-agent"\nversion = "1.2.3"\n', encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "GITHUB_WORKSPACE": str(repo),
            "GITHUB_REPOSITORY": REPOSITORY,
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_RUN_ID": "42",
            "GITHUB_OUTPUT": str(tmp_path / "output.txt"),
            "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
            "GH_STUB_CALLS": str(tmp_path / "gh-calls.log"),
            "GH_STUB_PR_URL": PR_URL,
            "GH_STUB_CASE": "",
            "GIT_STUB_CALLS": str(tmp_path / "git-calls.log"),
            "GIT_STUB_HEAD_SHA": HEAD_SHA,
            "GIT_STUB_MAIN_SHA": MAIN_SHA,
            "BUMP": "patch",
            "SET_VERSION": "",
            "DRY_RUN": "false",
            "RELEASE_BUMP_RETRY_ATTEMPTS": "1",
            "RELEASE_BUMP_RETRY_DELAY_SECONDS": "0",
            "RELEASE_BUMP_RUN_DISCOVER_ATTEMPTS": "2",
            "RELEASE_BUMP_RUN_DISCOVER_SECONDS": "0",
            "RELEASE_BUMP_MERGE_WAIT_ATTEMPTS": "2",
            "RELEASE_BUMP_MERGE_WAIT_SECONDS": "0",
        }
    )
    return Fixture(
        repo=repo,
        env=env,
        gh_calls=tmp_path / "gh-calls.log",
        git_calls=tmp_path / "git-calls.log",
        output=tmp_path / "output.txt",
        summary=tmp_path / "summary.md",
    )


def run_bump(fixture: Fixture) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=fixture.env,
        cwd=fixture.repo,
    )


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def test_bump_merges_version_pr(release_bump: Fixture) -> None:
    result = run_bump(release_bump)
    gh_calls = read(release_bump.gh_calls)
    git_calls = read(release_bump.git_calls)
    output = read(release_bump.output)

    assert result.returncode == 0, result.stderr
    assert f"workflow run ci.yml --repo {REPOSITORY} --ref bot/release-bump-v1.2.4-42" in gh_calls
    assert (
        f"workflow run workflow-lint.yml --repo {REPOSITORY} "
        "--ref bot/release-bump-v1.2.4-42" in gh_calls
    )
    assert "pr create" in gh_calls
    assert "run watch" in gh_calls
    assert "run view" in gh_calls
    assert f"pr merge --repo {REPOSITORY} --auto --squash --delete-branch {PR_URL}" in gh_calls
    assert f"api repos/{REPOSITORY}/pulls/123" in gh_calls
    assert "pr close" not in gh_calls
    assert "switch -q -c bot/release-bump-v1.2.4-42" in git_calls
    assert "commit -m Release v1.2.4: update version files" in git_calls
    assert "push origin HEAD:refs/heads/bot/release-bump-v1.2.4-42" in git_calls
    assert "fetch -q origin main" in git_calls
    assert "version=1.2.4" in output
    assert f"sha={MAIN_SHA}" in output
    assert 'version = "1.2.4"' in read(release_bump.repo / "pyproject.toml")


def test_dry_run_closes_pr_without_merging(release_bump: Fixture) -> None:
    release_bump.env["DRY_RUN"] = "true"
    result = run_bump(release_bump)
    gh_calls = read(release_bump.gh_calls)
    output = read(release_bump.output)
    summary = read(release_bump.summary)

    assert result.returncode == 0, result.stderr
    assert "pr create" in gh_calls
    assert (
        f"pr close --repo {REPOSITORY} --delete-branch {PR_URL}"
        " --comment Dry run: closing without merge." in gh_calls
    )
    assert "pr merge" not in gh_calls
    assert f"api repos/{REPOSITORY}/pulls/" not in gh_calls
    assert "version=1.2.4" in output
    assert f"sha={HEAD_SHA}" in output
    assert "dry run complete: version files verified on bot/release-bump-v1.2.4-42" in summary


def test_explicit_version_matching_current_skips_bump(release_bump: Fixture) -> None:
    release_bump.env["SET_VERSION"] = "v1.2.3"
    result = run_bump(release_bump)

    assert result.returncode == 0, result.stderr
    assert read(release_bump.gh_calls) == ""
    assert "pr create" not in read(release_bump.gh_calls)
    output = read(release_bump.output)
    assert "version=1.2.3" in output
    assert f"sha={HEAD_SHA}" in output
    assert 'version = "1.2.3"' in read(release_bump.repo / "pyproject.toml")


def test_existing_tag_fails_before_bump_pr(release_bump: Fixture) -> None:
    release_bump.env["GIT_STUB_TAG_EXISTS"] = "1"
    result = run_bump(release_bump)

    assert result.returncode == 1
    assert "tag v1.2.4 already exists" in result.stderr
    assert "pr create" not in read(release_bump.gh_calls)


def test_set_version_applies_explicit_bump(release_bump: Fixture) -> None:
    release_bump.env["SET_VERSION"] = "2.0.0"
    result = run_bump(release_bump)
    gh_calls = read(release_bump.gh_calls)

    assert result.returncode == 0, result.stderr
    assert "switch -q -c bot/release-bump-v2.0.0-42" in read(release_bump.git_calls)
    assert "pr create" in gh_calls
    assert "version=2.0.0" in read(release_bump.output)
    assert '"version": "2.0.0"' in read(release_bump.repo / "plugins/dashboard/.plugin/plugin.json")


def test_gate_workflow_failure_leaves_pr_open(release_bump: Fixture) -> None:
    release_bump.env["GH_STUB_CASE"] = "gate-failure"
    result = run_bump(release_bump)
    gh_calls = read(release_bump.gh_calls)

    assert result.returncode == 1
    assert "concluded 'failure'; the version PR remains open" in result.stderr
    assert "workflow run ci.yml" in gh_calls
    assert "pr merge" not in gh_calls
    assert "pr close" not in gh_calls
