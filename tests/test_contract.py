from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from dashboard.contract import DashboardContract, load_contract

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "path",
    [
        ROOT / "examples/smart-kettle/smart-kettle.dash.json",
        ROOT / "examples/bench-meter/bench-meter.dash.json",
    ],
)
def test_example_contracts_load(path: Path) -> None:
    contract = load_contract(path)

    assert contract.system == "dashboard"
    assert contract.artifact_kind == "dashboard_contract"
    assert contract.protocol.framing == "cobs-crc16"


def test_ios_and_ipados_are_independent_contract_declarations() -> None:
    kettle = load_contract(ROOT / "examples/smart-kettle/smart-kettle.dash.json")
    bench = load_contract(ROOT / "examples/bench-meter/bench-meter.dash.json")
    kettle_platforms = {platform.os: platform for platform in kettle.platforms}
    bench_platforms = {platform.os: platform for platform in bench.platforms}

    assert kettle_platforms["ios"].status == "supported"
    assert kettle_platforms["ipados"].status == "supported"
    assert kettle_platforms["ios"].routes == kettle_platforms["ipados"].routes
    assert bench_platforms["ios"].status == "unsupported"
    assert bench_platforms["ipados"].status == "unsupported"
    assert bench_platforms["ios"].reason
    assert bench_platforms["ipados"].reason


def test_contract_models_reject_unknown_fields_and_invalid_platforms() -> None:
    kettle = load_contract(ROOT / "examples/smart-kettle/smart-kettle.dash.json")
    value = kettle.model_dump(mode="json")
    value["unexpected"] = True

    with pytest.raises(ValidationError):
        DashboardContract.model_validate(value)

    value = kettle.model_dump(mode="json")
    value["platforms"][0]["os"] = "ipad"
    with pytest.raises(ValidationError):
        DashboardContract.model_validate(value)

    value["platforms"][0]["os"] = "bsd"
    assert DashboardContract.model_validate(value).platforms[0].os == "bsd"
