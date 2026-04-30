"""Evidence-readiness payload builders."""

from __future__ import annotations

from typing import Any


def build_evidence_readiness_payload(
    *,
    status: str,
    failed_checks: list[str],
    checks: dict[str, bool],
    integrity_reason: str,
    run_id: str,
) -> dict[str, Any]:
    """Build normalized readiness payload for machine consumption.

    Args:
        status: Final readiness status.
        failed_checks: List of failed check IDs.
        checks: Check-status mapping.
        integrity_reason: Optional failure reason string.
        run_id: Runtime identifier.

    Returns:
        Deterministic payload dictionary.
    """
    return {
        "run_id": str(run_id),
        "status": str(status),
        "checks": {str(k): bool(v) for k, v in sorted(checks.items(), key=lambda item: item[0])},
        "failed_checks": sorted(set(map(str, failed_checks))),
        "integrity_reason": str(integrity_reason or ""),
    }

