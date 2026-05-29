"""Tests for permission column survival audit across training stages."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from obsidiandroid.diagnostics import permission_training_survival_audit as pts
from config import app_config


def test_export_permission_training_survival_audit_writes_csv(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_PERMISSION_TRAINING_SURVIVAL_CSV", "", raising=False)
    align = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "perm__internet": [1, 0],
            "perm_grp__x": [0, 1],
        }
    )
    fam = align.iloc[[0]].copy()
    low = fam.drop(columns=["perm_grp__x"])
    leak = low.copy()
    cohort_fused_stats = pts.perm_prefix_nonzero_stats(align)
    path = pts.export_permission_training_survival_audit(
        after_align=(pts.perm_prefix_nonzero_stats(align), len(align)),
        after_family_support=(pts.perm_prefix_nonzero_stats(fam), len(fam)),
        after_low_information_prune=(pts.perm_prefix_nonzero_stats(low), len(low)),
        after_leakage_prune=(pts.perm_prefix_nonzero_stats(leak), len(leak)),
        cohort_fused=(cohort_fused_stats, len(align)),
        diagnostics_dir=tmp_path,
        run_id="unit",
    )
    assert path is not None
    assert Path(path).exists()
    written = pd.read_csv(path)
    assert "matrix_rows_cohort_fused" in written.columns
    assert written.loc[written["column"] == "perm__internet", "nonzero_cohort_fused"].iloc[0] == 1
    assert "perm__internet" in written["column"].tolist()
    dropped = written.loc[written["column"] == "perm_grp__x", "dropped_by_low_information_prune"].iloc[0]
    assert bool(dropped) is True
    assert getattr(app_config, "RUNTIME_PERMISSION_TRAINING_SURVIVAL_CSV", "") == path


def test_export_skips_when_no_perm_columns(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_PERMISSION_TRAINING_SURVIVAL_CSV", "stale", raising=False)
    df = pd.DataFrame({"sample_id": [1], "x": [1]})
    b = (pts.perm_prefix_nonzero_stats(df), len(df))
    out = pts.export_permission_training_survival_audit(
        after_align=b,
        after_family_support=b,
        after_low_information_prune=b,
        after_leakage_prune=b,
        diagnostics_dir=tmp_path,
        run_id="empty",
    )
    assert out is None
    assert getattr(app_config, "RUNTIME_PERMISSION_TRAINING_SURVIVAL_CSV", "") == ""


def test_export_permission_training_survival_audit_uses_global_latest_for_run_scoped_dirs(
    make_run_diagnostics_layout,
    monkeypatch,
) -> None:
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("rid")
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_PERMISSION_TRAINING_SURVIVAL_CSV", "", raising=False)
    align = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "perm__internet": [1, 0],
            "perm_grp__x": [0, 1],
        }
    )
    fam = align.iloc[[0]].copy()
    low = fam.drop(columns=["perm_grp__x"])
    leak = low.copy()

    path = pts.export_permission_training_survival_audit(
        after_align=(pts.perm_prefix_nonzero_stats(align), len(align)),
        after_family_support=(pts.perm_prefix_nonzero_stats(fam), len(fam)),
        after_low_information_prune=(pts.perm_prefix_nonzero_stats(low), len(low)),
        after_leakage_prune=(pts.perm_prefix_nonzero_stats(leak), len(leak)),
        diagnostics_dir=diagnostics_dir,
        run_id="rid",
    )

    assert path == str(diagnostics_dir / "permission_training_survival_rid.csv")
    assert (diagnostics_dir / "permission_training_survival_rid.csv").is_file()
    assert not (diagnostics_dir / "permission_training_survival.latest.csv").exists()
    assert (output_root / "diagnostics" / "permission_training_survival.latest.csv").is_file()


def test_summarize_fused_permission_columns_counts_internet_and_meta() -> None:
    from obsidiandroid.diagnostics import fused_permission_matrix_audit

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
    from obsidiandroid.diagnostics import fused_permission_matrix_audit

    df = pd.DataFrame({"meta__permissions": [1]}, index=[1])
    df.index.name = "sample_id"
    out = fused_permission_matrix_audit.summarize_fused_permission_columns(df)
    assert out["fused_matrix_perm_like_column_count"] == 0
    assert out["fused_matrix_meta__permissions_nonzero_rows"] == 1
