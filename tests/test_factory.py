from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from dashboard.gates import run_gates
from dashboard.generate import generate

EXAMPLE = Path(__file__).parents[1] / "examples" / "smart-kettle" / "smart-kettle.dash.json"
SPEC = Path(__file__).parent / "fixtures" / "prodeng" / "factory-test-spec.json"


def _contract(tmp_path: Path, transport: str = "kettle-serial", **spec_changes: Any) -> Path:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    spec.update(spec_changes)
    raw = json.dumps(spec).encode()
    (tmp_path / "factory-test-spec.json").write_bytes(raw)
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["factory"] = {
        "spec": "factory-test-spec.json",
        "spec_sha256": hashlib.sha256(raw).hexdigest(),
        "transport": transport,
    }
    (tmp_path / "firmware").symlink_to(EXAMPLE.parent / "firmware")
    path = tmp_path / "smart-kettle.dash.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _factory(path: Path) -> tuple[str, str]:
    report = run_gates(path, path.parent / "out")
    check = next(item for item in report.checks if item.id == "factory.spec")
    return check.status, "; ".join(check.evidence) + (check.detail or "")


def test_without_factory_view_is_not_applicable(tmp_path: Path) -> None:
    report = run_gates(EXAMPLE, tmp_path)
    assert next(c for c in report.checks if c.id == "factory.spec").status == "not_applicable"


def test_pinned_uart_spec_on_web_serial_passes(tmp_path: Path) -> None:
    assert _factory(_contract(tmp_path))[0] == "pass"


def test_changed_or_missing_spec_fails(tmp_path: Path) -> None:
    path = _contract(tmp_path)
    spec = tmp_path / "factory-test-spec.json"
    spec.write_text(spec.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert _factory(path)[0] == "fail"
    assert "sha256 mismatch" in _factory(path)[1]
    spec.unlink()
    assert "file not found" in _factory(path)[1]


@pytest.mark.parametrize(
    ("transport", "changes", "problem"),
    [
        ("kettle-ble", {}, "must be a declared web_serial"),
        ("kettle-tauri-serial", {}, "must be a declared web_serial"),
        ("kettle-serial", {"interface": {"transport": "ble", "settings": ""}}, "uart only"),
        (
            "kettle-serial",
            {"interface": {"transport": "uart", "settings": "9600 baud, 8N1"}},
            "spec baud 9600",
        ),
        ("kettle-serial", {"interface": {"transport": "uart", "settings": "8N1"}}, "no baud"),
        ("kettle-serial", {"declared": False}, "declares no factory"),
        ("kettle-serial", {"commands": []}, "lists no commands"),
        ("kettle-serial", {"commands": [{"id": "TC-01", "timeout_ms": 0}]}, "malformed"),
    ],
)
def test_unusable_spec_fails(
    tmp_path: Path, transport: str, changes: dict[str, Any], problem: str
) -> None:
    status, detail = _factory(_contract(tmp_path, transport, **changes))
    assert status == "fail"
    assert problem in detail


@pytest.mark.parametrize(("timeout_ms", "status"), [(-1, "fail"), (0, "fail"), (1, "pass")])
def test_command_timeout_must_be_positive(tmp_path: Path, timeout_ms: int, status: str) -> None:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    commands = [{**spec["commands"][0], "timeout_ms": timeout_ms}]
    assert _factory(_contract(tmp_path, commands=commands))[0] == status


def test_generate_embeds_the_commands_and_refuses_a_broken_spec(tmp_path: Path) -> None:
    path = _contract(tmp_path)
    output, _ = generate(path, tmp_path / "out")
    config = json.loads((output / "dashboard.config.json").read_text(encoding="utf-8"))
    assert config["factory"]["transport"] == "kettle-serial"
    assert [item["id"] for item in config["factory"]["commands"]] == ["TC-01", "TC-02"]
    (tmp_path / "factory-test-spec.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="factory spec unusable"):
        generate(path, tmp_path / "out")
