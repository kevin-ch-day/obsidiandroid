"""Tests for confusion matrix hierarchical layout and export gating."""

from pathlib import Path

import pytest

from config import app_config
from obsidiandroid.reporting import confusion_matrix_layout as cml


def test_parse_experiment_combo_splits_label_target() -> None:
    fs, lt = cml.parse_experiment_combo("vendor_full__lt_family_id")
    assert fs == "vendor_full"
    assert lt == "family_id"


def test_selected_ablation_includes_permission_fusion_experiments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", True, raising=False)
    monkeypatch.setattr(app_config, "CONFUSION_MATRIX_EXPORT_MODE", "selected_ablation", raising=False)
    assert cml.should_export_confusion_matrix(experiment_id="permissions_grouped__lt_family_id")
    assert cml.should_export_confusion_matrix(experiment_id="full_fused__lt_family_id")


def test_should_export_headline_only_filters_ablation_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_ABLATION_ACTIVE", True, raising=False)
    monkeypatch.setattr(app_config, "CONFUSION_MATRIX_EXPORT_MODE", "headline_only", raising=False)
    monkeypatch.setattr(app_config, "CONFUSION_MATRIX_HEADLINE_EXPERIMENT", "vendor_no_parsed_family", raising=False)
    assert cml.should_export_confusion_matrix(experiment_id="vendor_no_parsed_family__lt_family_id")
    assert not cml.should_export_confusion_matrix(experiment_id="vendor_no_parsed_family__lt_family_canonical_default")
    assert not cml.should_export_confusion_matrix(experiment_id="permissions_raw__lt_family_id")
def test_write_catalog_smoke(tmp_path: Path) -> None:
    cm = tmp_path / "conf_matrices"
    (cm / "headline").mkdir(parents=True)
    (cm / "headline" / "random_forest.png").write_bytes(b"x")
    (cm / "ablation" / "vendor_full" / "family_canonical_default").mkdir(parents=True)
    (cm / "ablation" / "vendor_full" / "family_canonical_default" / "xgboost.png").write_bytes(b"y")
    idx, readme = cml.write_confusion_matrix_catalog(cm, run_id="rid")
    assert idx is not None and idx.is_file()
    assert readme is not None and "headline" in readme.read_text(encoding="utf-8")


def test_confusion_matrix_exporter_forces_agg_backend() -> None:
    """Confusion matrix exports should use a non-interactive backend."""
    import matplotlib

    import obsidiandroid.reporting.confusion_matrix_exporter  # noqa: F401 pylint: disable=import-outside-toplevel,unused-import

    backend = str(matplotlib.get_backend()).lower()
    assert "agg" in backend
