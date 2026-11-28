"""Resolve a gated Dashboard image candidate for the tagged version."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from scripts.bump_version import BumpError, current_version

PACKAGE = "ghcr.io/vibebb/dashboard-tools"
REPO = "VibeBB/dashboard-agent"
PUBLISHER = ".github/workflows/publish-dashboard-images.yml"
INPUTS = (
    "docker/**",
    ".dockerignore",
    ".trivyignore",
    "src/**",
    "plugins/dashboard/**",
    "runtime/**",
    "examples/**",
    "scripts/**",
    "pyproject.toml",
    "uv.lock",
    PUBLISHER,
    "scripts/publish_image_pin_pr.sh",
    "scripts/package_level_sbom.py",
    ":(exclude)docker/image-digests.json",
    ":(exclude)docker/README.md",
    ":(exclude)plugins/dashboard/tools-image.json",
)
VERSION_RE = re.compile(r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")
SHA_RE = re.compile(r"[0-9a-f]{40}")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def release_version(tag: str) -> str:
    root = Path.cwd()
    version = current_version(root)
    if not VERSION_RE.fullmatch(tag) or tag != f"v{version}":
        raise ValueError("tag does not match the release version files")
    return version


def _inputs_changed(source: str, sha: str) -> bool:
    return bool(git("diff", "--no-ext-diff", "--name-only", source, sha, "--", *INPUTS))


def verify_candidate(source: str, expected_image: str | None = None) -> str:
    if not SHA_RE.fullmatch(source):
        raise ValueError("invalid candidate source SHA")
    digest = subprocess.check_output(
        [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            f"{PACKAGE}:{source}-tools",
            "--format",
            "{{.Manifest.Digest}}",
        ],
        text=True,
        timeout=60,
    ).strip()
    if not DIGEST_RE.fullmatch(digest):
        raise ValueError("invalid Dashboard tools candidate digest")
    image = f"{PACKAGE}@{digest}"
    if expected_image is not None and expected_image != image:
        raise ValueError("the candidate digest changed after validation")
    subprocess.run(
        [
            "gh",
            "attestation",
            "verify",
            f"oci://{image}",
            "--repo",
            REPO,
            "--signer-workflow",
            f"{REPO}/{PUBLISHER}",
            "--source-ref",
            "refs/heads/main",
            "--source-digest",
            source,
            "--signer-digest",
            source,
            "--deny-self-hosted-runners",
        ],
        check=True,
        timeout=120,
    )
    return image


def resolve_candidate(sha: str) -> tuple[str, str]:
    for source in git("rev-list", "--first-parent", sha).splitlines():
        if _inputs_changed(source, sha):
            break
        try:
            return source, verify_candidate(source)
        except (ValueError, subprocess.SubprocessError) as exc:
            print(f"Candidate {source} failed verification: {exc}", file=sys.stderr)
    raise ValueError("no provenance-verified candidate found with unchanged image and gate inputs")


def validate(tag: str, source: str | None, image: str | None) -> dict[str, str]:
    version = release_version(tag)
    sha = git("rev-parse", "HEAD")
    newer = tuple(map(int, version.split(".")))
    if any(
        tuple(map(int, other[1:].split("."))) > newer
        for other in git("tag", "--list", "v*").splitlines()
        if VERSION_RE.fullmatch(other)
    ):
        raise ValueError("a newer stable tag exists; refusing to roll back :latest")
    if source is None:
        source, image = resolve_candidate(sha)
    else:
        if source not in git("rev-list", "--first-parent", sha).splitlines():
            raise ValueError("candidate is not on the tagged commit's first-parent history")
        if _inputs_changed(source, sha):
            raise ValueError("candidate image or gate inputs differ from the tagged commit")
        image = verify_candidate(source, image)
    return {"sha": sha, "version": version, "source": source, "image": image}


def write_manifest(path: Path, tag: str, sha: str, image: str) -> None:
    package, _, digest = image.partition("@")
    if (
        package != PACKAGE
        or not DIGEST_RE.fullmatch(digest)
        or not SHA_RE.fullmatch(sha)
        or not VERSION_RE.fullmatch(tag)
    ):
        raise ValueError("cannot write invalid Dashboard image release metadata")
    path.write_text(
        json.dumps({"image": package, "digest": digest, "commit": sha, "tag": tag}) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    try:
        tag = os.environ["GITHUB_REF_NAME"]
        if len(sys.argv) == 3 and sys.argv[1] == "--write-manifest":
            write_manifest(Path(sys.argv[2]), tag, os.environ["RELEASE_SHA"], os.environ["IMAGE"])
            return 0
        source = image = None
        if sys.argv[1:] == ["--publish-check"]:
            source, image = os.environ["CANDIDATE_SOURCE"], os.environ["IMAGE"]
            if not source or not image:
                raise ValueError("missing previously verified candidate")
        elif sys.argv[1:]:
            raise ValueError("unknown validation option")
        values = validate(tag, source, image)
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            for key, value in values.items():
                print(f"{key}={value}", file=output)
    except (
        BumpError,
        OSError,
        ValueError,
        KeyError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"::error::Cannot validate Dashboard release: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
