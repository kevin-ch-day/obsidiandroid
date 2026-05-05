"""Tests for cohort duplicate sample_id audit."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from obsidiandroid.diagnostics import cohort_sample_id_audit


def test_audit_reports_no_surplus_when_unique(tmp_path: Path) -> None:
    df = pd.DataFrame({"sample_id": [1, 2, 3], "x": [1, 2, 3]})
    out = cohort_sample_id_audit.audit_cohort_sample_id_uniqueness(
        df,
        diagnostics_dir=tmp_path,
        run_id="u1",
        artifact_list=[],
    )
    assert out["cohort_duplicate_surplus_rows"] == 0
    assert not (tmp_path / "duplicate_sample_id_cohort_u1.csv").exists()


def test_audit_exports_when_duplicates(tmp_path: Path) -> None:
    df = pd.DataFrame({"sample_id": [1, 1, 2], "x": [1, 2, 3]})
    arts: list[str] = []
    out = cohort_sample_id_audit.audit_cohort_sample_id_uniqueness(
        df,
        diagnostics_dir=tmp_path,
        run_id="d1",
        artifact_list=arts,
    )
    assert out["cohort_prepared_rows"] == 3
    assert out["cohort_distinct_sample_id"] == 2
    assert out["cohort_duplicate_surplus_rows"] == 1
    assert (tmp_path / "duplicate_sample_id_cohort_d1.csv").exists()
    assert arts

    ctx: dict = {}
    cohort_sample_id_audit.merge_sample_id_audit_into_manifest(ctx, out)
    assert ctx["cohort_distinct_sample_id"] == 2
    assert ctx["cohort_duplicate_surplus_rows"] == 1
