"""Compare profiles built from permission or signal prevalence."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .pattern_framework import annotate_similarity_patterns

_FAMILY_COLUMNS = (
    "family_a",
    "family_b",
    "type_a",
    "type_b",
    "support_a",
    "support_b",
    "jaccard_similarity",
    "cosine_similarity",
    "spearman_correlation",
    "same_type_flag",
)
_TYPE_COLUMNS = (
    "type_a",
    "type_b",
    "support_a",
    "support_b",
    "jaccard_similarity",
    "cosine_similarity",
    "spearman_correlation",
)


def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_norm = float(np.linalg.norm(left))
    right_norm = float(np.linalg.norm(right))
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return float(np.dot(left, right) / (left_norm * right_norm))


def spearman_similarity_details(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    """Return Spearman value plus explicit undefined-input provenance."""
    left_constant = bool(left.size and np.allclose(left, left[0], equal_nan=True))
    right_constant = bool(right.size and np.allclose(right, right[0], equal_nan=True))
    if left.shape == right.shape and np.allclose(left, right, equal_nan=True):
        return {"spearman_correlation": 1.0, "correlation_status": "identical_profile", "left_profile_constant": left_constant, "right_profile_constant": right_constant}
    if left_constant or right_constant:
        return {"spearman_correlation": None, "correlation_status": "constant_input", "left_profile_constant": left_constant, "right_profile_constant": right_constant}
    try:
        corr = pd.Series(left).corr(pd.Series(right), method="spearman")
        if pd.notna(corr):
            return {"spearman_correlation": float(corr), "correlation_status": "defined", "left_profile_constant": False, "right_profile_constant": False}
        return {"spearman_correlation": None, "correlation_status": "undefined", "left_profile_constant": left_constant, "right_profile_constant": right_constant}
    except Exception:
        return {"spearman_correlation": None, "correlation_status": "error", "left_profile_constant": left_constant, "right_profile_constant": right_constant}


def _jaccard_similarity(left: np.ndarray, right: np.ndarray) -> float:
    left_set = set(np.flatnonzero(left > 0.0).tolist())
    right_set = set(np.flatnonzero(right > 0.0).tolist())
    union = left_set | right_set
    if not union:
        return 1.0
    return float(len(left_set & right_set) / float(len(union)))


def _similarity_metrics(left_vec: np.ndarray, right_vec: np.ndarray) -> dict[str, Any]:
    spearman = spearman_similarity_details(left_vec, right_vec)
    return {
        "jaccard_similarity": round(_jaccard_similarity(left_vec, right_vec), 6),
        "cosine_similarity": round(_cosine_similarity(left_vec, right_vec), 6),
        "spearman_correlation": (
            round(float(spearman["spearman_correlation"]), 6)
            if spearman["spearman_correlation"] is not None else None
        ),
        "correlation_status": spearman["correlation_status"],
        "left_profile_constant": spearman["left_profile_constant"],
        "right_profile_constant": spearman["right_profile_constant"],
    }


def _build_family_similarity(
    family_prevalence_df: pd.DataFrame, *, feature_column: str, basis: str
) -> pd.DataFrame:
    if family_prevalence_df.empty:
        return pd.DataFrame(columns=_FAMILY_COLUMNS)
    pivot = family_prevalence_df.pivot_table(
        index=["family_canonical", "type_slug", "family_support"],
        columns=feature_column,
        values="prevalence_pct",
        fill_value=0.0,
    )
    index_rows = pivot.index.tolist()
    rows: list[dict[str, Any]] = []
    for i, left_key in enumerate(index_rows):
        left_vec = np.array(pivot.loc[left_key], dtype=float)
        for j in range(i + 1, len(index_rows)):
            right_key = index_rows[j]
            right_vec = np.array(pivot.loc[right_key], dtype=float)
            family_a, type_a, support_a = left_key
            family_b, type_b, support_b = right_key
            rows.append(
                {
                    "family_a": str(family_a),
                    "family_b": str(family_b),
                    "type_a": str(type_a),
                    "type_b": str(type_b),
                    "support_a": int(support_a),
                    "support_b": int(support_b),
                    **_similarity_metrics(left_vec, right_vec),
                    "same_type_flag": bool(str(type_a) == str(type_b)),
                }
            )
    if not rows:
        return pd.DataFrame(columns=_FAMILY_COLUMNS)
    out = pd.DataFrame(rows).sort_values(
        by=["same_type_flag", "cosine_similarity", "jaccard_similarity", "family_a", "family_b"],
        ascending=[False, False, False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return annotate_similarity_patterns(
        out,
        support_a_col="support_a",
        support_b_col="support_b",
        same_type_col="same_type_flag",
        basis=basis,
    )


def build_family_permission_similarity(
    family_prevalence_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compare family profiles using raw permission prevalence."""
    return _build_family_similarity(
        family_prevalence_df, feature_column="permission", basis="family_permission_similarity",
    )


def build_family_signal_similarity(
    family_signal_prevalence_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compare family profiles using signal prevalence."""
    return _build_family_similarity(
        family_signal_prevalence_df, feature_column="signal_key", basis="family_signal_similarity",
    )


def build_type_permission_similarity(
    type_prevalence_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compare type profiles using raw permission prevalence."""
    if type_prevalence_df.empty:
        return pd.DataFrame(columns=_TYPE_COLUMNS)
    pivot = type_prevalence_df.pivot_table(
        index=["type_slug", "n_samples"],
        columns="permission",
        values="prevalence_pct",
        fill_value=0.0,
    )
    types = pivot.index.tolist()
    rows: list[dict[str, Any]] = []
    for i, left_key in enumerate(types):
        left_vec = np.array(pivot.loc[left_key], dtype=float)
        for j in range(i + 1, len(types)):
            right_key = types[j]
            right_vec = np.array(pivot.loc[right_key], dtype=float)
            type_a, support_a = left_key
            type_b, support_b = right_key
            rows.append(
                {
                    "type_a": str(type_a),
                    "type_b": str(type_b),
                    "support_a": int(support_a),
                    "support_b": int(support_b),
                    **_similarity_metrics(left_vec, right_vec),
                }
            )
    if not rows:
        return pd.DataFrame(columns=_TYPE_COLUMNS)
    out = pd.DataFrame(rows).sort_values(
        by=["cosine_similarity", "jaccard_similarity", "type_a", "type_b"],
        ascending=[False, False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return annotate_similarity_patterns(
        out,
        support_a_col="support_a",
        support_b_col="support_b",
        basis="type_permission_similarity",
    )
