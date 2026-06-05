"""Support-floor policy helpers for cohort membership, diagnostics, and benchmarks."""

from __future__ import annotations

from typing import Any

import pandas as pd


SUPPORT_FLOOR_MODE_MEMBERSHIP_GATE = "membership_gate"
SUPPORT_FLOOR_MODE_DIAGNOSTIC_ONLY = "diagnostic_only"
SUPPORT_FLOOR_MODE_BENCHMARK_ELIGIBILITY = "benchmark_eligibility"
SUPPORT_DIAGNOSTIC_FLOORS: tuple[int, ...] = (20, 10, 5, 3, 1)


def resolve_support_floor_mode(
    gates: dict[str, Any] | None,
    *,
    samples_df: pd.DataFrame | None = None,
) -> str:
    """Return normalized support-floor mode for the cohort gates.

    ``samples_df`` is accepted for backward compatibility with reporting callers
    that resolve the active support-floor mode from dataframe attrs after
    preparation. Explicit gate configuration still takes precedence.
    """
    payload = gates if isinstance(gates, dict) else {}
    token = str(payload.get("support_floor_mode", "") or "").strip().lower()
    if not token and isinstance(samples_df, pd.DataFrame):
        token = str(samples_df.attrs.get("support_floor_mode", "") or "").strip().lower()
    if token == SUPPORT_FLOOR_MODE_DIAGNOSTIC_ONLY:
        return SUPPORT_FLOOR_MODE_DIAGNOSTIC_ONLY
    if token == SUPPORT_FLOOR_MODE_BENCHMARK_ELIGIBILITY:
        return SUPPORT_FLOOR_MODE_BENCHMARK_ELIGIBILITY
    return SUPPORT_FLOOR_MODE_MEMBERSHIP_GATE


def resolve_configured_min_samples_per_family(gates: dict[str, Any] | None) -> int | None:
    """Return the explicitly configured family-support floor, if any."""
    payload = gates if isinstance(gates, dict) else {}
    value = payload.get("min_samples_per_family")
    if value in (None, ""):
        return None
    return int(value)


def resolve_membership_min_samples_per_family(gates: dict[str, Any] | None) -> int | None:
    """Return the membership gate support floor, or ``None`` when not applied."""
    mode = resolve_support_floor_mode(gates)
    configured = resolve_configured_min_samples_per_family(gates)
    if mode in {
        SUPPORT_FLOOR_MODE_DIAGNOSTIC_ONLY,
        SUPPORT_FLOOR_MODE_BENCHMARK_ELIGIBILITY,
    }:
        return None
    return configured


def resolve_benchmark_min_samples_per_family(gates: dict[str, Any] | None) -> int | None:
    """Return the benchmark-eligibility support floor, or ``None`` when not applied."""
    mode = resolve_support_floor_mode(gates)
    configured = resolve_configured_min_samples_per_family(gates)
    if mode != SUPPORT_FLOOR_MODE_BENCHMARK_ELIGIBILITY:
        return None
    if configured is None:
        return None
    return max(1, int(configured))


def resolve_diagnostic_min_samples_per_family(
    gates: dict[str, Any] | None,
    *,
    default: int = 3,
) -> int:
    """Return the support floor to use for diagnostics and training safeguards."""
    configured = resolve_configured_min_samples_per_family(gates)
    if configured is not None:
        return max(1, int(configured))
    return max(1, int(default))
