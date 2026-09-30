#!/usr/bin/env python3
"""Bump the dashboard plugin and Python package version files together."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, cast

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_PLUGIN = "plugins/dashboard/.plugin/plugin.json"
_PROJECT = "pyproject.toml"
_LOCK = "uv.lock"
_PLUGIN_PATTERN = re.compile(r'"version":\s*"([^"]+)"')
_PROJECT_PATTERN = re.compile(r'(?m)^version = "([^"]+)"')
_SKILL_PATTERN = re.compile(r"(?m)^version: (.+)$")
_LOCK_PATTERN = re.compile(r'(?m)^(name = "dashboard-agent"\nversion = )"([^"]+)"')


class BumpError(Exception):
    pass


def _version_files(root: Path) -> list[str]:
    skills = sorted((root / "plugins/dashboard/skills").glob("*/SKILL.md"))
    if not skills:
        raise BumpError("plugins/dashboard/skills: no SKILL.md files found")
    return [_PLUGIN, _PROJECT, *[path.relative_to(root).as_posix() for path in skills]]


def _pattern(path: str) -> re.Pattern[str]:
    if path == _PLUGIN:
        return _PLUGIN_PATTERN
    if path == _PROJECT:
        return _PROJECT_PATTERN
    return _SKILL_PATTERN


def _read_versions(root: Path, files: list[str]) -> dict[str, str]:
    versions: dict[str, str] = {}
    for rel in files:
        path = root / rel
        if not path.is_file():
            raise BumpError(f"{rel}: file not found")
        if rel == _PLUGIN:
            try:
                payload: Any = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise BumpError(f"{rel}: invalid JSON: {exc}") from exc
            version = (
                cast(dict[str, Any], payload).get("version") if isinstance(payload, dict) else None
            )
            if not isinstance(version, str):
                raise BumpError(f"{rel}: version field not found")
            versions[rel] = version
            continue
        match = _pattern(rel).search(path.read_text(encoding="utf-8"))
        if match is None:
            raise BumpError(f"{rel}: version field not found")
        versions[rel] = match.group(1).strip()
    lock = root / _LOCK
    if not lock.is_file():
        raise BumpError(f"{_LOCK}: file not found")
    match = _LOCK_PATTERN.search(lock.read_text(encoding="utf-8"))
    if match is None:
        raise BumpError(f"{_LOCK}: dashboard-agent package entry not found")
    versions[_LOCK] = match.group(2)
    return versions


def _parse(version: str) -> tuple[int, int, int]:
    match = _SEMVER.fullmatch(version)
    if match is None:
        raise BumpError(f"version '{version}' is not X.Y.Z")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _current_version(versions: dict[str, str]) -> str:
    current = versions[_PLUGIN]
    mismatch = {path: version for path, version in versions.items() if version != current}
    if mismatch:
        detail = "; ".join(f"{path}={version}" for path, version in versions.items())
        raise BumpError(f"version mismatch across files: {detail}")
    _parse(current)
    return current


def _bumped(current: str, kind: str) -> str:
    major, minor, patch = _parse(current)
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _apply(root: Path, files: list[str], new: str) -> None:
    for rel in files:
        path = root / rel
        if rel == _PLUGIN:
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["version"] = new
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            continue
        pattern = _pattern(rel)
        text = path.read_text(encoding="utf-8")
        updated, count = pattern.subn(
            f"version: {new}" if rel.endswith("SKILL.md") else f'version = "{new}"', text, count=1
        )
        if count != 1:
            raise BumpError(f"{rel}: version field could not be updated")
        path.write_text(updated, encoding="utf-8")
    lock = root / _LOCK
    text = lock.read_text(encoding="utf-8")
    updated, count = _LOCK_PATTERN.subn(rf'\g<1>"{new}"', text, count=1)
    if count != 1:
        raise BumpError(f"{_LOCK}: dashboard-agent package entry could not be updated")
    lock.write_text(updated, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--bump", choices=["patch", "minor", "major"])
    group.add_argument("--set", dest="set_version", metavar="X.Y.Z")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--github-output", metavar="PATH")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve()
        files = _version_files(root)
        current = _current_version(_read_versions(root, files))
        if args.set_version:
            new = args.set_version.removeprefix("v")
            if not _SEMVER.fullmatch(new):
                raise BumpError(f"--set '{new}' is not X.Y.Z")
            if _parse(new) <= _parse(current):
                raise BumpError(f"--set '{new}' must be greater than current '{current}'")
        else:
            assert args.bump is not None
            new = _bumped(current, args.bump)
        if not args.dry_run:
            _apply(root, files, new)
        if args.github_output:
            with Path(args.github_output).open("a", encoding="utf-8") as stream:
                stream.write(f"version={new}\ntag=v{new}\n")
    except (BumpError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(new)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
