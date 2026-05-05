"""Integration wiring checks for export manager module consumers."""

from analysis.evaluation import evaluate_av_classifications
from analysis.evaluation import vendor_feature_extractor
from obsidiandroid.pipeline import score_av_engines
from obsidiandroid.modeling import pipeline_core
from obsidiandroid.reporting import export_manager


def test_export_manager_shared_import_aliases_point_to_module() -> None:
    """Ensure major pipeline modules import the shared export manager module."""
    assert evaluate_av_classifications.em is export_manager
    assert vendor_feature_extractor.em is export_manager
    assert score_av_engines.em is export_manager
    assert pipeline_core.em is export_manager
