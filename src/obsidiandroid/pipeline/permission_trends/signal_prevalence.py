"""Summarize and validate permission signal prevalence by type and family."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import numpy as np
import pandas as pd

from obsidiandroid.reporting.package_balanced_permission_analysis import compute_hhi

from .constants import SIGNAL_EVIDENCE_CONTRACT_VERSION
from .pattern_framework import annotate_prevalence_patterns
from .sample_permission_data import family_support_frame
from .signal_assignments import (
    prepare_signal_assignments,
    prepare_signal_sample_core,
    signal_catalog_frame,
)


def filter_behavior_safe_signals(signal_prevalence_df: pd.DataFrame) -> pd.DataFrame:
    """Select signal rows marked safe for behavior-facing reports."""
    if not isinstance(signal_prevalence_df, pd.DataFrame) or signal_prevalence_df.empty:
        return pd.DataFrame(columns=getattr(signal_prevalence_df, "columns", []))
    return signal_prevalence_df[
        pd.to_numeric(signal_prevalence_df["include_in_behavioral_claims"], errors="coerce")
        .fillna(0)
        .astype(bool)
    ].copy()


class _GroupPackages:
    """Keep one package denominator and ordering for all signals in a group."""

    def __init__(self, group: pd.DataFrame):
        known = group.loc[~group["is_missing_package"].astype(bool), ["sample_id", "package_key"]]
        self.sample_ids = pd.Index(known["sample_id"])
        # Preserve the package ordering used by the previous grouped mean.
        self.codes, _ = pd.factorize(known["package_key"], sort=True)
        self.counts = np.bincount(self.codes)
        self.coverage = {
            "known_package_sample_count": len(known),
            "known_package_count": len(self.counts),
            "largest_package_sample_share_pct": float("nan"),
            "package_hhi": float("nan"),
            "effective_package_count": float("nan"),
        }
        if len(known):
            hhi = compute_hhi(np.sort(self.counts)[::-1])
            self.coverage.update(
                largest_package_sample_share_pct=round(float(self.counts.max() / len(known)) * 100.0, 6),
                package_hhi=round(hhi, 9),
                effective_package_count=round(1.0 / hhi, 6),
            )

    def signal_metrics(
        self, eligible_sample_ids: set[int], observed_sample_ids: set[int]
    ) -> dict[str, float | int]:
        if not len(self.counts):
            return {
                **self.coverage,
                "package_positive_count": 0,
                "package_balanced_prevalence_pct": float("nan"),
                "observed_package_balanced_prevalence_pct": float("nan"),
            }
        eligible = self._count_by_package(eligible_sample_ids)
        observed = self._count_by_package(observed_sample_ids)
        return {
            **self.coverage,
            "package_positive_count": int(np.count_nonzero(eligible)),
            "package_balanced_prevalence_pct": round(float((eligible / self.counts).mean()) * 100.0, 6),
            "observed_package_balanced_prevalence_pct": round(float((observed / self.counts).mean()) * 100.0, 6),
        }

    def _count_by_package(self, sample_ids: set[int]) -> np.ndarray:
        matching = self.sample_ids.isin(sample_ids)
        return np.bincount(self.codes[matching], minlength=len(self.counts))


def _index_signal_assignments(
    permission_signal_rows_df: pd.DataFrame,
) -> dict[str, dict[str, set[int]]]:
    assignments = prepare_signal_assignments(permission_signal_rows_df)
    return {
        str(key): {
            "observed": set(group["sample_id"]),
            "eligible": set(group.loc[group["assignment_model_eligible"], "sample_id"]),
            "candidate": set(group.loc[group["signal_evidence_tier"].eq("candidate_governance"), "sample_id"]),
            "raw_pattern": set(group.loc[group["signal_evidence_tier"].eq("raw_pattern"), "sample_id"]),
        }
        for key, group in assignments.groupby("signal_key", sort=False)
    }


def _group_signal_prevalence(
    group: pd.DataFrame,
    support: int,
    catalog_df: pd.DataFrame,
    assignments: dict[str, dict[str, set[int]]],
) -> Iterator[dict[str, Any]]:
    group_sample_ids = set(group["sample_id"])
    packages = _GroupPackages(group)
    denominator = float(max(support, 1))
    for signal in catalog_df.itertuples(index=False):
        signal_key = str(signal.signal_key)
        signal_assignments = assignments.get(signal_key, {})
        observed = group_sample_ids.intersection(signal_assignments.get("observed", ()))
        eligible = group_sample_ids.intersection(signal_assignments.get("eligible", ()))
        candidate = group_sample_ids.intersection(signal_assignments.get("candidate", ()))
        raw_pattern = group_sample_ids.intersection(signal_assignments.get("raw_pattern", ()))
        package_metrics = packages.signal_metrics(eligible, observed)
        prevalence_pct = round(len(eligible) / denominator * 100.0, 6)
        yield {
            "signal_key": signal_key,
            "signal_label": str(signal.display_name),
            "authority_lane": str(signal.authority_lane),
            "include_in_model_features": bool(signal.include_in_model_features),
            "include_in_behavioral_claims": bool(signal.include_in_behavioral_claims),
            "positive_count": len(eligible),
            "observed_positive_count": len(observed),
            "candidate_positive_count": len(candidate),
            "raw_pattern_positive_count": len(raw_pattern),
            "prevalence_pct": prevalence_pct,
            "observed_prevalence_pct": round(len(observed) / denominator * 100.0, 6),
            **package_metrics,
            "sample_minus_package_balanced_pp": round(
                prevalence_pct - float(package_metrics["package_balanced_prevalence_pct"]),
                6,
            ),
            "signal_evidence_contract_version": SIGNAL_EVIDENCE_CONTRACT_VERSION,
            "assignment_evidence_policy": "model_eligible_assignments_only",
        }


def build_signal_prevalence_by_type(
    sample_core_df: pd.DataFrame,
    permission_signal_rows_df: pd.DataFrame,
    *,
    catalog_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Summarize model-eligible and observed signal prevalence by type."""
    if catalog_df is None:
        catalog_df = signal_catalog_frame()
    sample_membership = prepare_signal_sample_core(sample_core_df, grouping_columns=["type_slug"])
    assignments = _index_signal_assignments(permission_signal_rows_df)
    rows: list[dict[str, Any]] = []
    for type_slug, group in sample_membership.groupby("type_slug", dropna=False):
        support = int(group["sample_id"].nunique())
        rows.extend(
            {"type_slug": str(type_slug), **metrics, "type_sample_count": support}
            for metrics in _group_signal_prevalence(group, support, catalog_df, assignments)
        )
    report = pd.DataFrame(rows)
    if not report.empty:
        # Preserve the established export column order.
        report.insert(
            report.columns.get_loc("positive_count"), "type_sample_count", report.pop("type_sample_count")
        )
    return annotate_prevalence_patterns(
        report,
        support_col="type_sample_count",
        basis="signal_prevalence_by_type",
    )


def build_signal_prevalence_by_family(
    sample_core_df: pd.DataFrame,
    permission_signal_rows_df: pd.DataFrame,
    *,
    benchmark_min_support: int = 3,
    catalog_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Summarize model-eligible and observed signal prevalence by family."""
    family_support_df = family_support_frame(sample_core_df, benchmark_min_support=benchmark_min_support)
    if catalog_df is None:
        catalog_df = signal_catalog_frame()
    if family_support_df.empty:
        return pd.DataFrame(
            columns=[
                "family_canonical",
                "type_slug",
                "family_support",
                "benchmark_eligible_n_ge_3",
                "signal_key",
                "signal_label",
                "authority_lane",
                "include_in_model_features",
                "include_in_behavioral_claims",
                "positive_count",
                "observed_positive_count",
                "candidate_positive_count",
                "raw_pattern_positive_count",
                "prevalence_pct",
                "observed_prevalence_pct",
                "known_package_sample_count",
                "known_package_count",
                "largest_package_sample_share_pct",
                "package_hhi",
                "effective_package_count",
                "package_positive_count",
                "package_balanced_prevalence_pct",
                "observed_package_balanced_prevalence_pct",
                "sample_minus_package_balanced_pp",
                "signal_evidence_contract_version",
                "assignment_evidence_policy",
            ]
        )
    sample_membership = prepare_signal_sample_core(
        sample_core_df,
        grouping_columns=["family_id", "family_canonical"],
    )
    merged = (
        sample_membership
        .merge(family_support_df, on=["family_id", "family_canonical"], how="inner")
    )
    assignments = _index_signal_assignments(permission_signal_rows_df)
    rows: list[dict[str, Any]] = []
    for (family_name, type_slug, family_support, benchmark_eligible), group in merged.groupby(
        ["family_canonical", "type_slug", "family_support", "benchmark_eligible_n_ge_3"],
        dropna=False,
    ):
        support = int(family_support)
        rows.extend(
            {
                "family_canonical": str(family_name),
                "type_slug": str(type_slug),
                "family_support": support,
                "benchmark_eligible_n_ge_3": bool(benchmark_eligible),
                **metrics,
            }
            for metrics in _group_signal_prevalence(group, support, catalog_df, assignments)
        )
    out = pd.DataFrame(rows).sort_values(
        by=["family_support", "family_canonical", "signal_key"],
        ascending=[False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return annotate_prevalence_patterns(
        out,
        support_col="family_support",
        basis="signal_prevalence_by_family",
    )


def validate_signal_prevalence_contract(
    frame: pd.DataFrame,
    *,
    support_column: str,
) -> None:
    """Fail closed when model-safe and observed signal counts become ambiguous."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return
    required = {
        support_column,
        "positive_count",
        "observed_positive_count",
        "candidate_positive_count",
        "raw_pattern_positive_count",
        "prevalence_pct",
        "observed_prevalence_pct",
        "package_balanced_prevalence_pct",
        "signal_evidence_contract_version",
        "assignment_evidence_policy",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(
            "Signal prevalence evidence contract is incomplete; missing columns: "
            + ", ".join(missing)
        )
    versions = set(frame["signal_evidence_contract_version"].dropna().astype(str))
    if versions != {SIGNAL_EVIDENCE_CONTRACT_VERSION}:
        raise ValueError(
            "Signal prevalence evidence contract version mismatch: "
            f"expected {SIGNAL_EVIDENCE_CONTRACT_VERSION}, found {sorted(versions)}"
        )
    policies = set(frame["assignment_evidence_policy"].dropna().astype(str))
    if policies != {"model_eligible_assignments_only"}:
        raise ValueError(
            "Signal prevalence must use model-eligible assignments only; "
            f"found policies {sorted(policies)}"
        )

    numeric = {
        column: pd.to_numeric(frame[column], errors="coerce")
        for column in (
            support_column,
            "positive_count",
            "observed_positive_count",
            "candidate_positive_count",
            "raw_pattern_positive_count",
            "prevalence_pct",
            "observed_prevalence_pct",
        )
    }
    if any(series.isna().any() for series in numeric.values()):
        raise ValueError("Signal prevalence evidence contract contains non-numeric counts")
    support = numeric[support_column]
    positive = numeric["positive_count"]
    observed = numeric["observed_positive_count"]
    candidate = numeric["candidate_positive_count"]
    raw_pattern = numeric["raw_pattern_positive_count"]
    if (support <= 0).any():
        raise ValueError("Signal prevalence evidence contract requires positive group support")
    if ((positive < 0) | (positive > observed) | (observed > support)).any():
        raise ValueError("Model-eligible and observed signal counts do not reconcile")
    if ((candidate < 0) | (candidate > observed)).any():
        raise ValueError("Candidate signal counts do not reconcile with observed counts")
    if ((raw_pattern < 0) | (raw_pattern > observed)).any():
        raise ValueError("Raw-pattern signal counts do not reconcile with observed counts")

    expected_model_pct = positive / support * 100.0
    expected_observed_pct = observed / support * 100.0
    if not np.allclose(
        numeric["prevalence_pct"],
        expected_model_pct,
        rtol=0.0,
        atol=1e-5,
    ):
        raise ValueError("Model-eligible signal prevalence does not match its count denominator")
    if not np.allclose(
        numeric["observed_prevalence_pct"],
        expected_observed_pct,
        rtol=0.0,
        atol=1e-5,
    ):
        raise ValueError("Observed signal prevalence does not match its count denominator")
    package_prevalence = pd.to_numeric(
        frame["package_balanced_prevalence_pct"],
        errors="coerce",
    ).dropna()
    if ((package_prevalence < 0) | (package_prevalence > 100)).any():
        raise ValueError("Package-balanced signal prevalence is outside [0, 100]")
