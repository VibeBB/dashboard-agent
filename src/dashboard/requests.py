"""Sibling change requests; dashboard never edits another agent's inputs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contract import load_contract, resolve
from .interchange import sha256_file
from .liaison import HashedPath
from .records import LOG_FILES, records_dir
from .workspace import workspace_path, workspace_root


class DashboardRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[2] = 2
    system: Literal["dashboard"] = "dashboard"
    artifact_kind: Literal["dash_request"] = "dash_request"
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    design: str
    target: Literal[
        "bard",
        "circuit",
        "doc",
        "firmware",
        "fpga",
        "mech",
        "prodeng",
        "sim",
        "wire",
        "ux-creator",
    ]
    risk: Literal["low", "high"]
    change: str = Field(min_length=8)
    rationale: str = Field(min_length=8)
    failing_checks: list[str] = Field(default_factory=list)
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    inputs: list[HashedPath] = Field(default_factory=list[HashedPath])
    decision_refs: list[str] = Field(default_factory=list[str])

    @model_validator(mode="after")
    def validate_high_risk_refs(self) -> DashboardRequest:
        if self.risk == "high" and not self.decision_refs:
            raise ValueError("high-risk requests require at least one decision_ref")
        return self


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "request"


def _event_ids(path: Path) -> set[str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    found: set[str] = set()
    for line in lines:
        try:
            value: object = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            event_id = cast(dict[str, object], value).get("event_id")
            if isinstance(event_id, str):
                found.add(event_id)
    return found


def write_request(
    contract_path: Path,
    design: str,
    out_dir: Path,
    *,
    target: str,
    risk: str,
    change: str,
    rationale: str,
    failing_checks: list[str],
    decision_refs: list[str],
) -> tuple[DashboardRequest, Path]:
    base = workspace_root()
    contract_path = workspace_path(contract_path, base)
    contract = load_contract(contract_path)
    inputs = [
        HashedPath(
            path=contract_path.relative_to(base).as_posix(),
            sha256=sha256_file(contract_path),
        )
    ]
    if contract.device.firmware_contract is not None:
        firmware_path = workspace_path(
            resolve(contract_path, contract.device.firmware_contract), base
        )
        if not firmware_path.is_file():
            raise ValueError(
                f"firmware contract does not exist: {contract.device.firmware_contract}"
            )
        inputs.append(
            HashedPath(
                path=firmware_path.relative_to(base).as_posix(),
                sha256=sha256_file(firmware_path),
            )
        )
    known_decisions = _event_ids(records_dir(base) / LOG_FILES["decision"])
    unknown_decisions = sorted(set(decision_refs) - known_decisions)
    if unknown_decisions:
        raise ValueError("unknown decision_refs: " + ", ".join(unknown_decisions))
    request = DashboardRequest.model_validate(
        {
            "id": f"{target}-{_slug(change)}",
            "design": design,
            "target": target,
            "risk": risk,
            "change": change,
            "rationale": rationale,
            "failing_checks": failing_checks,
            "contract_sha256": sha256_file(contract_path),
            "inputs": [item.model_dump(mode="json") for item in inputs],
            "decision_refs": decision_refs,
        }
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{design}.{request.id}.dash-request.json"
    path.write_text(
        json.dumps(request.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return request, path
