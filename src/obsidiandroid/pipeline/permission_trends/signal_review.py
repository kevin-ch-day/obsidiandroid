"""Build diagnostic review tables for candidate permission evidence."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from obsidiandroid.database.permission_current_interpretation import (
    is_androidx_dynamic_receiver_permission,
)

from .constants import SIGNAL_EVIDENCE_CONTRACT_VERSION
from .signal_assignments import prepare_signal_sample_core


def build_signal_evidence_review_queue(
    type_prevalence_df: pd.DataFrame,
    family_prevalence_df: pd.DataFrame,
    *,
    run_id: str,
) -> pd.DataFrame:
    """Build the diagnostic-only candidate/raw evidence review surface."""
    frames: list[pd.DataFrame] = []
    specifications = (
        ("type", type_prevalence_df, "type_slug", "type_sample_count"),
        ("family", family_prevalence_df, "family_canonical", "family_support"),
    )
    for group_kind, source, group_column, support_column in specifications:
        if not isinstance(source, pd.DataFrame) or source.empty:
            continue
        work = source.copy()
        for column in (
            support_column,
            "positive_count",
            "observed_positive_count",
            "candidate_positive_count",
            "raw_pattern_positive_count",
        ):
            work[column] = pd.to_numeric(work[column], errors="coerce").fillna(0)
        work["excluded_observed_positive_count"] = (
            work["observed_positive_count"] - work["positive_count"]
        ).clip(lower=0)
        work = work[
            work[
                [
                    "candidate_positive_count",
                    "raw_pattern_positive_count",
                    "excluded_observed_positive_count",
                ]
            ].max(axis=1)
            > 0
        ].copy()
        if work.empty:
            continue
        work["run_id"] = run_id
        work["group_kind"] = group_kind
        work["group_value"] = work[group_column].astype(str)
        work["group_support"] = work[support_column].astype(int)
        work["candidate_prevalence_pct"] = (
            work["candidate_positive_count"] / work["group_support"] * 100.0
        ).round(6)
        work["raw_pattern_prevalence_pct"] = (
            work["raw_pattern_positive_count"] / work["group_support"] * 100.0
        ).round(6)
        frames.append(work)
    columns = [
        "run_id",
        "group_kind",
        "group_value",
        "type_slug",
        "signal_key",
        "signal_label",
        "group_support",
        "positive_count",
        "observed_positive_count",
        "excluded_observed_positive_count",
        "candidate_positive_count",
        "candidate_prevalence_pct",
        "raw_pattern_positive_count",
        "raw_pattern_prevalence_pct",
        "prevalence_pct",
        "observed_prevalence_pct",
        "package_balanced_prevalence_pct",
        "observed_package_balanced_prevalence_pct",
        "sample_minus_package_balanced_pp",
        "signal_evidence_contract_version",
        "assignment_evidence_policy",
    ]
    if not frames:
        return pd.DataFrame(columns=["review_rank", *columns])
    out = pd.concat(frames, ignore_index=True, sort=False)
    for column in columns:
        if column not in out.columns:
            out[column] = ""
    out = out.sort_values(
        by=[
            "candidate_positive_count",
            "raw_pattern_positive_count",
            "excluded_observed_positive_count",
            "group_kind",
            "group_value",
            "signal_key",
        ],
        ascending=[False, False, False, True, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    out.insert(0, "review_rank", np.arange(1, len(out) + 1, dtype=int))
    return out[["review_rank", *columns]]


def build_androidx_receiver_evidence_review(
    permission_rows_df: pd.DataFrame,
    sample_core_df: pd.DataFrame,
    *,
    run_id: str,
) -> pd.DataFrame:
    """Return actionable AndroidX candidate and malformed-token cohorts."""
    columns = [
        "review_rank",
        "run_id",
        "permission_string",
        "morphology",
        "evidence_tier",
        "review_reason",
        "observation_count",
        "sample_count",
        "known_package_count",
        "type_count",
        "raw_token_variant_count",
        "package_exact_observations",
        "template_example_observations",
        "prefix_related_observations",
        "cross_package_reuse_observations",
        "missing_package_observations",
        "permission_source",
        "governance_precedence",
        "effective_source_family_key",
        "candidate_source_family_key",
        "effective_resolution_semantics",
        "signal_evidence_contract_version",
    ]
    if (
        not isinstance(permission_rows_df, pd.DataFrame)
        or permission_rows_df.empty
        or "permission_string" not in permission_rows_df.columns
    ):
        return pd.DataFrame(columns=columns)
    work = permission_rows_df.copy()
    work["permission_string"] = (
        work["permission_string"].fillna("").astype(str).str.strip().str.lower()
    )
    work = work[
        work["permission_string"].str.contains(
            "dynamic_receiver_not_exported_permission",
            regex=False,
        )
    ].copy()
    if work.empty:
        return pd.DataFrame(columns=columns)
    for column in (
        "permission_source",
        "governance_precedence",
        "effective_source_family_key",
        "candidate_source_family_key",
        "effective_resolution_semantics",
    ):
        values = (
            work[column]
            if column in work.columns
            else pd.Series("", index=work.index, dtype="object")
        )
        work[column] = values.fillna("").astype(str).str.strip().str.lower()
    if "permission_string_raw" not in work.columns:
        work["permission_string_raw"] = work["permission_string"]
    work["permission_string_raw"] = (
        work["permission_string_raw"].fillna("").astype(str).str.strip()
    )
    work["is_exact_shape"] = work["permission_string"].map(
        is_androidx_dynamic_receiver_permission
    )
    work["is_candidate"] = work["governance_precedence"].eq("candidate") | work[
        "effective_resolution_semantics"
    ].eq("candidate")
    work["has_candidate_guard"] = work["candidate_source_family_key"].eq(
        "app_defined_dynamic_receiver_guard"
    ) | (
        work["effective_source_family_key"].eq(
            "app_defined_dynamic_receiver_guard"
        )
        & work["is_candidate"]
    )
    work["is_actionable_candidate"] = work["is_exact_shape"] & work[
        "has_candidate_guard"
    ]
    work["is_malformed"] = ~work["is_exact_shape"]
    work = work[work["is_actionable_candidate"] | work["is_malformed"]].copy()
    if work.empty:
        return pd.DataFrame(columns=columns)
    malformed_extension = re.compile(
        r"^[a-z0-9_]+(?:\.[a-z0-9_]+)+\."
        r"dynamic_receiver_not_exported_permission[a-z0-9_]+$",
        re.IGNORECASE,
    )
    work["morphology"] = np.where(
        work["is_exact_shape"],
        "exact_androidx_guard",
        work["permission_string"].map(
            lambda value: (
                "trailing_extension"
                if malformed_extension.fullmatch(str(value))
                else "other_near_structure"
            )
        ),
    )
    work["evidence_tier"] = np.where(
        work["is_actionable_candidate"],
        "candidate_governance",
        "malformed_raw_pattern",
    )
    work["review_reason"] = np.where(
        work["is_actionable_candidate"],
        "source_or_manifest_evidence_required",
        "malformed_suffix_requires_exact_row_review",
    )

    membership = prepare_signal_sample_core(
        sample_core_df,
        grouping_columns=["type_slug"],
    )[
        ["sample_id", "type_slug", "package_key", "is_missing_package"]
    ]
    work = work.merge(membership, on="sample_id", how="left", validate="many_to_one")
    work["type_slug"] = work["type_slug"].fillna("unknown").astype(str)
    work["package_key"] = work["package_key"].fillna("").astype(str)
    work["is_missing_package"] = work["is_missing_package"].fillna(True).astype(bool)
    suffix = ".dynamic_receiver_not_exported_permission"
    work["permission_prefix"] = work["permission_string"].map(
        lambda value: str(value).split(suffix, maxsplit=1)[0]
    )

    def package_relation(row: pd.Series) -> str:
        if bool(row["is_missing_package"]):
            return "missing_package"
        prefix = str(row["permission_prefix"])
        package = str(row["package_key"])
        if prefix == package:
            return "package_exact"
        if "example" in prefix.split("."):
            return "template_example"
        if prefix.startswith(package + ".") or package.startswith(prefix + "."):
            return "prefix_related"
        return "cross_package_reuse"

    work["package_relation"] = work.apply(package_relation, axis=1)
    work["known_package_key"] = work["package_key"].where(
        ~work["is_missing_package"],
        "",
    )
    group_columns = [
        "permission_string",
        "morphology",
        "evidence_tier",
        "review_reason",
        "permission_source",
        "governance_precedence",
        "effective_source_family_key",
        "candidate_source_family_key",
        "effective_resolution_semantics",
    ]
    out = (
        work.groupby(group_columns, dropna=False)
        .agg(
            observation_count=("sample_id", "size"),
            sample_count=("sample_id", "nunique"),
            known_package_count=(
                "known_package_key",
                lambda values: int(values[values != ""].nunique()),
            ),
            type_count=("type_slug", "nunique"),
            raw_token_variant_count=("permission_string_raw", "nunique"),
            package_exact_observations=(
                "package_relation",
                lambda values: int((values == "package_exact").sum()),
            ),
            template_example_observations=(
                "package_relation",
                lambda values: int((values == "template_example").sum()),
            ),
            prefix_related_observations=(
                "package_relation",
                lambda values: int((values == "prefix_related").sum()),
            ),
            cross_package_reuse_observations=(
                "package_relation",
                lambda values: int((values == "cross_package_reuse").sum()),
            ),
            missing_package_observations=(
                "package_relation",
                lambda values: int((values == "missing_package").sum()),
            ),
        )
        .reset_index()
        .sort_values(
            by=["observation_count", "sample_count", "permission_string"],
            ascending=[False, False, True],
            kind="mergesort",
        )
        .reset_index(drop=True)
    )
    out.insert(0, "run_id", run_id)
    out.insert(0, "review_rank", np.arange(1, len(out) + 1, dtype=int))
    out["signal_evidence_contract_version"] = SIGNAL_EVIDENCE_CONTRACT_VERSION
    return out[columns]
