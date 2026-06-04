"""Tests for feature_matrix_gap_lineage (no DB)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from obsidiandroid.diagnostics import feature_matrix_gap_lineage as fmgl


def test_infer_primary_row_loss_stage_vendor_gap() -> None:
    out = fmgl.infer_primary_row_loss_stage(cohort_rows=2571, av_binary_rows=2571, vendor_merge_rows=2142)
    assert out["stage"] == "vendor_encoded_merge_top_k"


def test_infer_primary_row_loss_stage_av_gap() -> None:
    out = fmgl.infer_primary_row_loss_stage(cohort_rows=2571, av_binary_rows=2400, vendor_merge_rows=2142)
    assert out["stage"] == "av_binary_matrix"


def test_analyze_fusion_vs_training_columns() -> None:
    modality = {
        "fusion_modality": {"feature_count_total": 829, "matrix_shape": {"columns": 829}},
        "permission_modality": {"feature_count_raw": 677},
    }
    training_cols = ["perm__a", "perm__b", "meta__x"] + [f"c{i}" for i in range(174)]
    out = fmgl.analyze_fusion_vs_training_columns(modality, training_cols)
    assert out["fusion_matrix_columns_total"] == 829
    assert out["fusion_permission_columns_before_training_prune"] == 677
    assert out["permission_columns_dropped_as_low_information"] == 677 - 2


def test_run_gap_report_filesystem_only(tmp_path: Path) -> None:
    diag = tmp_path / "diagnostics"
    diag.mkdir(parents=True)
    cohort = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "sha256": ["a", "b", "c"],
            "family_canonical": ["F", "F", "G"],
        }
    )
    cohort.to_csv(diag / "cohort_membership.csv", index=False)
    pd.DataFrame({"sample_id": [3]}).to_csv(diag / "unmatched_label_ids.csv", index=False)

    (diag / "feature_build_coverage.latest.json").write_text(
        json.dumps(
            {
                "feature_matrix_unique_row_count": 2,
                "vendor_merge_authority_unique_count": 2,
                "cohort_rows_missing_from_feature_matrix": 1,
                "vendor_merge_equals_final_index": True,
                "feature_rows_not_in_cohort": 0,
            }
        ),
        encoding="utf-8",
    )
    (diag / "cohort_missing_from_feature_matrix.latest.csv").write_text(
        "sample_id\n3\n", encoding="utf-8"
    )
    (diag / "modality_method_contract.json").write_text(
        json.dumps(
            {
                "fusion_modality": {"feature_count_total": 829, "matrix_shape": {"columns": 829}},
                "permission_modality": {"feature_count_raw": 677},
            }
        ),
        encoding="utf-8",
    )
    (diag / "feature_contract.json").write_text(
        json.dumps(
            {
                "feature_columns": ["perm__x", "meta__y"],
                "feature_shape": {"rows": 2, "columns": 2},
            }
        ),
        encoding="utf-8",
    )

    lineage_df, gap_detail, summary = fmgl.run_feature_matrix_gap_report(tmp_path, skip_db_recompute=True)
    assert len(lineage_df) == 3
    assert summary["row_loss"]["cohort_samples_locked"] == 3
    assert summary["row_loss"]["feature_matrix_rows_pre_alignment"] == 2
    assert (diag / "feature_matrix_gap_summary.json").is_file()
    assert (diag / "feature_matrix_row_lineage.csv").is_file()


def test_run_gap_report_cohort_rows_use_distinct_sample_id(tmp_path: Path) -> None:
    """Table row count can exceed distinct sample_id; stage cohort_rows matches nunique."""
    diag = tmp_path / "diagnostics"
    diag.mkdir(parents=True)
    cohort = pd.DataFrame(
        {
            "sample_id": [1, 1, 2, 3],
            "sha256": ["a", "a_dup", "b", "c"],
            "family_canonical": ["F", "F", "F", "G"],
        }
    )
    cohort.to_csv(diag / "cohort_membership.csv", index=False)
    pd.DataFrame({"sample_id": [3]}).to_csv(diag / "unmatched_label_ids.csv", index=False)

    (diag / "feature_build_coverage.latest.json").write_text(
        json.dumps(
            {
                "feature_matrix_unique_row_count": 2,
                "vendor_merge_authority_unique_count": 2,
                "cohort_rows_missing_from_feature_matrix": 1,
                "vendor_merge_equals_final_index": True,
                "feature_rows_not_in_cohort": 0,
            }
        ),
        encoding="utf-8",
    )
    (diag / "cohort_missing_from_feature_matrix.latest.csv").write_text(
        "sample_id\n3\n", encoding="utf-8"
    )
    for name, payload in (
        (
            "modality_method_contract.json",
            {
                "fusion_modality": {"feature_count_total": 10, "matrix_shape": {"columns": 10}},
                "permission_modality": {"feature_count_raw": 5},
            },
        ),
        (
            "feature_contract.json",
            {"feature_columns": ["c0"], "feature_shape": {"rows": 2, "columns": 1}},
        ),
    ):
        (diag / name).write_text(json.dumps(payload), encoding="utf-8")

    _lineage_df, _gap_detail, summary = fmgl.run_feature_matrix_gap_report(tmp_path, skip_db_recompute=True)
    sc = summary["stage_row_counts"]
    assert sc["cohort_rows"] == 3
    assert sc["cohort_prepared_table_rows"] == 4
    assert sc["cohort_duplicate_surplus_rows"] == 1
    assert summary["row_loss"]["cohort_samples_locked"] == 3


def test_run_gap_report_prefers_manifest_run_id_for_slot_root(tmp_path: Path) -> None:
    run_id = "20260604T033648Z__d79069"
    run_root = tmp_path / "majorfam_benchmark"
    diag = run_root / "diagnostics"
    diag.mkdir(parents=True)
    (run_root / "run_manifest.json").write_text(
        json.dumps({"run_id": run_id, "run_root": str(run_root)}),
        encoding="utf-8",
    )
    cohort = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "sha256": ["a", "b"],
            "family_canonical": ["F", "G"],
        }
    )
    cohort.to_csv(diag / "cohort_membership.csv", index=False)
    pd.DataFrame({"sample_id": [2]}).to_csv(diag / "unmatched_label_ids.csv", index=False)
    (diag / f"feature_build_coverage_{run_id}.json").write_text(
        json.dumps(
            {
                "feature_matrix_unique_row_count": 1,
                "vendor_merge_authority_unique_count": 1,
                "cohort_rows_missing_from_feature_matrix": 1,
                "vendor_merge_equals_final_index": True,
                "feature_rows_not_in_cohort": 0,
            }
        ),
        encoding="utf-8",
    )
    (diag / "cohort_missing_from_feature_matrix.latest.csv").write_text("sample_id\n2\n", encoding="utf-8")
    (diag / "modality_method_contract.json").write_text(
        json.dumps({"fusion_modality": {"feature_count_total": 2, "matrix_shape": {"columns": 2}}}),
        encoding="utf-8",
    )
    (diag / "feature_contract.json").write_text(
        json.dumps({"feature_columns": ["perm__x"], "feature_shape": {"rows": 1, "columns": 1}}),
        encoding="utf-8",
    )

    _lineage_df, _gap_detail, summary = fmgl.run_feature_matrix_gap_report(run_root, skip_db_recompute=True)

    assert summary["run_id"] == run_id
