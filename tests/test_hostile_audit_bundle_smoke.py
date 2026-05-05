"""Smoke tests for hostile audit orchestration."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from obsidiandroid.diagnostics.hostile_audit.bundle import write_hostile_audit_bundle
from obsidiandroid.diagnostics.hostile_audit.cohort_population_audit import write_cohort_population_audit


def test_write_cohort_population_audit_writes_table(tmp_path: Path) -> None:
    diagnostics_dir = tmp_path / "diag"
    samples = pd.DataFrame(
        {"sample_id": [1, 2], "family_canonical": ["a", "b"], "type_slug": ["t1", "t1"]},
    )
    manifest = {"cohort_size": 2}
    mctx = {
        "cohort_prepared_row_count": 2,
        "governed_cohort_rows": 2,
        "aligned_supervised_rows": 2,
        "train_sample_count": 1,
        "test_sample_count": 1,
    }
    csv_p, md_p = write_cohort_population_audit(
        diagnostics_dir=diagnostics_dir,
        run_id="test_run",
        manifest=manifest,
        manifest_context=mctx,
        samples_df=samples,
    )
    assert csv_p.exists()
    assert md_p.exists()
    text = csv_p.read_text(encoding="utf-8")
    assert "cohort_prepared_row_count" in text
    assert "distinct_families_canonical_prepared_cohort" in text


def test_write_hostile_audit_bundle_minimum(tmp_path: Path) -> None:
    diagnostics_dir = tmp_path / "diag"
    manifest = {}
    mctx = {"profile_params": {"cohort_gates": {"time_window_start_utc": "", "time_window_end_utc": ""}}}
    artifacts: list[str] = []
    write_hostile_audit_bundle(
        run_root=tmp_path,
        diagnostics_dir=diagnostics_dir,
        run_id="r1",
        manifest_context=mctx,
        manifest=manifest,
        samples_df=None,
        artifact_list=artifacts,
    )
    assert (diagnostics_dir / "cohort_population_audit.csv").exists()
    assert (diagnostics_dir / "baseline_comparison.csv").exists()
    assert (diagnostics_dir / "figure_validity_audit.md").exists()
    assert len(artifacts) >= 3
