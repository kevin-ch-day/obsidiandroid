"""Policy resolution helpers for profile-driven governance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GovernancePolicy:
    """Resolved governance policy for a single run.

    Attributes:
        evidence_mode: Whether profile is marked as evidence mode.
        strict_evidence_mode: Evidence mode with overrides disallowed.
        allow_vendor_fallback_for_width: Whether vendor width fallback is allowed.
        allow_adaptive_top_k: Whether effective top-k may be lower than requested.
        requested_top_k: Requested top-k for vendor selection.
        exclude_unknown_from_main_results: Whether unknown families are excluded.
        allow_global_artifacts: Whether global artifacts are temporarily allowed.
        override_used: Whether a runtime override path is active.
    """

    evidence_mode: bool
    strict_evidence_mode: bool
    allow_vendor_fallback_for_width: bool
    allow_adaptive_top_k: bool
    requested_top_k: int
    exclude_unknown_from_main_results: bool
    allow_global_artifacts: bool
    override_used: bool


def resolve_policy(profile: dict[str, Any], runtime_flags: dict[str, Any]) -> GovernancePolicy:
    """Resolve governance policy from profile and runtime flags.

    Args:
        profile: Loaded profile dictionary.
        runtime_flags: Runtime CLI/environment flags.

    Returns:
        Immutable resolved policy object.
    """
    evidence_mode = bool(profile.get("evidence_mode", False))
    override_used = bool(runtime_flags.get("override_used", False))
    strict_evidence_mode = bool(evidence_mode and not override_used)
    return GovernancePolicy(
        evidence_mode=evidence_mode,
        strict_evidence_mode=strict_evidence_mode,
        allow_vendor_fallback_for_width=bool(
            profile.get("allow_vendor_fallback_for_width", True)
        ),
        allow_adaptive_top_k=bool(profile.get("allow_adaptive_top_k", True)),
        requested_top_k=int(profile.get("top_k_requested", 8) or 8),
        exclude_unknown_from_main_results=bool(
            profile.get("exclude_unknown_from_main_results", False)
        ),
        allow_global_artifacts=bool(runtime_flags.get("allow_global_artifacts", False)),
        override_used=override_used,
    )

