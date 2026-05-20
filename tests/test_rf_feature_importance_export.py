"""Tests for RF impurity importance export hygiene."""

from __future__ import annotations

from pathlib import Path

from config import app_config
from obsidiandroid.diagnostics import rf_feature_importance_export as rfexp


class _DummyModel:
    feature_importances_ = [0.7, 0.3]


def test_export_rf_impurity_importances_uses_global_latest_for_run_scoped_dirs(
    make_run_diagnostics_layout,
    monkeypatch,
) -> None:
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("rid")
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)

    out = rfexp.export_rf_impurity_importances_csv(
        model=_DummyModel(),
        feature_names=["perm__internet", "vendor_signal"],
        diagnostics_dir=diagnostics_dir,
        run_id="rid",
        top_k=2,
    )

    assert out == diagnostics_dir / "rf_impurity_importance_rid.csv"
    assert Path(out).is_file()
    assert not (diagnostics_dir / "rf_impurity_importance.latest.csv").exists()
    assert (output_root / "diagnostics" / "rf_impurity_importance.latest.csv").is_file()
