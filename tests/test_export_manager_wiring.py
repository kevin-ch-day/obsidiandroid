"""Integration wiring checks for export manager module consumers."""

from obsidiandroid.evaluation import evaluate_av_classifications
from obsidiandroid.evaluation import vendor_feature_extractor
from obsidiandroid.pipeline import score_av_engines
from obsidiandroid.modeling import pipeline_core
from obsidiandroid.reporting import export_manager


def test_export_manager_shared_import_aliases_point_to_module() -> None:
    """Ensure major pipeline modules import the shared export manager module."""
    assert evaluate_av_classifications.em is export_manager
    assert vendor_feature_extractor.em is export_manager
    assert score_av_engines.em is export_manager
    assert pipeline_core.em is export_manager


def test_apply_scoring_defaults_tolerates_none_engine_thresholds(monkeypatch) -> None:
    from config import app_config

    monkeypatch.setattr(app_config, "ENGINE_MIN_SAMPLES_SCANNED", None, raising=False)
    monkeypatch.setattr(app_config, "ENGINE_MIN_COVERAGE_PCT", None, raising=False)
    monkeypatch.setattr(app_config, "ENGINE_MIN_POSITIVE_FLAGS", None, raising=False)
    monkeypatch.setattr(app_config, "ENGINE_MIN_DETECTION_PCT", None, raising=False)

    cfg = score_av_engines.apply_scoring_defaults({})
    assert cfg["min_engine_detections"] == 10
    assert cfg["min_coverage_pct"] == 20.0
    assert cfg["min_positive_flags"] == 5
    assert cfg["min_detection_pct"] == 1.0
