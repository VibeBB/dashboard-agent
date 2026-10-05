"""Dashboard command-line interface."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from . import service


def _emit(payload: service.Json) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload.get("verdict") == "pass" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dashboard")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    sub.add_parser("matrix")
    sub.add_parser("validate").add_argument("contract", type=Path)
    for name in ("generate", "check", "gates", "smoke", "screenshot", "protocol-export"):
        command = sub.add_parser(name)
        command.add_argument("contract", type=Path)
        command.add_argument("--out", type=Path)
    request = sub.add_parser("request")
    request.add_argument("contract", type=Path)
    request.add_argument("--target", required=True)
    request.add_argument("--risk", choices=("low", "high"), required=True)
    request.add_argument("--change", required=True)
    request.add_argument("--rationale", required=True)
    request.add_argument("--failing-check", action="append", default=[])
    request.add_argument("--out", type=Path)
    record = sub.add_parser("record")
    record.add_argument(
        "kind",
        choices=("decision", "impression", "vision-review", "status"),
    )
    record.add_argument("--json", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "doctor":
        return _emit(service.doctor_payload())
    if args.command == "matrix":
        return _emit(service.matrix_payload())
    if args.command == "validate":
        return _emit(service.validate_payload(args.contract))
    if args.command == "record":
        if args.kind == "status":
            return _emit(service.records_status_payload())
        if args.json is None:
            _parser().error(f"record {args.kind} requires --json")
        try:
            value: object = json.loads(args.json.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("record JSON must be an object")
            return _emit(service.record_payload(args.kind, cast(dict[str, object], value)))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return _emit({"verdict": "fail", "stage": "record", "detail": str(exc)})
    if args.command == "generate":
        return _emit(service.generate_payload(args.contract, args.out))
    if args.command == "smoke":
        return _emit(service.smoke_payload(args.contract, args.out))
    if args.command == "screenshot":
        return _emit(service.screenshot_payload(args.contract, args.out))
    if args.command == "protocol-export":
        return _emit(service.protocol_export_payload(args.contract, args.out))
    if args.command in {"check", "gates"}:
        return _emit(
            service.gates_payload(
                args.contract,
                args.out,
                full=args.command == "gates",
            )
        )
    return _emit(
        service.request_payload(
            args.contract,
            args.out,
            target=args.target,
            risk=args.risk,
            change=args.change,
            rationale=args.rationale,
            failing_checks=args.failing_check,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
