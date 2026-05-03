"""Cohort funnel / row authority assembly."""

from analysis.diagnostics.research_validity.cohort_funnel import (
    classify_main_training_row_authority,
    finalize_cohort_funnel_dict,
)


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
        "feature_matrix_row_count": 120,
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
