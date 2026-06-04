"""Tests for confusion matrix hierarchical layout and export gating."""

from pathlib import Path

import numpy as np
import pytest

from config import app_config
from obsidiandroid.governance.family_tier_authority import major_family_name_list
from obsidiandroid.pipeline.manifest.confusion_matrix_paths import find_primary_confusion_matrix
from obsidiandroid.reporting import confusion_matrix_exporter as cme
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


def test_build_grouped_family_confusion_matrix_buckets_major_minor_and_generic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_TRAINING_SUPERVISED_LABEL_FIELD", "family_id", raising=False)
    labels = [name.title() for name in major_family_name_list()[:13]] + [f"MinorFam{i}" for i in range(11)] + [
        "banker",
        "",
    ]
    cm = np.eye(len(labels), dtype=int)
    cm[0, 0] = 20
    cm[1, 1] = 18
    cm[13, 13] = 7
    cm[14, 14] = 6
    cm[-2, -2] = 5
    cm[-1, -1] = 3

    grouped = cme.build_grouped_family_confusion_matrix(cm, labels)
    assert grouped is not None
    grouped_cm, grouped_labels = grouped
    kept_major_labels = set(labels[:12])
    assert kept_major_labels.intersection(grouped_labels)
    assert "Other Major" in grouped_labels
    assert "Minor/Long-tail" in grouped_labels
    assert "Generic/Coarse" in grouped_labels
    assert "Unresolved" in grouped_labels
    assert int(grouped_cm.sum()) == int(cm.sum())


def test_export_confusion_matrix_image_writes_display_variant_for_large_family_surface(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Large family-surface export should write both primary and display variant paths."""
    monkeypatch.setattr(app_config, "RUNTIME_TRAINING_SUPERVISED_LABEL_FIELD", "family_id", raising=False)
    major = list(major_family_name_list()[:13])
    minor = [f"MinorFam{i}" for i in range(11)]
    labels = [name.title() for name in major] + minor + ["banker", ""]
    size = len(labels)
    cm = np.eye(size, dtype=int)
    output_path = tmp_path / "output" / "random_forest.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _fake_savefig(path: Path | str, *args, **kwargs) -> None:  # noqa: ARG001
        artifact_path = Path(path)
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(b"png")

    def _fake_export_grouped_display_variant(**kwargs) -> Path:
        display_path = cme.display_variant_output_path(Path(kwargs["output_path"]))
        display_path.parent.mkdir(parents=True, exist_ok=True)
        display_path.write_bytes(b"display")
        return display_path

    monkeypatch.setattr(cme, "_render_confusion_matrix_plot", lambda *args, **kwargs: None)
    monkeypatch.setattr(cme.plt, "savefig", _fake_savefig)
    monkeypatch.setattr(cme, "_export_grouped_display_variant", _fake_export_grouped_display_variant)

    rendered = cme.export_confusion_matrix_image(
        cm=cm,
        class_labels=labels,
        model_name="random_forest",
        output_path=output_path,
        verbose=False,
    )

    assert Path(rendered).is_file()
    assert cme.display_variant_output_path(output_path).is_file()


def test_find_primary_confusion_matrix_prefers_display_variant_for_evidence(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    cm_dir = run_root / "conf_matrices"
    cm_dir.mkdir(parents=True, exist_ok=True)
    raw = cm_dir / "confusion_matrix_primary.png"
    display = cm_dir / "confusion_matrix_primary_display.png"
    raw.write_bytes(b"raw")
    display.write_bytes(b"display")

    resolved = find_primary_confusion_matrix(run_root=run_root, top_model="random_forest", evidence_mode=True)
    assert resolved == display
