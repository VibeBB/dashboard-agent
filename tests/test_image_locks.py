from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import cast

import pytest
from scripts.measure_image_tools import measure
from scripts.print_locked_image import locked_image
from scripts.update_image_digest_lock import update_lock

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "docker/image-digests.json"
PLUGIN_PIN = ROOT / "plugins/dashboard/tools-image.json"
IMAGE = "ghcr.io/vibebb/dashboard-tools"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _write_null_lock(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "dashboard_tools": {
                    "image": IMAGE,
                    "digest": None,
                    "tag": None,
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_initial_lock_entry_shape_and_plugin_consistency() -> None:
    root_entry = json.loads(LOCK.read_text(encoding="utf-8"))["dashboard_tools"]
    plugin_entry = json.loads(PLUGIN_PIN.read_text(encoding="utf-8"))

    assert root_entry["image"] == IMAGE
    digest = root_entry["digest"]
    tag = root_entry["tag"]
    if digest is None:
        assert tag is None
    else:
        assert isinstance(digest, str) and _DIGEST.fullmatch(digest)
        assert isinstance(tag, str) and tag
    assert {key: plugin_entry.get(key) for key in ("image", "digest", "tag")} == {
        key: root_entry.get(key) for key in ("image", "digest", "tag")
    }


def test_print_locked_image_rejects_literal_null_fixture(tmp_path: Path) -> None:
    lock = tmp_path / "image-digests.json"
    _write_null_lock(lock)

    with pytest.raises(ValueError, match="not digest-pinned"):
        locked_image(lock, "dashboard_tools")


def test_update_lock_populates_literal_null_fixture(tmp_path: Path) -> None:
    lock = tmp_path / "image-digests.json"
    _write_null_lock(lock)

    assert update_lock(
        lock,
        entry="dashboard_tools",
        image=IMAGE,
        tag="abc-tools",
        digest=f"sha256:{'a' * 64}",
        published_at="2026-10-01T12:00:00Z",
        workflow_run="https://github.com/VibeBB/dashboard-agent/actions/runs/1",
        dockerfile="docker/dashboard-tools.Dockerfile",
        tools={"node": "v26.10.0"},
    )
    assert locked_image(lock, "dashboard_tools") == f"{IMAGE}@sha256:{'a' * 64}"
    assert not update_lock(
        lock,
        entry="dashboard_tools",
        image=IMAGE,
        tag="abc-tools",
        digest=f"sha256:{'a' * 64}",
        published_at="2026-10-01T12:00:00Z",
        workflow_run="https://github.com/VibeBB/dashboard-agent/actions/runs/1",
        dockerfile="docker/dashboard-tools.Dockerfile",
        tools={"node": "v26.10.0"},
    )


def test_update_lock_rejects_invalid_digest(tmp_path: Path) -> None:
    lock = tmp_path / "image-digests.json"
    _write_null_lock(lock)

    with pytest.raises(ValueError, match="non-placeholder"):
        update_lock(
            lock,
            entry="dashboard_tools",
            image=IMAGE,
            tag="abc-tools",
            digest=f"sha256:{'0' * 64}",
            published_at="2026-10-01T12:00:00Z",
            workflow_run="run",
            dockerfile="docker/dashboard-tools.Dockerfile",
            tools={"node": "v26"},
        )


def test_measurement_records_commands_and_outputs(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "probe output\n", "")

    monkeypatch.setattr("scripts.measure_image_tools.subprocess.run", run)
    result = measure("dashboard-tools:local")
    raw_measurements = result["measurements"]

    assert isinstance(raw_measurements, dict)
    measurements = cast(dict[str, dict[str, str]], raw_measurements)
    assert set(measurements) == {
        "python",
        "uv",
        "dashboard_agent",
        "node",
        "npm",
        "typescript",
        "playwright",
        "chromium",
        "emcc",
        "servoshell",
    }
    assert all(item["output"] == "probe output" for item in measurements.values())
    assert all(command[command.index("--network") + 1] == "none" for command in calls)


def test_measure_rejects_unpinned_remote_ref() -> None:
    with pytest.raises(ValueError, match="digest-pinned"):
        measure("ghcr.io/vibebb/dashboard-tools:latest")
