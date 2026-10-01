from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from dashboard import doctor

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PACKAGES = {
    "typescript": "typescript",
    "esbuild": "esbuild",
    "playwright": "@playwright/test",
}


def _capture_checks(
    monkeypatch: pytest.MonkeyPatch, root: Path, *, run_probes: bool
) -> tuple[dict[str, doctor.ToolCheck], dict[str, str | None]]:
    expected_versions: dict[str, str | None] = {}
    probe_attribute = "_probe"
    original_probe = cast(Callable[..., doctor.ToolCheck], getattr(doctor, probe_attribute))

    def capture(
        name: str,
        argv: list[str],
        *,
        required: bool,
        expected: str | None = None,
    ) -> doctor.ToolCheck:
        if name in RUNTIME_PACKAGES:
            expected_versions[name] = expected
            if run_probes:
                return original_probe(name, argv, required=required, expected=expected)
        return doctor.ToolCheck(name=name, status="ok")

    monkeypatch.setattr(doctor, "__file__", str(root / "src" / "dashboard" / "doctor.py"))
    monkeypatch.setattr(doctor, "_probe", capture)
    checks = {check.name: check for check in doctor.checks()}
    return checks, expected_versions


def test_doctor_expectations_match_runtime_package_pins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = cast(
        dict[str, object],
        json.loads((ROOT / "runtime" / "package.json").read_text(encoding="utf-8")),
    )
    dev_dependencies = cast(dict[str, object], package["devDependencies"])
    expected = {
        "typescript": dev_dependencies["typescript"],
        "esbuild": dev_dependencies["esbuild"],
        "playwright": dev_dependencies["@playwright/test"],
    }
    checks, expected_versions = _capture_checks(monkeypatch, ROOT, run_probes=False)

    assert expected_versions == expected
    assert all(checks[name].status == "ok" for name in RUNTIME_PACKAGES)


def test_runtime_version_prefers_dev_dependencies_and_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    package_path = runtime / "package.json"
    package_path.write_text(
        json.dumps(
            {
                "devDependencies": {"typescript": "dev-pin"},
                "dependencies": {"typescript": "runtime-pin", "esbuild": "0.28.2"},
            }
        ),
        encoding="utf-8",
    )
    _, expected_versions = _capture_checks(monkeypatch, tmp_path, run_probes=False)

    assert expected_versions == {
        "typescript": "dev-pin",
        "esbuild": "0.28.2",
        "playwright": "",
    }


@pytest.mark.parametrize(
    ("package_data", "missing_tools"),
    [
        (None, set(RUNTIME_PACKAGES)),
        ({"devDependencies": {"typescript": "7.1.0", "esbuild": "0.28.2"}}, {"playwright"}),
        ("{invalid", set(RUNTIME_PACKAGES)),
    ],
    ids=["missing-package-json", "missing-pin", "unreadable-package-json"],
)
def test_missing_runtime_pins_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    package_data: dict[str, object] | str | None,
    missing_tools: set[str],
) -> None:
    if package_data is not None:
        runtime = tmp_path / "runtime"
        runtime.mkdir()
        content = package_data if isinstance(package_data, str) else json.dumps(package_data)
        (runtime / "package.json").write_text(content, encoding="utf-8")

    checks, expected_versions = _capture_checks(monkeypatch, tmp_path, run_probes=True)

    for name in missing_tools:
        assert expected_versions[name] == ""
        assert checks[name].status == "fail"
