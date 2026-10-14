"""Research validity decision for Permission Intel inputs.

The policy is declared before feature construction. A failed lookup is never
equivalent to a verified empty projection, and a development continuation is
never an accepted research result.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd


def permission_frame_status(frame: pd.DataFrame | None, *, degraded: bool) -> str:
    """Distinguish an empty successful query from unavailable or conflicted input."""
    if degraded:
        return "UNAVAILABLE"
    if frame is None or frame.empty:
        return "NO_OBSERVATIONS"
    if frame.attrs.get("permission_feature_contract_version") == (
        "obsidiandroid-permission-exact-v2-unresolved-v1"
    ):
        return "PROVIDER_REPORTED_UNRESOLVED"
    if "perm_status__governance_conflict_count" in frame:
        if frame["perm_status__governance_conflict_count"].sum() > 0:
            return "CONTRADICTORY"
        if frame["perm_status__unresolved_count"].sum() > 0:
            return "INCOMPLETE"
        positive = [name for name in frame if name.startswith(("perm_provider__", "perm_manifest__"))]
        if positive and frame[positive].to_numpy().sum() > 0:
            return "PRESENT"
        if "perm_status__has_manifest_parse" in frame and frame[
            "perm_status__has_manifest_parse"].eq(1).all():
            return "VERIFIED_EMPTY"
        return "INCOMPLETE"
    return "PRESENT" if len(frame.columns) > 1 else "NO_OBSERVATIONS"


def evaluate_permission_run_validity(
    flags: Mapping[str, Any], *, available: bool, degraded: bool,
    evidence_status: str | None = None,
) -> dict[str, str]:
    """Return a durable decision or reject a required PI run before training."""
    enabled = flags.get("enable_permission_features", True)
    if not isinstance(enabled, bool):
        raise TypeError("permission feature enablement must be a boolean")
    policy = flags.get("permission_input_policy")
    if policy is None:
        policy = "development_compatibility" if enabled else "intentionally_disabled"
    if policy not in {"required", "development_compatibility", "intentionally_disabled"}:
        raise ValueError("unknown permission input policy")
    if (policy == "intentionally_disabled") != (not enabled):
        raise ValueError("permission input policy conflicts with feature enablement")
    if not enabled:
        return {"policy": policy, "evidence_status": "INTENTIONALLY_DISABLED",
                "research_validity": "PI_DISABLED_DECLARED"}
    status = evidence_status or ("UNAVAILABLE" if degraded else
                                 "PRESENT" if available else "NO_OBSERVATIONS")
    if status not in {"PRESENT", "VERIFIED_EMPTY", "PROVIDER_REPORTED_UNRESOLVED",
                      "NO_OBSERVATIONS", "UNAVAILABLE",
                      "INCOMPLETE", "CONTRADICTORY", "UNSUPPORTED", "BLOCKED"}:
        raise ValueError("unknown permission evidence status")
    if degraded and status not in {"UNAVAILABLE", "INCOMPLETE", "BLOCKED"}:
        raise ValueError("degraded permission input cannot claim verified evidence")
    permitted = {"PRESENT", "VERIFIED_EMPTY"}
    if flags.get("permission_feature_contract_version") == (
        "obsidiandroid-permission-exact-v2-unresolved-v1"
    ):
        permitted.add("PROVIDER_REPORTED_UNRESOLVED")
    if policy == "required" and status not in permitted:
        raise RuntimeError(f"required Permission Intel input is {status}; training blocked")
    validity = ("ACCEPTED_UNRESOLVED_OCCURRENCE_CONTRACT" if policy == "required"
                and status == "PROVIDER_REPORTED_UNRESOLVED" else
                "ACCEPTED_PI_INPUT" if policy == "required" else
                "DEVELOPMENT_ONLY_NOT_ACCEPTED_RESEARCH")
    return {"policy": policy, "evidence_status": status,
            "research_validity": validity}


def assert_training_permission_validity(decision: Mapping[str, str] | None) -> None:
    """Enforce the runner's PI decision at the last boundary before model fitting."""
    if not decision:
        raise RuntimeError("permission run validity is absent before training")
    policy = decision.get("policy")
    status = decision.get("evidence_status")
    validity = decision.get("research_validity")
    expected = (
        "ACCEPTED_PI_INPUT" if policy == "required" and status in {
            "PRESENT", "VERIFIED_EMPTY"} else
        "ACCEPTED_UNRESOLVED_OCCURRENCE_CONTRACT"
        if policy == "required" and status == "PROVIDER_REPORTED_UNRESOLVED" else
        "DEVELOPMENT_ONLY_NOT_ACCEPTED_RESEARCH"
        if policy == "development_compatibility" and status in {
            "PRESENT", "VERIFIED_EMPTY", "PROVIDER_REPORTED_UNRESOLVED",
            "NO_OBSERVATIONS", "UNAVAILABLE", "INCOMPLETE",
            "CONTRADICTORY", "UNSUPPORTED", "BLOCKED"} else
        "PI_DISABLED_DECLARED"
        if policy == "intentionally_disabled" and status == "INTENTIONALLY_DISABLED"
        else None
    )
    if expected is None or validity != expected:
        if policy == "required":
            raise RuntimeError("required Permission Intel input is invalid before training")
        raise RuntimeError("permission run validity is inconsistent before training")
