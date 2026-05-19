"""Tests for research summary modality fallbacks and notes."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from config import app_config
from obsidiandroid.reporting import research_three_questions as rtq


def test_modality_summary_falls_back_to_runtime_engine_counts_and_notes_raw_permissions(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Q2 summary should avoid misleading 0/0 engine counts and explain disabled permission fusion."""
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    (diagnostics_dir / "cohort_foundation.json").write_text(
        json.dumps(
            {
                "cohort_prepared_row_count": 10,
                "family_type_summary": {
                    "family_count": 2,
                    "type_count": 1,
                    "top_family": "fam_a",
                    "top_family_count": 6,
                    "top_family_share_pct": 60.0,
                    "top3_share_pct": 100.0,
                    "top5_share_pct": 100.0,
                    "family_distribution": {"fam_a": 6, "fam_b": 4},
                    "type_distribution": {"banker": 10},
                },
                "gate_stats": {
                    "excluded_unmapped_family": 0,
                    "excluded_missing_sha256": 0,
                },
                "missing_package_rate_pct": 0.0,
                "missing_vt_timestamp_rate_pct": 0.0,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / "feature_modality_coverage_summary_run1.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "permission_pi_signal_positive_n": 0,
                "vendor_merge_n": 10,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / "modality_method_contract.json").write_text(
        json.dumps(
            {
                "fusion_modality": {"feature_count_permission": 0},
                "permission_modality": {"feature_count_raw": 0},
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / "permission_signal_quality.csv").write_text(
        "metric,value,notes\nsamples_with_any_permission_observation,9,\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(app_config, "RUNTIME_ENGINE_COUNT_INCLUDED_AFTER_GATING", 7, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ENGINE_COUNT_EXCLUDED_AFTER_GATING", 3, raising=False)

    bundle = rtq.write_research_question_artifacts(
        diagnostics_dir=diagnostics_dir,
        run_id="run1",
        profile_id="unit_profile",
        manifest_context={},
        samples_df=pd.DataFrame({"sample_id": list(range(1, 11)), "family_canonical": ["fam_a"] * 6 + ["fam_b"] * 4, "type_slug": ["banker"] * 10}),
        model_results={},
        top_model=None,
    )

    q2 = bundle["q2"]
    assert q2["av_engines_included"] == 7
    assert q2["av_engines_observed"] == 10
    assert any("permission features were disabled" in note for note in q2["interpretation_notes"])

    summary_payload = json.loads((diagnostics_dir / "modality_contribution_summary.json").read_text(encoding="utf-8"))
    assert summary_payload["av_engines_included"] == 7
    assert summary_payload["av_engines_observed"] == 10


def test_modality_summary_computes_raw_permission_fallback_without_csv(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Q2 summary should infer raw permission coverage even before hostile-audit CSV exists."""
    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    (diagnostics_dir / "cohort_foundation.json").write_text(
        json.dumps(
            {
                "cohort_prepared_row_count": 4,
                "family_type_summary": {
                    "family_count": 2,
                    "type_count": 1,
                    "top_family": "fam_a",
                    "top_family_count": 2,
                    "top_family_share_pct": 50.0,
                    "top3_share_pct": 100.0,
                    "top5_share_pct": 100.0,
                    "family_distribution": {"fam_a": 2, "fam_b": 2},
                    "type_distribution": {"banker": 4},
                },
                "gate_stats": {
                    "excluded_unmapped_family": 0,
                    "excluded_missing_sha256": 0,
                },
                "missing_package_rate_pct": 0.0,
                "missing_vt_timestamp_rate_pct": 0.0,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / "feature_modality_coverage_summary_run2.json").write_text(
        json.dumps(
            {
                "run_id": "run2",
                "permission_pi_signal_positive_n": 0,
                "vendor_merge_n": 4,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / "modality_method_contract.json").write_text(
        json.dumps(
            {
                "fusion_modality": {"feature_count_permission": 0},
                "permission_modality": {"feature_count_raw": 0},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(rtq, "_raw_permission_observation_count", lambda _samples_df: 3)

    bundle = rtq.write_research_question_artifacts(
        diagnostics_dir=diagnostics_dir,
        run_id="run2",
        profile_id="unit_profile",
        manifest_context={},
        samples_df=pd.DataFrame(
            {
                "sample_id": [1, 2, 3, 4],
                "family_canonical": ["fam_a", "fam_a", "fam_b", "fam_b"],
                "type_slug": ["banker"] * 4,
            }
        ),
        model_results={},
        top_model=None,
    )

    q2 = bundle["q2"]
    assert q2["permission_raw_observation_n"] == 3
    assert any("Raw permission observations exist in the DB" in note for note in q2["interpretation_notes"])


def test_print_research_questions_terminal_labels_vendor_merge_coverage_honestly() -> None:
    """Run summary should not describe 100% vendor-merge coverage as sparse."""
    captured: list[str] = []

    class _DummyDisplay:
        @staticmethod
        def print_section(_title: str) -> None:
            return None

        @staticmethod
        def print_table(*_args, **_kwargs) -> None:
            return None

    rtq.print_research_questions_terminal(
        {
            "q1": {
                "governed_samples": 10,
                "aligned_supervised_samples": 10,
                "trainable_after_support_filter": 10,
                "families_represented": 2,
                "malware_types_represented": 1,
                "concentration": {
                    "top_family": "fam_a",
                    "top_family_count": 6,
                    "top_family_share_pct": 60.0,
                    "top3_share_pct": 100.0,
                    "top5_share_pct": 100.0,
                },
                "quality_gates": {},
                "supervised_family_claims_suitable": True,
            },
            "q2": {
                "permission_signal_n": 9,
                "permission_signal_pct": 90.0,
                "permission_raw_observation_n": 9,
                "permission_raw_observation_pct": 90.0,
                "permission_feature_columns": 10,
                "vendor_merge_n": 10,
                "vendor_merge_pct": 100.0,
                "av_engines_observed": 5,
                "av_engines_included": 3,
            },
            "q3": {},
            "model_key": "random_forest",
            "macro_f1": 0.9,
            "wf1": 0.91,
            "acc": 0.92,
            "gap_w_m": 0.01,
            "concentration_warn": True,
        },
        pr=captured.append,
        du=_DummyDisplay(),
    )

    text = "\n".join(captured)
    assert "parsed vendor merge full (100.0%)." in text
    assert "parsed vendor merge sparse (100.0%)." not in text


def test_modality_summary_uses_global_feature_column_survival_mirror(make_run_diagnostics_layout) -> None:
    """Q2 feature-group export should still work when run-local `.latest` is intentionally omitted."""
    output_root, diagnostics_dir, global_diag = make_run_diagnostics_layout("run3")

    (diagnostics_dir / "cohort_foundation.json").write_text(
        json.dumps(
            {
                "cohort_prepared_row_count": 2,
                "family_type_summary": {
                    "family_count": 1,
                    "type_count": 1,
                    "top_family": "fam_a",
                    "top_family_count": 2,
                    "top_family_share_pct": 100.0,
                    "top3_share_pct": 100.0,
                    "top5_share_pct": 100.0,
                    "family_distribution": {"fam_a": 2},
                    "type_distribution": {"banker": 2},
                },
                "gate_stats": {
                    "excluded_unmapped_family": 0,
                    "excluded_missing_sha256": 0,
                },
                "missing_package_rate_pct": 0.0,
                "missing_vt_timestamp_rate_pct": 0.0,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / "feature_modality_coverage_summary_run3.json").write_text(
        json.dumps(
            {
                "run_id": "run3",
                "permission_pi_signal_positive_n": 2,
                "vendor_merge_n": 2,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / "modality_method_contract.json").write_text(
        json.dumps(
            {
                "fusion_modality": {"feature_count_permission": 1},
                "permission_modality": {"feature_count_raw": 1},
            }
        ),
        encoding="utf-8",
    )
    (global_diag / "feature_column_survival.latest.csv").write_text(
        "feature_name,nonzero_count_final_training,modality\n"
        "perm__android_CAMERA,2,permission\n",
        encoding="utf-8",
    )

    rtq.write_research_question_artifacts(
        diagnostics_dir=diagnostics_dir,
        run_id="run3",
        profile_id="unit_profile",
        manifest_context={},
        samples_df=pd.DataFrame(
            {
                "sample_id": [1, 2],
                "family_canonical": ["fam_a", "fam_a"],
                "type_slug": ["banker", "banker"],
            }
        ),
        model_results={},
        top_model=None,
    )

    got = pd.read_csv(diagnostics_dir / "feature_group_survival.csv")
    assert got.to_dict(orient="records") == [{"modality": "permission", "n_features": 1}]
