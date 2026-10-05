"""Dashboard-local validation for Sister Liaison Protocol v2."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Annotated, Literal, cast

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from . import records
from .gates import GateReport
from .workspace import workspace_path, workspace_root

Target = Literal[
    "bard",
    "circuit",
    "dashboard",
    "doc",
    "firmware",
    "fpga",
    "mech",
    "prodeng",
    "sim",
    "wire",
]
Stage = Literal[
    "requirements",
    "design",
    "manufacturing_handoff",
    "build",
    "evaluation",
    "revision",
]
ResponseStatus = Literal["accepted", "in_progress", "done", "rejected", "deferred", "needs_info"]

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
NonEmpty = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]
Purpose = Annotated[str, StringConstraints(min_length=20, strip_whitespace=True)]
_JOB_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_JOB_TOKEN = re.compile(r"(?<![a-z0-9_])[a-z][a-z0-9_]*(?![a-z0-9_])")
_FINAL_STATUSES = {"done", "rejected"}
_MISSING_INPUT_ALLOWED = {"needs_info", "rejected", "deferred"}


def _workspace_relative(value: str) -> str:
    path = Path(value)
    if (
        not value.strip()
        or path.is_absolute()
        or PureWindowsPath(value).is_absolute()
        or PureWindowsPath(value).drive
        or "\\" in value
        or ".." in path.parts
    ):
        raise ValueError("path must be a workspace-relative path without traversal")
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class HashedPath(StrictModel):
    path: NonEmpty
    sha256: Sha256

    @field_validator("path")
    @classmethod
    def validate_workspace_relative_path(cls, value: str) -> str:
        return _workspace_relative(value)


class GateVerdict(StrictModel):
    gate: NonEmpty
    verdict: Literal["pass", "fail", "unknown"]


class UxRequest(StrictModel):
    schema_version: Literal[2] = 2
    system: Literal["ux-creator"] = "ux-creator"
    id: Slug
    target_agent: Target
    stage: Stage
    risk: Literal["low", "high"]
    purpose: Purpose
    rationale: NonEmpty
    requested_changes: list[NonEmpty] = Field(min_length=1)
    inputs: list[HashedPath] = Field(default_factory=list[HashedPath])
    expected_deliverables: list[NonEmpty] = Field(min_length=1)
    acceptance: list[NonEmpty] = Field(min_length=1)
    depends_on: list[Slug] = Field(default_factory=list[Slug])
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_request(self) -> UxRequest:
        if self.id in self.depends_on:
            raise ValueError("depends_on must not contain this request id")
        if self.risk == "high" and not any(
            item.path.lower().endswith(".ux.json") for item in self.inputs
        ):
            raise ValueError("high-risk requests must bind a .ux.json input")
        return self


class UxResponse(StrictModel):
    schema_version: Literal[2] = 2
    system: Literal["ux-creator"] = "ux-creator"
    request: Slug
    responder: Target
    status: ResponseStatus
    reason: str = ""
    input_hashes: dict[str, Sha256] = Field(default_factory=dict[str, Sha256])
    artifacts: list[HashedPath] = Field(default_factory=list[HashedPath])
    gate_verdicts: list[GateVerdict] = Field(default_factory=list[GateVerdict])
    decision_refs: list[str] = Field(default_factory=list[str])
    impression_refs: list[str] = Field(default_factory=list[str])
    questions_for_user: list[NonEmpty] = Field(default_factory=list[NonEmpty])
    responded_at: AwareDatetime

    @field_validator("input_hashes")
    @classmethod
    def validate_input_hash_paths(cls, value: dict[str, str]) -> dict[str, str]:
        for path in value:
            _workspace_relative(path)
        return value

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_response(self) -> UxResponse:
        if self.status not in {"accepted", "in_progress"} and len(self.reason.strip()) < 20:
            raise ValueError("reason must contain at least 20 non-whitespace characters")
        if self.status == "done":
            if not self.artifacts:
                raise ValueError("done responses require at least one artifact")
            if not self.gate_verdicts:
                raise ValueError("done responses require at least one gate verdict")
            if any(item.verdict in {"fail", "unknown"} for item in self.gate_verdicts):
                raise ValueError("done responses cannot contain fail or unknown gate verdicts")
        return self


class UxRespondInput(StrictModel):
    request: Slug
    status: ResponseStatus
    reason: str = ""
    artifacts: list[NonEmpty] = Field(default_factory=list[NonEmpty])
    gate_verdicts: list[GateVerdict] = Field(default_factory=list[GateVerdict])
    decision_refs: list[str] = Field(default_factory=list[str])
    impression_refs: list[str] = Field(default_factory=list[str])
    questions_for_user: list[NonEmpty] = Field(default_factory=list[NonEmpty])
    liaison_dir: str | None = None

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


def _request_file(path: Path, root: Path) -> tuple[UxRequest | None, str | None]:
    try:
        safe_path = workspace_path(path, root)
        value: object = json.loads(safe_path.read_text(encoding="utf-8"))
        request = UxRequest.model_validate(value)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, ValidationError) as exc:
        return None, str(exc)
    expected_name = f"{request.id}.ux-request.json"
    if path.name != expected_name:
        return None, f"request id {request.id!r} does not match filename {path.name!r}"
    if request.risk == "high":
        ux_input = next(
            (item for item in request.inputs if item.path.lower().endswith(".ux.json")),
            None,
        )
        if ux_input is None:
            return None, "high-risk requests must bind a .ux.json input"
        try:
            contract_path = workspace_path(ux_input.path, root)
            value = json.loads(contract_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            return None, f"high-risk UX contract is unreadable: {exc}"
        if not isinstance(value, dict):
            return None, "high-risk UX contract must be a JSON object"
        jobs_value = cast(dict[str, object], value).get("jobs", [])
        if not isinstance(jobs_value, list):
            return None, "high-risk UX contract jobs must be a list"
        job_ids: set[str] = set()
        for job in cast(list[object], jobs_value):
            if isinstance(job, dict):
                job_id = cast(dict[str, object], job).get("id")
                if isinstance(job_id, str) and _JOB_ID.fullmatch(job_id):
                    job_ids.add(job_id)
        rationale_tokens = set(_JOB_TOKEN.findall(request.rationale.lower()))
        if not job_ids.intersection(rationale_tokens):
            return None, "high-risk rationale must cite a UX jobs[].id token"
    return request, None


def _response_file(
    path: Path,
    request_id: str,
    root: Path,
    *,
    dashboard_target: bool,
) -> tuple[UxResponse | None, str | None]:
    try:
        safe_path = workspace_path(path, root)
        value: object = json.loads(safe_path.read_text(encoding="utf-8"))
        response = UxResponse.model_validate(value)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, ValidationError) as exc:
        return None, str(exc)
    if response.request != request_id:
        return None, f"response request {response.request!r} does not match {request_id!r}"
    if dashboard_target and response.responder != "dashboard":
        return None, "dashboard-targeted requests require responder 'dashboard'"
    return response, None


def _liaison_path(root: Path, liaison_dir: Path | str | None) -> Path:
    if liaison_dir is None:
        return workspace_path(root / "liaison", root)
    return workspace_path(liaison_dir, root)


def _current_input_hash(path: str, root: Path) -> str | None:
    try:
        resolved = workspace_path(path, root)
        if not resolved.is_file():
            return None
        return records.sha256_file(resolved)
    except (OSError, ValueError):
        return None


def _input_snapshots(request: UxRequest, root: Path) -> list[dict[str, str | None]]:
    return [
        {
            "path": item.path,
            "sha256": item.sha256,
            "current_sha256": _current_input_hash(item.path, root),
        }
        for item in request.inputs
    ]


def _stale_inputs(
    request: UxRequest,
    snapshots: list[dict[str, str | None]],
    response: UxResponse | None = None,
) -> list[str]:
    stale: list[str] = []
    for item, snapshot in zip(request.inputs, snapshots, strict=True):
        current = snapshot["current_sha256"]
        if current != item.sha256 or (
            response is not None and response.input_hashes.get(item.path) != current
        ):
            stale.append(item.path)
    return stale


def _circular_ids(requests: Mapping[str, UxRequest]) -> set[str]:
    visiting: list[str] = []
    state: dict[str, int] = {}
    circular: set[str] = set()

    def visit(request_id: str) -> None:
        mark = state.get(request_id, 0)
        if mark == 2:
            return
        if mark == 1:
            circular.update(visiting[visiting.index(request_id) :])
            return
        state[request_id] = 1
        visiting.append(request_id)
        for dependency in requests[request_id].depends_on:
            if dependency in requests:
                visit(dependency)
        visiting.pop()
        state[request_id] = 2

    for request_id in requests:
        visit(request_id)
    return circular


def _malformed(path: Path, detail: str) -> dict[str, str]:
    return {"path": str(path), "detail": detail}


def ux_inbox(
    root: Path | None = None,
    liaison_dir: Path | None = None,
) -> dict[str, object]:
    base = (root or workspace_root()).resolve()
    try:
        directory = _liaison_path(base, liaison_dir)
    except ValueError as exc:
        return {"verdict": "fail", "stage": "ux-inbox", "detail": str(exc)}
    if directory.exists() and not directory.is_dir():
        return {
            "verdict": "fail",
            "stage": "ux-inbox",
            "detail": f"liaison path is not a directory: {directory}",
        }
    if not directory.is_dir():
        return {
            "verdict": "pass",
            "stage": "ux-inbox",
            "liaison_dir": str(directory),
            "requests": [],
            "malformed": [],
            "other_targets": 0,
            "counts": {"new": 0, "answered": 0, "stale": 0, "blocked": 0},
            "all_final": True,
            "detail": "liaison directory does not exist",
        }

    malformed: list[dict[str, str]] = []
    requests: dict[str, UxRequest] = {}
    request_paths: dict[str, Path] = {}
    request_hashes: dict[str, str] = {}
    other_targets = 0
    for path in sorted(directory.glob("*.ux-request.json")):
        request, error = _request_file(path, base)
        if error is not None or request is None:
            malformed.append(_malformed(path, error or "invalid request"))
            continue
        try:
            request_hashes[request.id] = records.sha256_file(path)
        except OSError as exc:
            malformed.append(_malformed(path, str(exc)))
            continue
        requests[request.id] = request
        request_paths[request.id] = path
        if request.target_agent != "dashboard":
            other_targets += 1

    responses: dict[str, UxResponse] = {}
    response_paths: dict[str, Path] = {}
    dependency_ids = {
        dependency
        for request in requests.values()
        if request.target_agent == "dashboard"
        for dependency in request.depends_on
    }
    for request_id, request in requests.items():
        if request.target_agent != "dashboard" and request_id not in dependency_ids:
            continue
        response_path = directory / f"{request_id}.ux-response.json"
        if not response_path.exists():
            continue
        response, error = _response_file(
            response_path,
            request_id,
            base,
            dashboard_target=request.target_agent == "dashboard",
        )
        if error is not None or response is None:
            if request.target_agent == "dashboard":
                malformed.append(_malformed(response_path, error or "invalid response"))
            continue
        responses[request_id] = response
        response_paths[request_id] = response_path

    snapshots = {
        request_id: _input_snapshots(request, base) for request_id, request in requests.items()
    }
    stale_by_id = {
        request_id: _stale_inputs(request, snapshots[request_id], responses.get(request_id))
        for request_id, request in requests.items()
    }
    done_ids = {
        request_id
        for request_id, response in responses.items()
        if response.status == "done" and not stale_by_id[request_id]
    }
    circular = _circular_ids(requests)
    entries: list[dict[str, object]] = []
    counts = {"new": 0, "answered": 0, "stale": 0, "blocked": 0}
    for request_id, request in requests.items():
        if request.target_agent != "dashboard":
            continue
        response = responses.get(request_id)
        stale_inputs = stale_by_id[request_id]
        blocked_by = [dependency for dependency in request.depends_on if dependency not in done_ids]
        if response is not None:
            state = "stale" if stale_inputs else "answered"
        elif stale_inputs:
            state = "stale"
        elif blocked_by or request_id in circular:
            state = "blocked"
        else:
            state = "new"
        counts[state] += 1
        entries.append(
            {
                "id": request_id,
                "path": str(request_paths[request_id]),
                "request_sha256": request_hashes[request_id],
                "state": state,
                "final": response is not None and response.status in _FINAL_STATUSES,
                "stage": request.stage,
                "risk": request.risk,
                "purpose": request.purpose,
                "requested_changes": list(request.requested_changes),
                "expected_deliverables": list(request.expected_deliverables),
                "acceptance": list(request.acceptance),
                "depends_on": list(request.depends_on),
                "inputs": snapshots[request_id],
                "stale_inputs": stale_inputs,
                "blocked_by": blocked_by,
                "circular": request_id in circular,
                "response": (
                    {
                        "path": str(response_paths[request_id]),
                        "status": response.status,
                        "responded_at": response.responded_at.isoformat(),
                    }
                    if response is not None
                    else None
                ),
            }
        )
    return {
        "verdict": "fail" if malformed else "pass",
        "stage": "ux-inbox",
        "liaison_dir": str(directory),
        "requests": entries,
        "malformed": malformed,
        "other_targets": other_targets,
        "counts": counts,
        "all_final": all(bool(item["final"]) and item["state"] != "stale" for item in entries),
    }


def _valid_done_dependency(request_id: str, directory: Path, root: Path) -> bool:
    request_path = directory / f"{request_id}.ux-request.json"
    request, error = _request_file(request_path, root)
    if error is not None or request is None:
        return False
    response, error = _response_file(
        directory / f"{request_id}.ux-response.json",
        request_id,
        root,
        dashboard_target=request.target_agent == "dashboard",
    )
    if error is not None or response is None or response.status != "done":
        return False
    return not _stale_inputs(request, _input_snapshots(request, root), response)


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


def _artifact_reference(value: str, root: Path) -> tuple[HashedPath, Path]:
    path = workspace_path(value, root)
    if path.is_file():
        digest = records.sha256_file(path)
    elif path.is_dir():
        digest = records.tree_sha256(path)
    else:
        raise ValueError(f"artifact does not exist: {value}")
    relative = path.relative_to(root).as_posix()
    return HashedPath(path=relative, sha256=digest), path


def _gate_reports(artifacts: list[tuple[HashedPath, Path]]) -> list[GateReport]:
    reports: list[GateReport] = []
    for reference, path in artifacts:
        if not reference.path.endswith(".dash-report.json") or not path.is_file():
            continue
        try:
            report = GateReport.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError, ValidationError):
            continue
        reports.append(report)
    return reports


def ux_respond(payload: Mapping[str, object], root: Path | None = None) -> dict[str, object]:
    try:
        request_input = UxRespondInput.model_validate(dict(payload))
    except ValidationError as exc:
        return {"verdict": "fail", "stage": "ux-respond", "detail": str(exc)}
    base = (root or workspace_root()).resolve()
    try:
        directory = _liaison_path(base, request_input.liaison_dir)
        request_path = directory / f"{request_input.request}.ux-request.json"
        if not request_path.is_file():
            raise ValueError(f"UX request does not exist: {request_path}")
        request, error = _request_file(request_path, base)
        if error is not None or request is None:
            raise ValueError(error or "invalid UX request")
        if request.target_agent != "dashboard":
            raise ValueError("UX request is not targeted to dashboard")

        input_hashes: dict[str, str] = {}
        missing_inputs: list[str] = []
        stale_inputs: list[str] = []
        for item in request.inputs:
            current = _current_input_hash(item.path, base)
            if current is None:
                missing_inputs.append(item.path)
                continue
            input_hashes[item.path] = current
            if current != item.sha256:
                stale_inputs.append(item.path)
        if missing_inputs and request_input.status not in _MISSING_INPUT_ALLOWED:
            raise ValueError(
                f"request inputs are missing or unreadable: {', '.join(missing_inputs)}"
            )
        if request_input.status == "done":
            if stale_inputs:
                raise ValueError(
                    "request inputs are stale; re-read them and respond with needs_info: "
                    + ", ".join(stale_inputs)
                )
            missing_dependencies = [
                dependency
                for dependency in request.depends_on
                if not _valid_done_dependency(dependency, directory, base)
            ]
            if missing_dependencies:
                raise ValueError("dependencies are not done: " + ", ".join(missing_dependencies))
            if not request_input.decision_refs:
                raise ValueError("done responses require at least one decision_ref")
            if not request_input.impression_refs:
                raise ValueError("done responses require at least one impression_ref")

        decision_log = records.records_dir(base) / records.LOG_FILES["decision"]
        impression_log = records.records_dir(base) / records.LOG_FILES["stage_impression"]
        vision_log = records.records_dir(base) / records.LOG_FILES["vision_review"]
        valid_decisions = _event_ids(decision_log)
        valid_impressions = _event_ids(impression_log) | _event_ids(vision_log)
        unknown_decisions = sorted(set(request_input.decision_refs) - valid_decisions)
        unknown_impressions = sorted(set(request_input.impression_refs) - valid_impressions)
        if unknown_decisions:
            raise ValueError("unknown decision_refs: " + ", ".join(unknown_decisions))
        if unknown_impressions:
            raise ValueError("unknown impression_refs: " + ", ".join(unknown_impressions))

        artifact_refs = [_artifact_reference(value, base) for value in request_input.artifacts]
        reports = _gate_reports(artifact_refs)
        if request_input.status == "done":
            if not any(report.verdict == "pass" and report.scope == "full" for report in reports):
                raise ValueError("done responses require a passing full .dash-report.json artifact")
            for claimed in request_input.gate_verdicts:
                for report in reports:
                    for check in report.checks:
                        if check.id == claimed.gate and check.status != claimed.verdict:
                            raise ValueError(
                                f"gate verdict for {claimed.gate!r} does not match "
                                f"dashboard report status {check.status!r}"
                            )

        response = UxResponse(
            request=request.id,
            responder="dashboard",
            status=request_input.status,
            reason=request_input.reason,
            input_hashes=input_hashes,
            artifacts=[reference for reference, _ in artifact_refs],
            gate_verdicts=request_input.gate_verdicts,
            decision_refs=request_input.decision_refs,
            impression_refs=request_input.impression_refs,
            questions_for_user=request_input.questions_for_user,
            responded_at=datetime.now(UTC),
        )
        directory.mkdir(parents=True, exist_ok=True)
        response_path = directory / f"{request.id}.ux-response.json"
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=directory,
                prefix=f".{request.id}.",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                stream.write(
                    json.dumps(response.model_dump(mode="json"), indent=2, ensure_ascii=False)
                    + "\n"
                )
            os.replace(temporary_path, response_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return {
            "verdict": "pass",
            "stage": "ux-respond",
            "path": str(response_path),
            "response": response.model_dump(mode="json"),
        }
    except (OSError, ValueError, ValidationError) as exc:
        return {"verdict": "fail", "stage": "ux-respond", "detail": str(exc)}
