"""Tests for feature_builder_drop_trace (no database)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from analysis.diagnostics import feature_builder_drop_trace as fb


def test_load_selected_vendors_from_gate_csv(tmp_path: Path) -> None:
    p = tmp_path / "gate.csv"
    p.write_text("vendor,selected_flag\na,1\nb,0\n", encoding="utf-8")
    assert fb.load_selected_vendors_from_gate_csv(p) == ["a"]


def test_first_missing_stage_top_k() -> None:
    row = pd.Series(
        {
            "in_labels": True,
            "in_av_matrix": True,
            "in_parsed_vendor_any": True,
            "in_vendor_gate_merge": False,
            "in_permission_row": True,
            "in_metadata_row": True,
            "in_enrichment_frame": True,
            "in_final_feature_matrix": False,
        }
    )
    # Uses TRACE_COLUMNS order — attribute access via private helper by rebuilding
    slug = fb.infer_first_missing_stage(row)
    assert slug == "top_k_vendor_field_merge"


def test_build_trace_table_mock_sets() -> None:
    gap = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "sha256": ["a", "b"],
            "family_label": ["X", "Y"],
            "classification_primary": ["", ""],
            "likely_missing_reason": ["unknown_feature_builder_drop"] * 2,
            "has_pi_permissions": [1, 1],
        }
    )
    cohort = pd.DataFrame({"sample_id": [1, 2], "family_canonical": ["X", "Y"]})
    trace = fb.TraceSets(
        cohort_ids={1, 2},
        av_matrix_ids={1},
        parsed_any_ids={1},
        topk_merge_ids={1},
        perm_row_ids={1, 2},
        meta_row_ids={1, 2},
    )
    out = fb.build_trace_table(gap, cohort, trace)
    assert len(out) == 2
    row2 = out[out["sample_id"] == 2].iloc[0]
    assert not bool(row2["in_av_matrix"])
    assert row2["first_missing_stage"] == "av_binary_matrix"


def test_build_summary_dominant() -> None:
    df = pd.DataFrame({"first_missing_stage": ["a", "a", "b"]})
    summary = fb.build_summary(
        df,
        fb.TraceSets({1}, {1}, {1}, {1}, {1}, {1}),
    )
    assert summary["dominant_first_missing_stage"] == "a"
    assert summary["dominant_count"] == 2


def test_write_artifacts(tmp_path: Path) -> None:
    df = pd.DataFrame({"first_missing_stage": ["x"], "sample_id": [1]})
    summary = {"dominant_first_missing_stage": "x", "notes": [], "first_missing_stage_counts": {"x": 1}}
    c, j, m = fb.write_feature_builder_drop_artifacts(df, summary, tmp_path)
    assert c.is_file() and j.is_file() and m.is_file()
