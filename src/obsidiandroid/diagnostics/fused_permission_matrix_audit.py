"""Summarize permission-column mass on the fused ML feature matrix (cohort-indexed rows)."""

from __future__ import annotations

from typing import Any

import pandas as pd


def summarize_fused_permission_columns(feature_df: pd.DataFrame | None) -> dict[str, Any]:
    """Count ``perm__*`` / ``perm_grp__*`` nonzero mass after vendor encode + enrichment join.

    The fused matrix is indexed by ``sample_id`` (or carries a ``sample_id`` column with a
    default ``RangeIndex``); counts use whichever representation matches rows.

    Counts apply **after vendor row authority**: samples without vendor/parser coverage are
    absent from this matrix, so permission mass here can be far below cohort-level enrichment
    even when joins are correct.
    """
    if not isinstance(feature_df, pd.DataFrame) or feature_df.empty:
        return {}

    perm_cols = [c for c in feature_df.columns if str(c).startswith("perm__")]
    grp_cols = [c for c in feature_df.columns if str(c).startswith("perm_grp__")]
    if not perm_cols and not grp_cols:
        out: dict[str, Any] = {"fused_matrix_perm_like_column_count": 0}
        if "meta__permissions" in feature_df.columns:
            meta = pd.to_numeric(feature_df["meta__permissions"], errors="coerce").fillna(0)
            out["fused_matrix_row_count"] = int(len(feature_df))
            out["fused_matrix_meta__permissions_nonzero_rows"] = int((meta > 0).sum())
        return out

    work = feature_df[perm_cols + grp_cols].apply(pd.to_numeric, errors="coerce").fillna(0) if (perm_cols + grp_cols) else pd.DataFrame()
    if work.empty:
        return {}

    row_any_perm = (work.sum(axis=1) > 0) if len(work.columns) else pd.Series(dtype=int)
    out: dict[str, Any] = {
        "fused_matrix_row_count": int(len(feature_df)),
        "fused_matrix_perm_like_column_count": int(len(perm_cols) + len(grp_cols)),
        "fused_matrix_rows_with_any_perm_like_positive": int(row_any_perm.sum()),
    }
    internet = next((c for c in perm_cols if "internet" in str(c).lower()), None)
    if internet and internet in work.columns:
        out["fused_matrix_perm_internet_nonzero_rows"] = int((work[internet] > 0).sum())
    if "perm__total_count" in work.columns:
        out["fused_matrix_perm__total_count_nonzero_rows"] = int((work["perm__total_count"] > 0).sum())
    if "meta__permissions" in feature_df.columns:
        meta = pd.to_numeric(feature_df["meta__permissions"], errors="coerce").fillna(0)
        out["fused_matrix_meta__permissions_nonzero_rows"] = int((meta > 0).sum())
    return out
