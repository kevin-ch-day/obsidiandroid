"""Training-stage alignment attrition propagation."""

from __future__ import annotations

from config import app_config
from obsidiandroid.diagnostics.research_validity.cohort_funnel import (
    build_cohort_funnel_plain,
    describe_trainable_pool_funnel_segment,
    describe_trainable_pool_stage_notes,
    finalize_cohort_funnel_dict,
)
from obsidiandroid.modeling.training_alignment_attrition import (
    apply_training_alignment_attrition_to_manifest,
)


def test_apply_training_alignment_attrition_merges_training_stats(monkeypatch) -> None:
    monkeypatch.setattr(
        app_config,
        "RUNTIME_TRAINING_ALIGNMENT_ATTRITION_STATS",
        {
            "alignment_input_rows": 4563,
            "alignment_non_authoritative_family_drop_count": 211,
            "alignment_rows_post_authority_filter": 4352,
        },
        raising=False,
    )
    monkeypatch.setattr(
        app_config,
        "RUNTIME_TRAINING_ALIGNMENT_ATTRITION_DETAILS",
        {"alignment_non_authoritative_family_drop_families": {"unknown": 211}},
        raising=False,
    )
    ctx: dict = {"aligned_supervised_rows": 4563}
    apply_training_alignment_attrition_to_manifest(ctx)
    assert ctx["coarse_aligned_supervised_rows"] == 4563
    assert ctx["training_authority_aligned_rows"] == 4352
    assert ctx["alignment_attrition_stats"]["alignment_non_authoritative_family_drop_count"] == 211
    assert ctx["alignment_attrition_details"]["alignment_non_authoritative_family_drop_families"]["unknown"] == 211


def test_trainable_pool_notes_authority_only_drop() -> None:
    notes = describe_trainable_pool_stage_notes(
        alignment_attrition={"alignment_non_authoritative_family_drop_count": 211},
        low_support_row_drop_count=0,
        low_support_family_drop_count=0,
        support_floor_mode="diagnostic_only",
    )
    assert "excluded 211 non-authoritative family row(s)" in notes
    assert "diagnostic-only" in notes

    segment = describe_trainable_pool_funnel_segment(
        post_row_count=4352,
        alignment_attrition={"alignment_non_authoritative_family_drop_count": 211},
        low_support_row_drop_count=0,
        low_support_family_drop_count=0,
        support_floor_mode="diagnostic_only",
    )
    assert "4352 post-alignment trainable rows" in segment
    assert "excluded 211 non-authoritative family row(s)" in segment


def test_trainable_pool_notes_unexplained_classifier_pool_drop() -> None:
    notes = describe_trainable_pool_stage_notes(
        alignment_attrition={},
        low_support_row_drop_count=0,
        low_support_family_drop_count=0,
        support_floor_mode="diagnostic_only",
        aligned_row_count=4563,
        trainable_row_count=4352,
    )
    assert "excluded 211 row(s) via classifier trainable-pool filter" in notes
    assert "post-family-support" not in notes


def test_build_cohort_funnel_plain_uses_post_alignment_wording() -> None:
    plain = build_cohort_funnel_plain(
        manifest={"cohort_size": 4563, "train_sample_count": 2185, "test_sample_count": 2167},
        manifest_context={
            "fused_feature_rows": 4563,
            "aligned_supervised_rows": 4563,
            "post_low_support_training_rows": 4352,
            "support_floor_mode": "diagnostic_only",
        },
    )
    assert "post-alignment trainable rows" in plain
    assert "post-family-support" not in plain
    assert "classifier trainable-pool filter" in plain


def test_finalize_cohort_funnel_uses_authority_notes() -> None:
    ctx: dict = {
        "cohort_sql_scope_row_count": 4593,
        "cohort_prepared_row_count": 4563,
        "aligned_supervised_rows": 4563,
        "coarse_aligned_supervised_rows": 4563,
        "training_authority_aligned_rows": 4352,
        "alignment_attrition_stats": {
            "alignment_non_authoritative_family_drop_count": 211,
            "alignment_rows_post_authority_filter": 4352,
        },
        "post_low_support_training_rows": 4352,
        "support_floor_mode": "diagnostic_only",
        "train_sample_count": 2185,
        "test_sample_count": 2167,
    }
    finalize_cohort_funnel_dict(ctx)
    trainable_row = next(
        row for row in ctx["cohort_funnel"] if row.get("stage") == "post_low_support_training_rows"
    )
    assert "excluded 211 non-authoritative family row(s)" in str(trainable_row.get("notes"))
    authority_row = next(
        row for row in ctx["cohort_funnel"] if row.get("stage") == "post_family_authority_filter_rows"
    )
    assert authority_row.get("row_count") == 4352
