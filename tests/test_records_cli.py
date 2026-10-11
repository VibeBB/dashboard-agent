"""Dashboard record service, Stop-hook and policy drift checks."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from dashboard import records, service

SCRIPTS = Path(__file__).parents[1] / "plugins" / "dashboard" / "hooks" / "scripts"
HOOK = SCRIPTS / "require_records.py"

IMPRESSION = (
    "The harness drawing reads as a coherent build sheet: the power pair and the "
    "signal pair are visibly separated, and every cavity carries a unique label. "
    "What worries me is the 3.3 V sense lead, which runs parallel to the motor "
    "feed for most of its length and could pick up switching noise. A fabricator "
    "would still be able to cut and crimp from the tables alone, although the "
    "splice note is small. Next I would re-route the sense lead along the far "
    "edge of the bundle and re-render to confirm the separation. Overall the sheet "
    "communicates intent well, and the remaining risk sits in one routing choice."
)
IMPRESSION_JA = (
    "電源ペアと信号ペアが明確に分かれており、配線表だけで切断・圧着まで進められる構成だと感じた。"
    "一方でセンス線がモータ給電線と長く並走しており、スイッチングノイズを拾う懸念が残る。"
    "製造現場の作業者は端子番号を迷わず読めるが、スプライス注記の文字が小さく見落とされやすい。"
    "次の工程ではセンス線を束の反対側へ移し、再描画して分離が保たれているかを確認したい。"
    "全体としては設計意図が伝わる図面であり、誤読のリスクは注記の大きさに集中している。"
    "コネクタの嵌合方向は矢印で示されているが、裏面視か表面視かの明記が無いので追記したい。"
    "ケーブル長の基準点は嵌合面に揃っており、治具板への展開もそのまま行えると判断した。"
    "ただしシールドの終端処理は図から読み取れず、仕様書を別途参照させる必要がある。"
    "白黒印刷で色識別が失われた場合でも、線番と端子番号の併記によって配線の取り違えは防げると考える。"
    "最後に、検査工程で導通試験の手順を参照できるよう、試験点の一覧を図面の余白へ追加することを提案したい。"
)


def _hook_module() -> ModuleType:
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("_records", SCRIPTS / "_records.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HOOK_RECORDS = _hook_module()


def _decision(evidence_path: str) -> dict[str, Any]:
    return {
        "id": "sense-lead-routing",
        "stage": "design",
        "question": "Where should the 3.3 V sense lead run inside the bundle?",
        "principles": [
            "Inductive coupling falls with separation and shorter parallel run length",
            "IPC/WHMA-A-620 segregation of power and signal conductors",
        ],
        "options": [
            {"name": "same-bundle", "pros": ["shortest"], "cons": ["noise coupling"]},
            {"name": "far-edge", "pros": ["separation"], "cons": ["+40 mm length"]},
        ],
        "chosen": "far-edge",
        "rationale": (
            "The sense lead feeds an ADC whose LSB is about 0.8 mV, while the motor feed "
            "switches several amperes at 20 kHz; mutual inductance along a 300 mm parallel "
            "run would inject more than an LSB, so physical separation is the cheapest fix."
        ),
        "evidence": [{"path": evidence_path}, {"reference": "IPC/WHMA-A-620E section 13"}],
        "assumptions": ["motor PWM is 20 kHz"],
        "unknowns": ["actual motor current ripple"],
        "risks": ["longer lead adds 40 mm of copper"],
        "revisit_when": "a measured ADC noise floor exceeds 2 LSB",
    }


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("OPENHANDS_PROJECT_DIR", str(tmp_path))
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "demo").mkdir()
    (tmp_path / "out" / "demo" / "demo.dash-report.json").write_text("{}", encoding="utf-8")
    (tmp_path / "out" / "demo.screens").mkdir()
    (tmp_path / "out" / "demo.screens" / "desktop.png").write_bytes(b"\x89PNG fake")
    return tmp_path


def test_record_service_returns_record_stage_and_failures(workspace: Path) -> None:
    success = service.record_payload(
        "decision",
        _decision("out/demo/demo.dash-report.json"),
    )
    assert success["verdict"] == "pass"
    assert success["stage"] == "record"
    assert isinstance(success["record"], dict)

    invalid = service.record_payload("decision", {"id": "invalid"})
    assert invalid["verdict"] == "fail"
    assert invalid["stage"] == "record"
    assert isinstance(invalid["detail"], str)


def _hook(mode: str, root: Path, session: str = "s1") -> subprocess.CompletedProcess[str]:
    env = dict(os.environ) | {"OPENHANDS_PROJECT_DIR": str(root)}
    return subprocess.run(
        [sys.executable, str(HOOK), mode],
        input=json.dumps({"session_id": session, "working_dir": str(root)}),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _status(root: Path) -> dict[str, Any]:
    path = root / records.RECORDS_DIR / "records-status.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_stop_without_marker_allows(tmp_path: Path) -> None:
    assert _hook("stop", tmp_path).returncode == 0


def test_stop_clean_session_passes(tmp_path: Path) -> None:
    assert _hook("session-start", tmp_path).returncode == 0
    result = _hook("stop", tmp_path)
    assert result.returncode == 0, result.stdout
    assert _status(tmp_path)["verdict"] == "pass"


def test_records_policy_matches_core() -> None:
    policy = HOOK_RECORDS.load_policy(SCRIPTS.parents[1])
    assert policy["plugin"] == records.PLUGIN
    assert policy["records_dir"] == records.RECORDS_DIR.as_posix()
    assert HOOK_RECORDS.IMPRESSION_MIN_CHARS == records.IMPRESSION_MIN_CHARS
    assert HOOK_RECORDS.IMPRESSION_MIN_SENTENCES == records.IMPRESSION_MIN_SENTENCES
    assert HOOK_RECORDS.RATIONALE_MIN_CHARS == records.RATIONALE_MIN_CHARS
    assert HOOK_RECORDS.LOG_FILES == records.LOG_FILES
    hooks = json.loads((SCRIPTS.parent / "hooks.json").read_text(encoding="utf-8"))
    for event, mode in (("session_start", "session-start"), ("stop", "stop")):
        commands = [h["command"] for g in hooks[event] for h in g["hooks"]]
        assert any(f'require_records.py" {mode}' in c for c in commands)
