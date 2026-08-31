"""Credential-redacted live readiness probe for Permission Intel v1."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .adapter import PermissionIntelV1Adapter


def run_probe(adapter: Any, permission: str) -> dict[str, object]:
    """Exercise the gate and every v1 read surface without exposing DB settings."""
    canonical = str(permission or "").strip()
    if not canonical:
        raise ValueError("permission must not be blank")

    gate = adapter.read_catalog_gate()
    status = gate.catalog_status
    payload: dict[str, object] = {
        "status": "PASS" if gate.shadow_available else "BLOCKED",
        "gate_state": gate.state.value,
        "shadow_available": bool(gate.shadow_available),
        "diagnostic_codes": list(gate.diagnostic_codes),
        "catalog_release_id": None if status is None else status.catalog_release_id,
        "schema_contract_version": (
            None if status is None else status.schema_contract_version
        ),
        "exhaustive_scope": None if status is None else bool(status.exhaustive_scope),
        "permission": canonical,
    }
    if not gate.shadow_available:
        payload.update(
            {
                "exact_match": False,
                "case_folded_match": False,
                "authority_class": None,
                "split_relation_count": 0,
                "source_evidence_count": 0,
            }
        )
        return payload

    exact = adapter.get_permission(canonical)
    folded = adapter.get_permission(canonical.lower())
    payload.update(
        {
            "exact_match": exact is not None,
            "case_folded_match": folded is not None,
            "authority_class": (
                None if exact is None else exact.authority_class.value
            ),
            "split_relation_count": len(adapter.get_split_relations(canonical)),
            "source_evidence_count": len(adapter.get_source_evidence(canonical)),
        }
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a SELECT-only Permission Intel v1 gate and anchor probe."
    )
    parser.add_argument(
        "--permission",
        default="android.permission.INTERNET",
        help="Exact-case permission identity used for the bounded anchor lookup.",
    )
    parser.add_argument("--json", action="store_true", help="Emit one JSON object.")
    args = parser.parse_args(argv)

    try:
        payload = run_probe(PermissionIntelV1Adapter(), args.permission)
    except Exception as exc:
        payload = {
            "status": "ERROR",
            "error_class": exc.__class__.__name__,
            "message": "Permission Intel v1 probe failed; inspect redacted DB health logs.",
        }
        exit_code = 1
    else:
        exit_code = 0 if payload["status"] == "PASS" else 2

    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
