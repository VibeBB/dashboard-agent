#!/usr/bin/env python3
"""Report updates across dashboard Python, image, runtime, and scaffold pins.

Surfaces include `git clone --branch` pins inside workflows (e.g. the
pinned CISOfy/lynis checkout in container-audit.yml).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
HTTP_TIMEOUT_SECONDS = 30
SUBPROCESS_TIMEOUT_SECONDS = 120
DEPENDENCY_SURFACES = {
    "pypi",
    "pypi-lock",
    "uv",
    "npm",
    "tauri-scaffold",
    "github-actions",
    "git-clone",
    "docker-base",
    "servo",
}
FetchJson = Callable[[str], Any]
ListRemoteTags = Callable[[str], list[str]]
RunUv = Callable[[list[str], Path], str]


@dataclass(frozen=True)
class DependencyStatus:
    surface: str
    name: str
    current: str
    latest: str
    source: str
    outdated: bool
    note: str = ""
    deferred: bool = False
    fetch_failed: bool = False


@dataclass(frozen=True)
class DependencyDeferral:
    surface: str
    name: str
    latest: str
    review_by: date
    reason: str


def _default_fetch_json(url: str) -> Any:
    request = Request(url, headers={"User-Agent": "dashboard-agent-dependency-check"})
    with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _default_list_remote_tags(url: str) -> list[str]:
    result = subprocess.run(
        ["git", "ls-remote", "--tags", url],
        capture_output=True,
        text=True,
        check=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
    )
    tags: list[str] = []
    for line in result.stdout.splitlines():
        ref = line.split("\t")[-1]
        if ref.endswith("^{}"):
            continue
        if ref.startswith("refs/tags/"):
            tags.append(ref.removeprefix("refs/tags/"))
    return tags


def _default_run_uv(command: list[str], cwd: Path) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        timeout=SUBPROCESS_TIMEOUT_SECONDS,
    )
    return result.stdout


def _dict(value: Any, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(message)
    return cast(dict[str, Any], value)


def _normalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _latest_json_value(fetch_json: FetchJson, url: str, *path: str) -> str | None:
    try:
        value: Any = fetch_json(url)
        for key in path:
            if not isinstance(value, dict):
                return None
            value = cast(dict[str, Any], value).get(key)
        return value if isinstance(value, str) and value else None
    except (OSError, ValueError):
        return None


def _project_data(root: Path) -> dict[str, Any]:
    with (root / "pyproject.toml").open("rb") as stream:
        return _dict(tomllib.load(stream), "pyproject.toml is not an object")


def _lock_versions(root: Path) -> dict[str, str]:
    with (root / "uv.lock").open("rb") as stream:
        payload = _dict(tomllib.load(stream), "uv.lock is not an object")
    packages = payload.get("package")
    if not isinstance(packages, list):
        raise ValueError("uv.lock has no package entries")
    versions: dict[str, str] = {}
    for item in cast(list[Any], packages):
        package = _dict(item, "uv.lock package entry is malformed")
        name = package.get("name")
        version = package.get("version")
        if isinstance(name, str) and isinstance(version, str):
            versions[_normalize_name(name)] = version
    return versions


def _direct_python_names(data: dict[str, Any]) -> list[str]:
    project = _dict(data.get("project"), "pyproject.toml has no [project]")
    raw_dependencies: list[Any] = []
    dependencies = project.get("dependencies", [])
    if isinstance(dependencies, list):
        raw_dependencies.extend(cast(list[Any], dependencies))
    optional = project.get("optional-dependencies", {})
    if isinstance(optional, dict):
        for group in cast(dict[str, Any], optional).values():
            if isinstance(group, list):
                raw_dependencies.extend(cast(list[Any], group))
    groups = data.get("dependency-groups", {})
    if isinstance(groups, dict):
        for group in cast(dict[str, Any], groups).values():
            if isinstance(group, list):
                raw_dependencies.extend(cast(list[Any], group))
    names: list[str] = []
    for raw in raw_dependencies:
        if not isinstance(raw, str):
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+)", raw.strip())
        if match is not None:
            name = _normalize_name(match.group(1))
            if name not in names:
                names.append(name)
    return names


def _pypi_statuses(root: Path, fetch_json: FetchJson) -> list[DependencyStatus]:
    project = _project_data(root)
    versions = _lock_versions(root)
    tool = project.get("tool", {})
    tool_data = cast(dict[str, Any], tool) if isinstance(tool, dict) else {}
    uv_config = tool_data.get("uv", {})
    uv_data = cast(dict[str, Any], uv_config) if isinstance(uv_config, dict) else {}
    source_map = uv_data.get("sources", {})
    source_names: set[str] = set()
    if isinstance(source_map, dict):
        source_names = {_normalize_name(name) for name in cast(dict[str, Any], source_map)}
    statuses: list[DependencyStatus] = []
    for name in _direct_python_names(project):
        if name in source_names:
            continue
        current = versions.get(name, "?")
        latest = _latest_json_value(
            fetch_json, f"https://pypi.org/pypi/{name}/json", "info", "version"
        )
        statuses.append(
            DependencyStatus(
                "pypi",
                name,
                current,
                latest or "?",
                "pyproject.toml / uv.lock",
                latest is not None and current != latest,
                "" if latest is not None else "fetch failed",
                fetch_failed=latest is None,
            )
        )
    required = uv_data.get("required-version")
    if isinstance(required, str):
        current = required.removeprefix("==").removeprefix("v")
        latest = _latest_json_value(fetch_json, "https://pypi.org/pypi/uv/json", "info", "version")
        statuses.append(
            DependencyStatus(
                "uv",
                "uv",
                current,
                latest or "?",
                "pyproject.toml tool.uv.required-version",
                latest is not None and current != latest,
                "" if latest is not None else "fetch failed",
                fetch_failed=latest is None,
            )
        )
    return statuses


def _uv_lock_statuses(
    root: Path,
    direct_names: set[str],
    run_uv: RunUv,
) -> list[DependencyStatus]:
    output = run_uv(["uv", "lock", "--upgrade", "--dry-run"], root)
    patterns = (
        (re.compile(r"^Update (\S+) v(\S+) -> v(\S+)$"), "update"),
        (re.compile(r"^Add (\S+) v(\S+)$"), "add"),
        (re.compile(r"^Remove (\S+) v(\S+)$"), "remove"),
    )
    statuses: list[DependencyStatus] = []
    for line in output.splitlines():
        line = line.strip()
        for pattern, kind in patterns:
            match = pattern.fullmatch(line)
            if match is None:
                continue
            name, first, *rest = match.groups()
            if _normalize_name(name) in direct_names:
                break
            if kind == "update":
                current, latest, note = first, rest[0], ""
            elif kind == "add":
                current, latest, note = "-", first, "would be added"
            else:
                current, latest, note = first, "-", "would be removed"
            statuses.append(
                DependencyStatus(
                    "pypi-lock",
                    name,
                    current,
                    latest,
                    "uv.lock",
                    True,
                    note,
                )
            )
            break
    return statuses


def _npm_latest(fetch_json: FetchJson, name: str, current: str) -> str | None:
    encoded = quote(name, safe="@")
    try:
        payload = _dict(
            fetch_json(f"https://registry.npmjs.org/{encoded}"),
            f"npm registry response for {name} is malformed",
        )
        dist_tags = payload.get("dist-tags")
        if not isinstance(dist_tags, dict):
            return None
        tags = cast(dict[str, Any], dist_tags)
        next_tag = tags.get("next")
        preferred = "next" if "-" in current and isinstance(next_tag, str) else "latest"
        version = tags.get(preferred)
        return version if isinstance(version, str) and version else None
    except (OSError, ValueError):
        return None


def _exact_npm_pins(root: Path, rel: str) -> dict[str, str]:
    payload: Any = json.loads((root / rel).read_text(encoding="utf-8"))
    data = _dict(payload, f"{rel} is not an object")
    packages: dict[str, str] = {}
    for field in ("dependencies", "devDependencies"):
        section = data.get(field, {})
        if not isinstance(section, dict):
            continue
        for name, version in cast(dict[object, object], section).items():
            if isinstance(name, str) and isinstance(version, str):
                packages[name] = version
    return packages


def _npm_statuses(
    root: Path,
    rel: str,
    *,
    surface: str,
    fetch_json: FetchJson,
) -> list[DependencyStatus]:
    statuses: list[DependencyStatus] = []
    for name, current in sorted(_exact_npm_pins(root, rel).items()):
        exact = re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", current) is not None
        latest = _npm_latest(fetch_json, name, current)
        if not exact:
            latest = latest or "?"
        statuses.append(
            DependencyStatus(
                surface,
                name,
                current,
                latest or "?",
                rel,
                (not exact) or (latest is not None and current != latest),
                "pin is not an exact version" if not exact else ("" if latest else "fetch failed"),
                fetch_failed=latest is None and exact,
            )
        )
    return statuses


def _tauri_statuses(root: Path, fetch_json: FetchJson) -> list[DependencyStatus]:
    source = (root / "src/dashboard/generate.py").read_text(encoding="utf-8")
    start = source.index("def build_tauri_scaffold")
    end = source.find("\ndef ", start + 1)
    section = source[start : end if end >= 0 else len(source)]
    npm_pins = dict(
        re.findall(r'"((?:@[A-Za-z0-9_.-]+/)?[A-Za-z0-9_.-]+)"\s*:\s*"(\d+\.\d+\.\d+)"', section)
    )
    npm_pins.update(
        re.findall(
            r'dependencies\["((?:@[A-Za-z0-9_.-]+/)?[A-Za-z0-9_.-]+)"\]\s*=\s*"(\d+\.\d+\.\d+)"',
            section,
        )
    )
    statuses: list[DependencyStatus] = []
    for name, current in sorted(npm_pins.items()):
        latest = _npm_latest(fetch_json, name, current)
        statuses.append(
            DependencyStatus(
                "tauri-scaffold",
                name,
                current,
                latest or "?",
                "src/dashboard/generate.py (generated package.json)",
                latest is not None and current != latest,
                "" if latest is not None else "fetch failed",
                fetch_failed=latest is None,
            )
        )
    crate_pins = dict(
        re.findall(
            r'([A-Za-z0-9_-]+)\s*=\s*\{\s*version\s*=\s*"=(\d+\.\d+\.\d+)"',
            section,
        )
    )
    for name, current in sorted(crate_pins.items()):
        latest = _latest_json_value(
            fetch_json,
            f"https://crates.io/api/v1/crates/{quote(name, safe='')}",
            "crate",
            "max_version",
        )
        statuses.append(
            DependencyStatus(
                "tauri-scaffold",
                name,
                current,
                latest or "?",
                "src/dashboard/generate.py (generated Cargo.toml)",
                latest is not None and current != latest,
                "" if latest is not None else "fetch failed",
                fetch_failed=latest is None,
            )
        )
    return statuses


_ACTION = re.compile(r"uses:\s*([\w.-]+/[\w.-]+)@([0-9a-f]{40})(?:\s*#\s*(v[\w.-]+))?")
_GIT_CLONE = re.compile(
    r"git\s+clone[\s\S]{0,200}?--branch\s+(\S+)\s*(?:\\\s*\n\s*)?"
    r"\s*(https://github\.com/([\w.-]+/[\w.-]+))"
)


def _version_key(value: str) -> tuple[int, ...] | None:
    match = re.fullmatch(r"v?(\d+(?:\.\d+){0,3})(?:[-+].*)?", value)
    if match is None:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _workflow_files(root: Path) -> list[Path]:
    workflows = sorted((root / ".github/workflows").glob("*.yml"))
    workflows.extend(sorted((root / ".github/workflows").glob("*.yaml")))
    return workflows


def _github_latest_tag(repo: str, list_remote_tags: ListRemoteTags) -> str:
    try:
        tags = list_remote_tags(f"https://github.com/{repo}.git")
    except (OSError, subprocess.SubprocessError):
        return ""
    stable = [tag for tag in tags if _version_key(tag) is not None]
    return max(stable, key=lambda tag: _version_key(tag) or (), default="")


def _action_statuses(root: Path, list_remote_tags: ListRemoteTags) -> list[DependencyStatus]:
    pins: dict[str, tuple[str, str | None]] = {}
    for workflow in _workflow_files(root):
        text = workflow.read_text(encoding="utf-8")
        for repo, sha, version in _ACTION.findall(text):
            pins.setdefault(repo, (sha, version or None))
    statuses: list[DependencyStatus] = []
    for repo, (sha, current_tag) in sorted(pins.items()):
        latest = _github_latest_tag(repo, list_remote_tags)
        current_key = _version_key(current_tag or "")
        latest_key = _version_key(latest)
        statuses.append(
            DependencyStatus(
                "github-actions",
                repo,
                current_tag or sha,
                latest or "?",
                ".github/workflows",
                bool(current_key and latest_key and latest_key > current_key),
                "version tag comment missing"
                if latest and not current_tag
                else ("" if latest else "fetch failed"),
                fetch_failed=not latest,
            )
        )
    return statuses


def check_git_clones(
    root: Path, *, list_remote_tags: ListRemoteTags = _default_list_remote_tags
) -> list[DependencyStatus]:
    """`git clone --branch <ref> <github-url>` pins inside workflows
    (e.g. the pinned Lynis checkout in container-audit.yml)."""
    statuses: list[DependencyStatus] = []
    seen: set[tuple[str, str]] = set()
    for workflow in _workflow_files(root):
        for ref, _url, repo in _GIT_CLONE.findall(workflow.read_text(encoding="utf-8")):
            if (repo, ref) in seen:
                continue
            seen.add((repo, ref))
            latest = _github_latest_tag(repo, list_remote_tags)
            statuses.append(
                DependencyStatus(
                    "git-clone",
                    repo,
                    ref,
                    latest or "?",
                    workflow.name,
                    bool(latest) and latest != ref,
                    "" if latest else "fetch failed",
                    fetch_failed=not latest,
                )
            )
    return statuses


_FROM = re.compile(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)", re.MULTILINE)
_ARG = re.compile(r"^ARG\s+([A-Z_]+)=([^\s#]+)", re.MULTILINE)
_SERVO_VERSION = re.compile(r"/download/(v[\d.]+)/")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _docker_statuses(root: Path, fetch_json: FetchJson) -> list[DependencyStatus]:
    statuses: list[DependencyStatus] = []
    for dockerfile in sorted((root / "docker").glob("*.Dockerfile")):
        text = dockerfile.read_text(encoding="utf-8")
        for reference in _FROM.findall(text):
            image, separator, digest = reference.partition("@")
            statuses.append(
                DependencyStatus(
                    "docker-base",
                    image,
                    reference,
                    "digest-pinned"
                    if separator and _SHA256.fullmatch(digest.removeprefix("sha256:"))
                    else "unpinned",
                    dockerfile.relative_to(root).as_posix(),
                    not (separator and _SHA256.fullmatch(digest.removeprefix("sha256:"))),
                    "" if separator else "base image must use an immutable sha256 digest",
                )
            )
        args = dict(_ARG.findall(text))
        servo_url = args.get("SERVO_URL")
        servo_sha = args.get("SERVO_SHA256")
        if servo_url:
            version_match = _SERVO_VERSION.search(servo_url)
            current = version_match.group(1) if version_match else "?"
            latest = _latest_json_value(
                fetch_json,
                "https://api.github.com/repos/servo/servo/releases/latest",
                "tag_name",
            )
            statuses.append(
                DependencyStatus(
                    "servo",
                    "Servo release",
                    current,
                    latest or "?",
                    dockerfile.relative_to(root).as_posix() + " ARG SERVO_URL",
                    latest is not None and current != latest,
                    "" if latest else "fetch failed",
                    fetch_failed=latest is None,
                )
            )
        if servo_sha:
            valid = _SHA256.fullmatch(servo_sha) is not None
            statuses.append(
                DependencyStatus(
                    "servo",
                    "Servo archive SHA-256",
                    servo_sha,
                    "sha256 pinned" if valid else "invalid",
                    dockerfile.relative_to(root).as_posix() + " ARG SERVO_SHA256",
                    not valid,
                    "" if valid else "expected 64 lowercase hex characters",
                )
            )
    return statuses


def load_deferrals(root: Path) -> list[DependencyDeferral]:
    path = root / "scripts/dependency_update_deferrals.json"
    payload: Any = json.loads(path.read_text(encoding="utf-8"))
    data = _dict(payload, "dependency deferrals must be an object")
    if set(data) != {"deferrals"} or not isinstance(data.get("deferrals"), list):
        raise ValueError("dependency deferrals must contain a deferrals array")
    results: list[DependencyDeferral] = []
    expected = {"surface", "name", "latest", "review_by", "reason"}
    for raw in cast(list[Any], data["deferrals"]):
        item = _dict(raw, "dependency deferral is not an object")
        if set(item) != expected:
            raise ValueError("dependency deferral has unknown or missing keys")
        surface, name, latest, review_by, reason = (
            item.get("surface"),
            item.get("name"),
            item.get("latest"),
            item.get("review_by"),
            item.get("reason"),
        )
        if (
            not isinstance(surface, str)
            or surface not in DEPENDENCY_SURFACES
            or not isinstance(name, str)
            or not name
            or not isinstance(latest, str)
            or not latest
            or not isinstance(review_by, str)
            or not isinstance(reason, str)
            or not reason
        ):
            raise ValueError("dependency deferral has an invalid field")
        results.append(
            DependencyDeferral(surface, name, latest, date.fromisoformat(review_by), reason)
        )
    return results


def apply_deferrals(
    statuses: list[DependencyStatus],
    deferrals: list[DependencyDeferral],
    today: date,
) -> list[DependencyStatus]:
    results: list[DependencyStatus] = []
    for status in statuses:
        replacement = status
        if status.outdated:
            for deferral in deferrals:
                if (
                    deferral.surface == status.surface
                    and fnmatch.fnmatchcase(status.name, deferral.name)
                    and fnmatch.fnmatchcase(status.latest, deferral.latest)
                    and deferral.review_by >= today
                ):
                    note = f"deferred until {deferral.review_by.isoformat()}: {deferral.reason}"
                    replacement = replace(status, outdated=False, deferred=True, note=note)
                    break
        results.append(replacement)
    return results


def check_dependency_updates(
    root: Path,
    *,
    fetch_json: FetchJson = _default_fetch_json,
    list_remote_tags: ListRemoteTags = _default_list_remote_tags,
    run_uv: RunUv = _default_run_uv,
) -> list[DependencyStatus]:
    tag_cache: dict[str, list[str]] = {}

    def cached_tags(url: str) -> list[str]:
        if url not in tag_cache:
            tag_cache[url] = list_remote_tags(url)
        return tag_cache[url]

    pypi = _pypi_statuses(root, fetch_json)
    return [
        *pypi,
        *_uv_lock_statuses(root, {status.name for status in pypi}, run_uv),
        *_npm_statuses(
            root,
            "runtime/package.json",
            surface="npm",
            fetch_json=fetch_json,
        ),
        *_tauri_statuses(root, fetch_json),
        *_action_statuses(root, cached_tags),
        *check_git_clones(root, list_remote_tags=cached_tags),
        *_docker_statuses(root, fetch_json),
    ]


def render_markdown(statuses: list[DependencyStatus]) -> str:
    labels = {
        "git-clone": "Workflow git clones",
    }
    lines = ["# Dependency update check report", ""]
    for surface in sorted(DEPENDENCY_SURFACES):
        entries = [status for status in statuses if status.surface == surface]
        lines.extend([f"## {labels.get(surface, surface)}", ""])
        if not entries:
            lines.extend(["Nothing to check", ""])
            continue
        lines.extend(
            [
                "| dependency | current | latest | state | source |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for status in entries:
            state = (
                "deferred"
                if status.deferred
                else "update available"
                if status.outdated
                else "unknown"
                if status.fetch_failed
                else "up to date"
            )
            note = f" ({status.note})" if status.note else ""
            row = (
                f"| {status.name} | {status.current} | {status.latest}{note} | "
                f"{state} | {status.source} |"
            )
            lines.append(row)
        lines.append("")
    outdated = sum(status.outdated for status in statuses)
    deferred = sum(status.deferred for status in statuses)
    lines.append(f"update candidates: {outdated}")
    lines.append(f"deferred: {deferred}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--json", dest="json_path", type=Path)
    args = parser.parse_args(argv)
    try:
        root = args.repo_root.resolve()
        statuses = apply_deferrals(
            check_dependency_updates(root),
            load_deferrals(root),
            date.today(),
        )
        markdown = render_markdown(statuses)
        if args.markdown is not None:
            args.markdown.write_text(markdown, encoding="utf-8")
        if args.json_path is not None:
            args.json_path.write_text(
                json.dumps(
                    {
                        "statuses": [asdict(status) for status in statuses],
                        "outdated_count": sum(status.outdated for status in statuses),
                        "deferred_count": sum(status.deferred for status in statuses),
                        "unknown_count": sum(status.fetch_failed for status in statuses),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        print(markdown, end="")
    except (
        OSError,
        ValueError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"dependency update check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
