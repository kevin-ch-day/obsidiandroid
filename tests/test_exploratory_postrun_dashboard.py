"""The broad catalog pass finishes without repeating full-corpus PI reads."""

from __future__ import annotations

from pathlib import Path

from obsidiandroid.pipeline import runner


def test_all_catalog_skips_postrun_dashboard(monkeypatch, tmp_path: Path) -> None:
    def _unexpected(**_kwargs):
        raise AssertionError("optional dashboard must not run for broad catalog exploration")

    monkeypatch.setattr(runner.operator_dashboard, "emit_research_operator_report", _unexpected)
    runner._emit_post_finalize_operator_report(  # pylint: disable=protected-access
        st=None,
        diagnostics_dir=tmp_path,
        run_id="broad_unit",
        profile_id="android_catalog_all_exploratory",
        manifest_context={},
        samples_df=None,
        model_results=None,
        top_model=None,
    )
    assert not (tmp_path / "post_finalize_operator_report_timing_broad_unit.json").exists()


def test_exploratory_profile_is_not_presented_as_benchmark(monkeypatch):
    import pandas as pd
    from config import app_config
    from obsidiandroid.evaluation.ml_terminal_presentation import claim_surface_label_for_profile
    from obsidiandroid.observability.pipeline_observability.finalize import _claim_surface_label
    from obsidiandroid.diagnostics.output_inventory import _claim_surface_label as inventory_label
    from obsidiandroid.governance.cohort_readiness_report import _profile_surface_label, _cohort_summary_heading
    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False, raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    profile = "android_catalog_all_exploratory"
    assert claim_surface_label_for_profile(profile) == "Android catalog exploratory surface"
    for label in (_claim_surface_label, inventory_label):
        assert label(profile_id=profile, evidence_mode=False, paper_mode=False) == "Android catalog exploratory surface"
        assert label(profile_id=profile, evidence_mode=True, paper_mode=False) == "Locked publication cohort"
    assert _cohort_summary_heading(profile_id=profile, samples_df=pd.DataFrame()) == "Android Catalog Exploratory Summary"
    assert _profile_surface_label(profile_id=profile, samples_df=pd.DataFrame()).startswith("All-APK catalog exploration")
