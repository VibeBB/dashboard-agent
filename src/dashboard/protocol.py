from __future__ import annotations

from .contract import DashboardContract
from .interchange import sha256_file


def protocol_export(contract: DashboardContract, contract_sha256: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "system": "dashboard",
        "artifact_kind": "dashboard_protocol",
        "design": contract.name,
        "contract_sha256": contract_sha256,
        "framing": contract.protocol.framing,
        "messages": [message.model_dump(mode="json") for message in contract.protocol.messages],
    }


def protocol_sha(contract_path: str) -> str:
    from pathlib import Path

    return sha256_file(Path(contract_path))
