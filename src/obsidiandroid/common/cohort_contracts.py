"""Shared locked-cohort contract vocabulary and helpers."""

from __future__ import annotations

from typing import Any

CONTRACT_STATUS_NOT_LOCKED = "not_paper_locked"
CONTRACT_STATUS_MEMBERSHIP_LOCKED = "membership_locked"
CONTRACT_STATUS_COUNT_ONLY = "count_only_incomplete_sample_lock"

ENFORCEMENT_NONE = "none"
ENFORCEMENT_FULL = "full"
ENFORCEMENT_PARTIAL = "partial"


def declared_cohort_contract_status(*, has_sample_lock: bool) -> str:
    """Return the declared contract/cohort-lock status for a profile contract."""
    return CONTRACT_STATUS_MEMBERSHIP_LOCKED if has_sample_lock else CONTRACT_STATUS_COUNT_ONLY


def declared_cohort_enforcement_level(*, has_sample_lock: bool) -> str:
    """Return the declared enforcement level for a profile contract."""
    return ENFORCEMENT_FULL if has_sample_lock else ENFORCEMENT_PARTIAL


def unresolved_cohort_contract_payload(*, profile_id: str) -> dict[str, Any]:
    """Return the standard payload for an exploratory/unlocked profile."""
    return {
        "paper_locked": False,
        "profile_id": profile_id,
        "contract_name": profile_id,
        "contract_id": profile_id,
        "contract_status": CONTRACT_STATUS_NOT_LOCKED,
        "cohort_lock_status": CONTRACT_STATUS_NOT_LOCKED,
        "enforcement_level": ENFORCEMENT_NONE,
        "validation": {"checked": False, "status": CONTRACT_STATUS_NOT_LOCKED, "mismatches": []},
    }


def resolve_contract_cohort_lock_status(contract: dict[str, Any]) -> str:
    """Resolve cohort-lock status from a contract-like payload."""
    status = str(contract.get("cohort_lock_status") or contract.get("contract_status") or "").strip()
    if status:
        return status
    return "locked" if bool(contract.get("paper_locked")) else "not_locked"
