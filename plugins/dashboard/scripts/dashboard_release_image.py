"""Resolve and authenticate the tools image for a published Dashboard version."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import NamedTuple, cast
from urllib.error import HTTPError
from urllib.request import urlopen

REPOSITORY = "VibeBB/dashboard-agent"
IMAGE = "ghcr.io/vibebb/dashboard-tools"
RELEASE_WORKFLOW = f"{REPOSITORY}/.github/workflows/release.yml"
MANIFEST = "dashboard-tools-image.json"
BUNDLE = "dashboard-tools-image.bundle.jsonl"
VERIFIER_PATH = "plugins/dashboard/scripts/dashboard_release_image.py"
VERSION_RE = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")
SHA_RE = re.compile(r"[0-9a-f]{40}")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
MAX_ASSET_BYTES = 1024 * 1024


class ReleaseImage(NamedTuple):
    digest: str
    commit: str


class MissingManifest(ValueError):
    def __init__(self, tag: str) -> None:
        super().__init__(f"missing release image metadata for {tag}")
        self.tag = tag


def _download(tag: str, asset: str) -> bytes:
    url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{asset}"
    with urlopen(url, timeout=30) as response:
        data = response.read(MAX_ASSET_BYTES + 1)
    if not data or len(data) > MAX_ASSET_BYTES:
        raise ValueError(f"invalid release asset size: {asset}")
    return data


def _manifest(data: bytes, tag: str) -> ReleaseImage:
    raw: object = json.loads(data)
    if not isinstance(raw, dict):
        raise ValueError("invalid Dashboard release image metadata")
    entry = cast(dict[str, object], raw)
    digest = entry.get("digest")
    commit = entry.get("commit")
    if (
        entry.get("tag") != tag
        or entry.get("image") != IMAGE
        or not isinstance(digest, str)
        or not DIGEST_RE.fullmatch(digest)
        or not isinstance(commit, str)
        or not SHA_RE.fullmatch(commit)
    ):
        raise ValueError("invalid Dashboard release image metadata")
    return ReleaseImage(digest, commit)


def resolve(plugin_json: Path) -> ReleaseImage:
    plugin: object = json.loads(plugin_json.read_text(encoding="utf-8"))
    version = cast(dict[str, object], plugin).get("version") if isinstance(plugin, dict) else None
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise ValueError("invalid Dashboard plugin version")
    tag = f"v{version}"
    try:
        data = _download(tag, MANIFEST)
    except HTTPError as exc:
        if exc.code != 404:
            raise
        raise MissingManifest(tag) from exc
    gh = shutil.which("gh")
    if gh is None:
        raise ValueError("GitHub CLI (gh) is required to verify Dashboard release metadata")
    image = _manifest(data, tag)
    with tempfile.TemporaryDirectory(prefix="dashboard-image-") as tmp:
        manifest = Path(tmp) / MANIFEST
        manifest.write_bytes(data)
        bundle = Path(tmp) / BUNDLE
        bundle.write_bytes(_download(tag, BUNDLE))
        subprocess.run(
            [
                gh,
                "attestation",
                "verify",
                str(manifest),
                "--bundle",
                str(bundle),
                "--repo",
                REPOSITORY,
                "--signer-workflow",
                RELEASE_WORKFLOW,
                "--source-ref",
                f"refs/tags/{tag}",
                "--source-digest",
                image.commit,
                "--signer-digest",
                image.commit,
                "--deny-self-hosted-runners",
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
    return image


def resolve_if_released(plugin_json: Path) -> ReleaseImage | None:
    try:
        return resolve(plugin_json)
    except MissingManifest as missing:
        tag = missing.tag
        try:
            _download(tag, BUNDLE)
        except HTTPError as exc:
            if exc.code != 404:
                raise
        else:
            raise missing
        url = f"https://raw.githubusercontent.com/{REPOSITORY}/refs/tags/{tag}/{VERIFIER_PATH}"
        try:
            with urlopen(url, timeout=30):
                pass
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise
        raise missing
