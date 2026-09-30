from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/bump_version.py"
SKILLS = sorted(path.parent.name for path in (ROOT / "plugins/dashboard/skills").glob("*/SKILL.md"))


def _make_repo(tmp_path: Path, version: str = "0.1.0") -> Path:
    plugin = tmp_path / "plugins/dashboard/.plugin"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text(
        json.dumps({"name": "dashboard", "version": version}, indent=2) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "dashboard-agent"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    for skill in SKILLS:
        directory = tmp_path / f"plugins/dashboard/skills/{skill}"
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(
            f"---\nname: {skill}\nversion: {version}\n---\n",
            encoding="utf-8",
        )
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "another-package"\nversion = "9.9.9"\n\n'
        f'[[package]]\nname = "dashboard-agent"\nversion = "{version}"\n'
        'source = { virtual = "." }\n',
        encoding="utf-8",
    )
    return tmp_path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _versions(root: Path) -> list[str]:
    plugin = json.loads(
        (root / "plugins/dashboard/.plugin/plugin.json").read_text(encoding="utf-8")
    )
    versions = [plugin["version"]]
    project_version = re.search(
        r'(?m)^version = "([^"]+)"',
        (root / "pyproject.toml").read_text(encoding="utf-8"),
    )
    assert project_version is not None
    versions.append(project_version.group(1))
    for path in sorted((root / "plugins/dashboard/skills").glob("*/SKILL.md")):
        skill_version = re.search(
            r"(?m)^version: (.+)$",
            path.read_text(encoding="utf-8"),
        )
        assert skill_version is not None
        versions.append(skill_version.group(1))
    lock_version = re.search(
        r'name = "dashboard-agent"\nversion = "([^"]+)"',
        (root / "uv.lock").read_text(encoding="utf-8"),
    )
    assert lock_version is not None
    versions.append(lock_version.group(1))
    return versions


@pytest.mark.parametrize(
    ("bump", "expected"),
    [("patch", "0.1.1"), ("minor", "0.2.0"), ("major", "1.0.0")],
)
def test_bump(tmp_path: Path, bump: str, expected: str) -> None:
    root = _make_repo(tmp_path)
    result = _run("--bump", bump, "--root", str(root))
    assert result.returncode == 0
    assert result.stdout.strip() == expected
    assert _versions(root) == [expected] * (len(SKILLS) + 3)


def test_set_and_github_output(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    output = tmp_path / "github-output"
    result = _run("--set", "2.5.0", "--root", str(root), "--github-output", str(output))
    assert result.returncode == 0
    assert output.read_text(encoding="utf-8") == "version=2.5.0\ntag=v2.5.0\n"
    assert _versions(root) == ["2.5.0"] * (len(SKILLS) + 3)


def test_set_rejects_lower_version(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    result = _run("--set", "0.1.0", "--root", str(root))
    assert result.returncode == 1
    assert "must be greater than" in result.stderr
    assert _versions(root) == ["0.1.0"] * (len(SKILLS) + 3)


def test_inconsistent_version_files_are_rejected(tmp_path: Path) -> None:
    root = _make_repo(tmp_path)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "dashboard-agent"\nversion = "9.9.9"\n',
        encoding="utf-8",
    )
    result = _run("--bump", "patch", "--root", str(root))
    assert result.returncode == 1
    assert "version mismatch" in result.stderr
