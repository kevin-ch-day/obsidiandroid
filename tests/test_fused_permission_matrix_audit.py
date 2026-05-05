"""Tests for fused-matrix permission signal summaries."""

from __future__ import annotations

import pandas as pd

from obsidiandroid.diagnostics import fused_permission_matrix_audit


def test_summarize_fused_permission_columns_counts_internet_and_meta() -> None:
    df = pd.DataFrame(
        {
            "perm__android_permission_internet": [1, 0, 1],
            "perm__total_count": [2, 0, 1],
            "perm_grp__network_c2_count": [1, 0, 0],
            "meta__permissions": [5, 0, 3],
        },
        index=[101, 102, 103],
    )
    df.index.name = "sample_id"
    out = fused_permission_matrix_audit.summarize_fused_permission_columns(df)
    assert out["fused_matrix_row_count"] == 3
    assert out["fused_matrix_rows_with_any_perm_like_positive"] == 2
    assert out["fused_matrix_perm_internet_nonzero_rows"] == 2
    assert out["fused_matrix_meta__permissions_nonzero_rows"] == 2


def test_summarize_fused_permission_columns_meta_only_matrix() -> None:
    df = pd.DataFrame({"meta__permissions": [1]}, index=[1])
    df.index.name = "sample_id"
    out = fused_permission_matrix_audit.summarize_fused_permission_columns(df)
    assert out["fused_matrix_perm_like_column_count"] == 0
    assert out["fused_matrix_meta__permissions_nonzero_rows"] == 1
