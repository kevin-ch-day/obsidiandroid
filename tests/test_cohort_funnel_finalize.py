"""Cohort funnel / row authority assembly."""

from obsidiandroid.diagnostics.research_validity.cohort_funnel import (
    build_cohort_funnel_table,
    classify_main_training_row_authority,
    finalize_cohort_funnel_dict,
    write_cohort_funnel_artifacts,
)
from pathlib import Path


def test_row_authority_intersection_when_alignment_shrinks() -> None:
    assert (
        classify_main_training_row_authority(
            prepared_cohort_rows=100,
            vendor_merge_rows=100,
            fused_feature_rows=100,
            aligned_rows=80,
            main_uses_frozen_zero_fill=False,
        )
        == "intersection"
    )


def test_row_authority_governed_cohort_when_feature_matrix_authority_set() -> None:
    assert (
        classify_main_training_row_authority(
            prepared_cohort_rows=1226,
            vendor_merge_rows=708,
            fused_feature_rows=1226,
            aligned_rows=1200,
            main_uses_frozen_zero_fill=False,
            feature_matrix_row_authority="governed_cohort",
        )
        == "governed_cohort"
    )


def test_finalize_cohort_funnel_populates_manifest_context() -> None:
    ctx: dict = {
        "cohort_sql_scope_row_count": 50,
        "cohort_prepared_row_count": 48,
        "gate_total_candidates": 50,
        "raw_candidate_rows": 50,
        "governed_cohort_rows": 48,
        "vendor_merge_row_count": 48,
        "fused_feature_rows": 48,
        "aligned_supervised_rows": 48,
        "post_low_support_training_rows": 30,
        "feature_matrix_cols_post_prune": 120,
        "train_sample_count": 22,
        "test_sample_count": 8,
    }
    finalize_cohort_funnel_dict(ctx)
    assert ctx.get("main_training_row_authority") == "vendor_available"
    funnel = ctx.get("cohort_funnel")
    assert isinstance(funnel, list) and len(funnel) >= 5
    assert funnel[0]["stage"] == "cohort_sql_scope"
    assert any(row.get("stage") == "prepared_cohort" for row in funnel)
    assert any(row.get("stage") == "training_feature_cols_post_prune" for row in funnel)
    trow = next(r for r in funnel if r.get("stage") == "training_feature_cols_post_prune")
    assert trow.get("column_count") == 120
    assert trow.get("metric_kind") == "training_feature_column_count"


def test_write_cohort_funnel_artifacts_includes_temporal_holdout_section(tmp_path: Path) -> None:
    ctx: dict = {
        "cohort_funnel": [
            {"stage": "prepared_cohort", "row_count": 100, "notes": "prepared"},
            {"stage": "eval_train_rows_split_audit", "row_count": 60, "notes": "train"},
            {"stage": "eval_test_rows_split_audit", "row_count": 20, "notes": "test"},
        ],
        "main_training_row_authority": "governed_cohort",
        "split": {
            "temporal_split_summary": {
                "test_year_floor": 2024,
                "observed_year_min": 2020,
                "observed_year_max": 2025,
                "test_rows_dropped_unseen_train_classes": 219,
            }
        },
    }
    paths = write_cohort_funnel_artifacts(diagnostics_dir=tmp_path, manifest_context=ctx)
    assert any(path.name == "cohort_funnel.md" for path in paths)
    text = (tmp_path / "cohort_funnel.md").read_text(encoding="utf-8")
    assert "## Temporal holdout" in text
    assert "`2024`" in text
    assert "`219`" in text
