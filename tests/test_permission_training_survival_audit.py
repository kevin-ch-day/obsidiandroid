"""Tests for permission column survival audit across training stages."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from analysis.diagnostics import permission_training_survival_audit as pts
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
