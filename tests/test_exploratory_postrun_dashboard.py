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
