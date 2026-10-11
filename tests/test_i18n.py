from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from dashboard.contract import DashboardContract
from dashboard.gates import run_gates

EXAMPLE = Path(__file__).parents[1] / "examples" / "smart-kettle" / "smart-kettle.dash.json"
JA = {
    "water-temperature": "水温",
    "target-temperature": "目標温度",
    "heating-status": "加熱中",
    "error-code": "エラーコード",
    "set-target": "目標温度を設定",
    "start-boil": "沸騰開始",
}


def _statuses(
    tmp_path: Path, i18n: dict[str, Any] | None = None, widget: dict[str, str] | None = None
) -> dict[str, str]:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    if i18n is not None:
        data["i18n"] = i18n
    for widget_id, label in (widget or {}).items():
        next(item for item in data["widgets"] if item["id"] == widget_id)["label"] = label
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "smart-kettle.dash.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    for name in ("firmware",):
        (tmp_path / name).symlink_to(EXAMPLE.parent / name)
    report = run_gates(path, tmp_path / "out")
    return {check.id: check.status for check in report.checks}


def test_without_i18n_labels_are_not_applicable(tmp_path: Path) -> None:
    statuses = _statuses(tmp_path)
    assert statuses["i18n.labels"] == "not_applicable"
    assert statuses["a11y.names"] == "pass"


def test_complete_locale_passes(tmp_path: Path) -> None:
    statuses = _statuses(tmp_path, {"default_locale": "en", "labels": {"ja": JA}})
    assert statuses["i18n.labels"] == "pass"
    assert statuses["a11y.names"] == "pass"


@pytest.mark.parametrize(
    "labels",
    [
        {k: v for k, v in JA.items() if k != "start-boil"},
        {**JA, "start-boil": "  "},
        {**JA, "ghost": "幽霊"},
    ],
)
def test_incomplete_locale_fails(tmp_path: Path, labels: dict[str, str]) -> None:
    statuses = _statuses(tmp_path, {"default_locale": "en", "labels": {"ja": labels}})
    assert statuses["i18n.labels"] == "fail"


def test_shared_accessible_names_fail(tmp_path: Path) -> None:
    assert _statuses(tmp_path / "a", widget={"error-code": "heating"})["a11y.names"] == "fail"
    clash = {**JA, "error-code": "加熱中"}
    statuses = _statuses(tmp_path / "b", {"default_locale": "en", "labels": {"ja": clash}})
    assert statuses["a11y.names"] == "fail"


@pytest.mark.parametrize(
    "i18n",
    [
        {"default_locale": "english", "labels": {}},
        {"default_locale": "en", "labels": {"ja_JP": JA}},
        {"default_locale": "en", "labels": {"en": JA}},
    ],
)
def test_invalid_locales_are_rejected(i18n: dict[str, Any]) -> None:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["i18n"] = i18n
    with pytest.raises(ValidationError):
        DashboardContract.model_validate(data)
