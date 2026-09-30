"""Sibling change requests; dashboard never edits another agent's inputs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .interchange import sha256_file


class DashboardRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    system: Literal["dashboard"] = "dashboard"
    artifact_kind: Literal["dash_request"] = "dash_request"
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    design: str
    target: Literal["firmware", "circuit", "ux-creator", "mech", "wire", "bard"]
    risk: Literal["low", "high"]
    change: str = Field(min_length=8)
    rationale: str = Field(min_length=8)
    failing_checks: list[str] = Field(default_factory=list)
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "request"


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
) -> tuple[DashboardRequest, Path]:
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
        }
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{design}.{request.id}.dash-request.json"
    path.write_text(
        json.dumps(request.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return request, path
