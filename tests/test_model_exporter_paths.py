"""Tests for model exporter run-scoped path behavior."""

from __future__ import annotations

from pathlib import Path

from sklearn.dummy import DummyClassifier

from config import app_config
from utils import model_exporter


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
