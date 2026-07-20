"""Shared scientific-adequacy posture rules for operator/report surfaces."""

from __future__ import annotations

from typing import Any


def classify_scientific_adequacy(
    *,
    macro_f1: Any,
    supervised_family_claims_suitable: bool,
    dropped_future_only_rows: Any,
) -> tuple[str, list[str]]:
    """Classify scientific adequacy for family-level claims.

    The posture is intentionally stricter than pipeline/publication process status.
    It treats weak family holdout performance and temporal novelty loss as primary
    blockers for family-level scientific interpretation.
    """
    try:
        macro = float(macro_f1 or 0.0)
    except (TypeError, ValueError):
        macro = 0.0
    try:
        dropped = int(dropped_future_only_rows or 0)
    except (TypeError, ValueError):
        dropped = 0

    blockers: list[str] = []
    if macro < 0.40:
        blockers.append(f"headline family Macro-F1 is weak ({macro:.4f})")
    elif macro < 0.60:
        blockers.append(f"headline family Macro-F1 is mixed ({macro:.4f})")
    if not bool(supervised_family_claims_suitable):
        blockers.append(
            "dataset foundation has not passed the stricter supervised-family suitability gate"
        )
    if dropped > 0:
        blockers.append(f"temporal holdout dropped {dropped} future-only family row(s)")

    if macro < 0.40 or (not bool(supervised_family_claims_suitable) and dropped > 0):
        return "Weak", blockers
    if macro < 0.60 or not bool(supervised_family_claims_suitable) or dropped > 0:
        return "Mixed", blockers
    return "Strong", blockers
