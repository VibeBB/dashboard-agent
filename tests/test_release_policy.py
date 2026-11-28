"""Release metadata, candidate provenance, and workflow policy."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import nullcontext
from http.client import HTTPMessage
from pathlib import Path
from urllib.error import HTTPError

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plugins.dashboard.scripts import dashboard_launcher as launcher  # noqa: E402
from plugins.dashboard.scripts import dashboard_release_image as installed  # noqa: E402
from scripts import validate_release_candidate as candidate  # noqa: E402

SHA = "a" * 40
OLDER = "b" * 40
DIGEST = "sha256:" + "c" * 64
TAG = "v1.2.3"
IMAGE = f"{candidate.PACKAGE}@{DIGEST}"


def _gh_path(_name: str) -> str:
    return "/usr/bin/gh"


@pytest.fixture
def plugin(tmp_path: Path) -> Path:
    path = tmp_path / "plugin.json"
    path.write_text('{"version":"1.2.3"}', encoding="utf-8")
    return path


def test_metadata_verification_binds_workflow_tag_and_commit(
    monkeypatch: pytest.MonkeyPatch, plugin: Path, tmp_path: Path
) -> None:
    manifest = tmp_path / "manifest.json"
    candidate.write_manifest(manifest, TAG, SHA, IMAGE)

    def download(tag: str, asset: str) -> bytes:
        assert tag == TAG
        return manifest.read_bytes() if asset == installed.MANIFEST else b"bundle"

    def verify(args: list[str], *, check: bool, capture_output: bool, timeout: int) -> None:
        assert check and capture_output and timeout > 0
        assert Path(args[3]).read_bytes() == manifest.read_bytes()
        assert Path(args[5]).read_bytes() == b"bundle"
        assert args[args.index("--source-ref") + 1] == f"refs/tags/{TAG}"
        assert args[args.index("--source-digest") + 1] == SHA
        assert args[args.index("--signer-workflow") + 1] == installed.RELEASE_WORKFLOW

    monkeypatch.setattr(installed, "_download", download)
    monkeypatch.setattr(installed.shutil, "which", _gh_path)
    monkeypatch.setattr(installed.subprocess, "run", verify)
    assert installed.resolve(plugin) == installed.ReleaseImage(DIGEST, SHA)


def test_rejects_invalid_release_asset_and_bad_signature(
    monkeypatch: pytest.MonkeyPatch, plugin: Path
) -> None:
    entry = {"tag": "v1.2.2", "image": installed.IMAGE, "digest": DIGEST, "commit": SHA}

    def download(_tag: str, _asset: str) -> bytes:
        return json.dumps(entry).encode()

    def reject(args: list[str], *, check: bool, capture_output: bool, timeout: int) -> None:
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(installed, "_download", download)
    monkeypatch.setattr(installed.shutil, "which", _gh_path)
    monkeypatch.setattr(installed.subprocess, "run", reject)
    with pytest.raises(ValueError, match="invalid Dashboard release image metadata"):
        installed.resolve(plugin)
    entry["tag"] = TAG
    with pytest.raises(subprocess.CalledProcessError):
        installed.resolve(plugin)


@pytest.mark.parametrize("tag_requires_metadata", [True, False])
def test_missing_metadata_uses_lock_only_for_default_branch_or_legacy_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tag_requires_metadata: bool
) -> None:
    plugin_json = tmp_path / "plugin.json"
    plugin_json.write_text('{"version":"1.2.3"}', encoding="utf-8")

    def urlopen(url: str, *, timeout: int) -> object:
        marker = f"https://raw.githubusercontent.com/{installed.REPOSITORY}/refs/tags/{TAG}"
        if tag_requires_metadata and url == f"{marker}/{installed.VERIFIER_PATH}":
            return nullcontext()
        raise HTTPError(url, 404, "not found", HTTPMessage(), None)

    monkeypatch.setattr(installed, "urlopen", urlopen)
    if tag_requires_metadata:
        with pytest.raises(installed.MissingManifest, match=TAG):
            installed.resolve_if_released(plugin_json)
    else:
        assert installed.resolve_if_released(plugin_json) is None
        with pytest.raises(installed.MissingManifest, match=TAG):
            installed.resolve(plugin_json)


def test_candidate_falls_back_only_to_unchanged_attested_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def git(*_args: str) -> str:
        return f"{SHA}\n{OLDER}"

    def verify(source: str) -> str:
        if source == SHA:
            raise subprocess.CalledProcessError(1, "gh")
        return IMAGE

    def changed(source: str, _sha: str) -> bool:
        return source == OLDER

    def unchanged(_source: str, _sha: str) -> bool:
        return False

    monkeypatch.setattr(candidate, "git", git)
    monkeypatch.setattr(candidate, "verify_candidate", verify)
    monkeypatch.setattr(candidate, "_inputs_changed", unchanged)
    assert candidate.resolve_candidate(SHA) == (OLDER, IMAGE)
    monkeypatch.setattr(candidate, "_inputs_changed", changed)
    with pytest.raises(ValueError, match="no provenance-verified candidate"):
        candidate.resolve_candidate(SHA)


def test_installed_launcher_does_not_fall_back_to_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    metadata = tmp_path / ".plugin"
    metadata.mkdir()
    (metadata / "plugin.json").write_text('{"version":"1.2.3"}', encoding="utf-8")
    (tmp_path / "tools-image.json").write_text(
        json.dumps({"image": installed.IMAGE, "digest": DIGEST}), encoding="utf-8"
    )

    def unavailable(_path: Path) -> installed.ReleaseImage:
        raise ValueError("unverified image")

    monkeypatch.delenv("DASHBOARD_TOOLS_IMAGE", raising=False)
    monkeypatch.setenv("DASHBOARD_VERIFY_ATTESTATION", "off")
    monkeypatch.setattr(launcher.dashboard_release_image, "resolve", unavailable)
    with pytest.raises(ValueError, match="unverified image"):
        launcher.image_pin(tmp_path)


def test_candidate_attestation_is_after_gates_and_release_is_tag_only() -> None:
    workflows = ROOT / ".github/workflows"
    publisher = (workflows / "publish-dashboard-images.yml").read_text(encoding="utf-8")
    proof = publisher.index("Attest gated tools image provenance")
    for gate in (
        "Smoke published tools through the launcher",
        "Scan tools image (Trivy SARIF)",
        "Validate tools SPDX SBOM",
        "Attest tools SBOM",
    ):
        assert publisher.index(gate) < proof
    assert "gh pr create" not in publisher
    assert "imagetools create" not in publisher
    assert "scan-ref: ${{ steps.scan-ref.outputs.ref }}" in publisher
    release = (workflows / "release.yml").read_text(encoding="utf-8")
    assert 'on:\n  push:\n    tags: ["v[0-9]+.[0-9]+.[0-9]+"]\n' in release
    assert "workflow_dispatch" not in release
    publish = release[release.index("\n  publish:") :]
    assert "environment: production" in publish
    assert "gh release create" in publish and "--verify-tag" in publish
    assert publish.index("Attest versioned image") < publish.index("--publish-check")
    assert publish.index("--publish-check") < publish.index("imagetools create")
    assert publish.index("gh release create") < publish.index("metadata = resolve(")


def test_production_policy_refuses_draft_on_later_api_page(tmp_path: Path) -> None:
    def git(*args: str) -> str:
        return subprocess.check_output(
            [
                "git",
                "-c",
                "user.name=Release Test",
                "-c",
                "user.email=test@example.invalid",
                *args,
            ],
            cwd=tmp_path,
            text=True,
        ).strip()

    git("init", "-q")
    git("commit", "--allow-empty", "-qm", "release test")
    sha = git("rev-parse", "HEAD")
    git("update-ref", "refs/remotes/origin/main", sha)
    git("update-ref", f"refs/tags/{TAG}", sha)
    event = tmp_path / "event.json"
    event.write_text('{"deleted":false}', encoding="utf-8")
    gh = tmp_path / "gh"
    gh.write_text(
        """#!/usr/bin/env bash
case "${*: -1}" in
  */environments/production) printf '%s\n' "$TEST_ENVIRONMENT" ;;
  */deployment-branch-policies*)
    echo '[{"branch_policies":[{"name":"v*","type":"tag"}]}]' ;;
  */releases*) printf '%s\n' "$TEST_RELEASES" ;;
  *) exit 1 ;;
esac
""",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    python = tmp_path / "python3"
    python.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    python.chmod(0o755)
    production = {
        "can_admins_bypass": False,
        "deployment_branch_policy": {
            "protected_branches": False,
            "custom_branch_policies": True,
        },
        "protection_rules": [{"type": "required_reviewers", "reviewers": [{"id": 1}]}],
    }
    env = os.environ | {
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_REF": f"refs/tags/{TAG}",
        "GITHUB_REF_NAME": TAG,
        "GITHUB_REPOSITORY": installed.REPOSITORY,
        "GITHUB_SHA": sha,
        "TEST_ENVIRONMENT": json.dumps(production),
    }

    def run(releases: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(ROOT / "scripts/validate_release.sh"), "--publish-check"],
            cwd=tmp_path,
            env=env | {"TEST_RELEASES": releases},
            capture_output=True,
            text=True,
            check=False,
        )

    assert run("[[]]").returncode == 0
    result = run(f'[[{{"tag_name":"v0.1.0"}}],[{{"tag_name":"{TAG}","draft":true}}]]')
    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "Cannot confirm there is no existing Release" in output
