"""Tests for model exporter run-scoped path behavior."""

from __future__ import annotations

from pathlib import Path

from sklearn.dummy import DummyClassifier

from config import app_config
from obsidiandroid.modeling import model_exporter


def test_model_exporter_writes_run_scoped_only(monkeypatch, tmp_path: Path) -> None:
    """Model export should target run-scoped paths only."""
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "20260301T011643Z__d485b6", raising=False)

    model = DummyClassifier(strategy="most_frequent")
    model.fit([[0], [1]], [0, 1])

    path = model_exporter.export_model_to_file(
        model=model,
        output_dir=tmp_path,
        model_type="random_forest",
        metadata_dict={"ok": True},
    )
    assert path is not None
    run_scoped = tmp_path / "runs" / "20260301T011643Z__d485b6" / "models" / "random_forest"
    assert path.parent == run_scoped
    assert (run_scoped / "random_forest_classifier_model_metadata.json").exists()

    legacy_dir = tmp_path / "models" / "random_forest"
    assert not legacy_dir.exists()


def test_model_exporter_does_not_nest_runs_when_given_run_root(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Passing an existing run root should write directly into its models subtree."""
    run_id = "20260301T011643Z__d485b6"
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", run_id, raising=False)

    model = DummyClassifier(strategy="most_frequent")
    model.fit([[0], [1]], [0, 1])

    run_root = tmp_path / "runs" / run_id
    path = model_exporter.export_model_to_file(
        model=model,
        output_dir=run_root,
        model_type="random_forest",
        metadata_dict={"ok": True},
    )

    assert path is not None
    expected_dir = run_root / "models" / "random_forest"
    assert path.parent == expected_dir
    assert not (run_root / "runs" / run_id).exists()


def test_model_exporter_uses_slot_run_root_when_active(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Active slot roots should stay canonical for model exports."""
    run_id = "20260301T011643Z__d485b6"
    slot_root = tmp_path / "output" / "runs" / "allcurrent_diagnostic"
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ROOT", str(slot_root), raising=False)

    model = DummyClassifier(strategy="most_frequent")
    model.fit([[0], [1]], [0, 1])

    path = model_exporter.export_model_to_file(
        model=model,
        output_dir=tmp_path / "output",
        model_type="random_forest",
        metadata_dict={"ok": True},
    )

    assert path is not None
    expected_dir = slot_root / "models" / "random_forest"
    assert path.parent == expected_dir
    assert not (tmp_path / "output" / "runs" / run_id / "models").exists()
