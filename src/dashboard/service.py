"""JSON-returning application services shared by the CLI and MCP server."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from . import doctor
from .contract import load_contract
from .gates import FAIL, PASS, run_gates
from .generate import generate
from .interchange import sha256_file
from .matrix import CAVEATS, SUPPORT
from .protocol import protocol_export
from .report import write_outputs
from .requests import write_request

Json = dict[str, object]


def _default_out(contract_path: Path) -> Path:
    return contract_path.resolve().parent / "out"


def doctor_payload() -> Json:
    checks = doctor.checks()
    return {
        "verdict": FAIL if any(check.status == "fail" for check in checks) else PASS,
        "checks": [check.model_dump(mode="json") for check in checks],
    }


def validate_payload(contract_path: Path) -> Json:
    try:
        contract = load_contract(contract_path)
    except (OSError, ValueError, ValidationError) as exc:
        return {"verdict": FAIL, "stage": "validate", "detail": str(exc)}
    return {
        "verdict": PASS,
        "stage": "validate",
        "design": contract.name,
        "messages": len(contract.protocol.messages),
        "transports": [item.kind for item in contract.transports],
        "platforms": [item.os for item in contract.platforms],
    }


def generate_payload(contract_path: Path, out_dir: Path | None = None) -> Json:
    try:
        contract = load_contract(contract_path)
        output, paths = generate(contract_path, out_dir or _default_out(contract_path))
    except (OSError, ValueError, RuntimeError, ValidationError) as exc:
        return {"verdict": FAIL, "stage": "generate", "detail": str(exc)}
    return {
        "verdict": PASS,
        "stage": "generate",
        "design": contract.name,
        "output": str(output),
        "written": [str(path) for path in paths],
    }


def gates_payload(contract_path: Path, out_dir: Path | None = None, *, full: bool = False) -> Json:
    out = out_dir or _default_out(contract_path)
    report = run_gates(contract_path, out, full=full)
    written = write_outputs(report, out)
    payload: Json = json.loads(report.model_dump_json())
    payload["written"] = [str(path) for path in written]
    return payload


def matrix_payload() -> Json:
    rows = [
        {"os": os_name, "browser": browser, "transport": kind, "support": support, "caveat": caveat}
        for (os_name, browser, kind), (support, caveat) in sorted(SUPPORT.items())
    ]
    return {"verdict": PASS, "rows": rows, "caveats": CAVEATS}


def protocol_export_payload(contract_path: Path, out_dir: Path | None = None) -> Json:
    try:
        contract = load_contract(contract_path)
        output = out_dir or _default_out(contract_path)
        output.mkdir(parents=True, exist_ok=True)
        artifact = protocol_export(contract, sha256_file(contract_path))
        path = output / f"{contract.name}.dash-protocol.json"
        path.write_text(
            json.dumps(artifact, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, ValidationError) as exc:
        return {"verdict": FAIL, "stage": "protocol-export", "detail": str(exc)}
    return {"verdict": PASS, "stage": "protocol-export", "written": [str(path)]}


def smoke_payload(contract_path: Path, out_dir: Path | None = None) -> Json:
    try:
        contract = load_contract(contract_path)
        from .servo import smoke

        result = smoke((out_dir or _default_out(contract_path)) / contract.name)
    except (OSError, ValueError, RuntimeError, ValidationError) as exc:
        return {"verdict": FAIL, "stage": "smoke", "detail": str(exc)}
    return {
        "verdict": PASS if result.ok else FAIL,
        "stage": "smoke",
        "detail": result.detail,
    }


def request_payload(
    contract_path: Path,
    out_dir: Path | None,
    *,
    target: str,
    risk: str,
    change: str,
    rationale: str,
    failing_checks: list[str],
) -> Json:
    try:
        contract = load_contract(contract_path)
        request, path = write_request(
            contract_path,
            contract.name,
            out_dir or _default_out(contract_path),
            target=target,
            risk=risk,
            change=change,
            rationale=rationale,
            failing_checks=failing_checks,
        )
    except (OSError, ValueError, ValidationError) as exc:
        return {"verdict": FAIL, "stage": "request", "detail": str(exc)}
    payload: Json = json.loads(request.model_dump_json())
    payload["verdict"] = PASS
    payload["written"] = [str(path)]
    payload["contract_sha256"] = sha256_file(contract_path)
    return payload
