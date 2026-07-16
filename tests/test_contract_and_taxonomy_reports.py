"""Tests for run-scoped contract/taxonomy report hygiene."""

from __future__ import annotations

import json
from pathlib import Path

from obsidiandroid.diagnostics import contract_and_taxonomy_reports as reports


def test_contract_reports_reuse_run_scoped_outputs(tmp_path: Path, monkeypatch) -> None:
    """Research and operator bundles must not rematerialize the same run report."""
    output_root = tmp_path / "output"
    run_id = "r_cache"
    diagnostics_dir = output_root / "runs" / run_id / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        reports.oh.app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False
    )
    comparison_calls: list[bool] = []

    def _comparison(*_args, **_kwargs):
        comparison_calls.append(True)
        return {
            "headline_feature_column_hash": "h",
            "ablation_full_fused_feature_column_hash": "a",
            "split_hash": "s",
            "label_target": "family_id",
            "apples_to_apples": True,
        }

    monkeypatch.setattr(reports, "build_feature_contract_comparison", _comparison)
    first = reports.write_headline_vs_ablation_contract_reports(diagnostics_dir, run_id)
    second = reports.write_headline_vs_ablation_contract_reports(diagnostics_dir, run_id)
    assert len(comparison_calls) == 1
    assert first[:2] == second[:2]
    assert second[2]["apples_to_apples"] is True

    taxonomy_reads: list[bool] = []

    def _summary(*_args, **_kwargs):
        taxonomy_reads.append(True)
        return {"rows_evaluated": 0, "family_rows_evaluated": 0}

    monkeypatch.setattr(reports, "_read_taxonomy_summary", _summary)
    first_tax = reports.write_taxonomy_type_authority_reports(diagnostics_dir, run_id)
    second_tax = reports.write_taxonomy_type_authority_reports(diagnostics_dir, run_id)
    assert len(taxonomy_reads) == 1
    assert first_tax == second_tax


def test_contract_and_taxonomy_reports_use_global_latest_mirrors_for_run_dirs(
    tmp_path: Path, monkeypatch
) -> None:
    """Run diagnostics should keep run-scoped primaries and move latest mirrors global."""
    output_root = tmp_path / "output"
    run_id = "r100"
    diagnostics_dir = output_root / "runs" / run_id / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        reports.oh.app_config,
        "RUNTIME_OUTPUT_ROOT_BASE",
        str(output_root),
        raising=False,
    )
    monkeypatch.setattr(
        reports,
        "build_feature_contract_comparison",
        lambda *_args, **_kwargs: {
            "headline_feature_column_hash": "abc123",
            "headline_hash_source": "runtime",
            "ablation_full_fused_feature_column_hash": "def456",
            "ablation_summary_source": "summary",
            "split_hash": "split789",
            "label_target": "family_id",
            "apples_to_apples": False,
            "incommensurable_message": "feature hashes differ",
        },
    )

    (diagnostics_dir / f"taxonomy_consistency_summary_{run_id}.json").write_text(
        json.dumps(
            {
                "rows_evaluated": 10,
                "family_rows_evaluated": 10,
                "prediction_error_count": 1,
                "type_mismatch_count": 2,
                "type_missing_label_count": 3,
                "type_noncanonical_count": 0,
                "family_label_mismatch_count": 4,
                "taxonomy_mismatch_count": 5,
            }
        ),
        encoding="utf-8",
    )

    md_path, csv_path, _ = reports.write_headline_vs_ablation_contract_reports(
        diagnostics_dir,
        run_id,
        runtime_headline_hash="abc123",
    )
    tax_md_path, tax_csv_path = reports.write_taxonomy_type_authority_reports(
        diagnostics_dir,
        run_id,
    )

    assert md_path and md_path.exists()
    assert csv_path and csv_path.exists()
    assert tax_md_path and tax_md_path.exists()
    assert tax_csv_path and tax_csv_path.exists()

    assert not (diagnostics_dir / "headline_vs_ablation_contract_comparison.latest.md").exists()
    assert not (diagnostics_dir / "headline_vs_ablation_contract_comparison.latest.csv").exists()
    assert not (diagnostics_dir / "taxonomy_type_authority_review.latest.md").exists()
    assert not (diagnostics_dir / "taxonomy_type_authority_review.latest.csv").exists()

    global_diag = output_root / "diagnostics"
    assert (global_diag / "headline_vs_ablation_contract_comparison.latest.md").exists()
    assert (global_diag / "headline_vs_ablation_contract_comparison.latest.csv").exists()
    assert (global_diag / "taxonomy_type_authority_review.latest.md").exists()
    assert (global_diag / "taxonomy_type_authority_review.latest.csv").exists()


def test_taxonomy_type_authority_report_can_read_global_latest_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    run_id = "r101"
    diagnostics_dir = output_root / "runs" / run_id / "diagnostics"
    global_diag = output_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    global_diag.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        reports.oh.app_config,
        "RUNTIME_OUTPUT_ROOT_BASE",
        str(output_root),
        raising=False,
    )

    (global_diag / "taxonomy_consistency_summary.latest.json").write_text(
        json.dumps(
            {
                "rows_evaluated": 3,
                "family_rows_evaluated": 3,
                "prediction_error_count": 1,
                "type_mismatch_count": 1,
                "type_missing_label_count": 0,
                "type_noncanonical_count": 0,
                "family_label_mismatch_count": 0,
                "taxonomy_mismatch_count": 1,
            }
        ),
        encoding="utf-8",
    )
    (global_diag / "taxonomy_consistency_mismatches.latest.csv").write_text(
        "mismatch_reason,type_slug_expected,label_type_slug\n"
        "type_mapping_mismatch,banker,spyware\n",
        encoding="utf-8",
    )
    (global_diag / "prediction_errors.latest.csv").write_text(
        "sample_id,true_family,predicted_family\n1,A,B\n",
        encoding="utf-8",
    )

    md_path, _csv_path = reports.write_taxonomy_type_authority_reports(diagnostics_dir, run_id)
    text = md_path.read_text(encoding="utf-8")
    assert "family_prediction_errors" in text
    assert "type_mapping_mismatch" in text


def test_taxonomy_authority_split_reports_separate_scopes_and_categories(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    run_id = "r_split"
    diagnostics_dir = output_root / "runs" / run_id / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        reports.oh.app_config,
        "RUNTIME_OUTPUT_ROOT_BASE",
        str(output_root),
        raising=False,
    )
    monkeypatch.setattr(
        reports.oh.app_config,
        "RUNTIME_SPLIT_SAMPLE_METADATA",
        reports.pd.DataFrame(
            [
                {"sample_id": 1},
                {"sample_id": 2},
                {"sample_id": 3},
            ]
        ),
        raising=False,
    )

    (diagnostics_dir / f"taxonomy_consistency_summary_{run_id}.json").write_text(
        json.dumps(
            {
                "type_mismatch_count": 310,
                "type_missing_label_count": 64,
                "type_noncanonical_count": 3,
                "family_label_mismatch_count": 1,
                "prediction_error_count": 2,
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / f"taxonomy_consistency_mismatches_{run_id}.csv").write_text(
        (
            "sample_id,mismatch_reason,type_slug_expected,label_type_slug,label_family_slug,predicted_family\n"
            "1,type_mapping_mismatch,dropper,banker,devixor,Devixor\n"
            "2,type_label_missing,banker,,hiddenad,HiddenAd\n"
            "3,type_label_noncanonical,spyware,spy,spymax,SpyMax\n"
            "4,label_family_mismatch,banker,banker,wrongslug,RightFamily\n"
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / f"prediction_errors_{run_id}.csv").write_text(
        (
            "sample_id,family_canonical_expected,predicted_family,family_prediction_match,type_slug_expected,label_type_slug,classification_label\n"
            "9,Godfather,BankBot,False,banker,banker,trojan/android.banker.bankbot\n"
            "10,Vultur,GoldDigger,False,banker,banker,trojan/android.banker.golddigger\n"
        ),
        encoding="utf-8",
    )

    authority_df = reports.pd.DataFrame(
        [
            {
                "sample_id": 1,
                "authority_bucket": "authority_family_typed",
                "resolved_family_lc": "devixor",
                "authority_gap_reason": "authority_family_typed",
                "family_slug": "devixor",
                "family_name": "Devixor",
                "type_slug": "dropper",
                "raw_vs_authority_status": "raw_conflicts_with_authority",
                "raw_classification_primary": "Trojan",
                "raw_classification_subtype": "Banker",
                "vt_first_submission_at_utc": "2025-01-01T00:00:00Z",
            },
            {
                "sample_id": 2,
                "authority_bucket": "resolved_but_no_authority_family",
                "resolved_family_lc": "blankbot",
                "authority_gap_reason": "resolved_token_not_in_authority_taxonomy",
                "family_slug": "",
                "family_name": "",
                "type_slug": "",
                "raw_vs_authority_status": "authority_unknown",
                "raw_classification_primary": "",
                "raw_classification_subtype": "",
                "vt_first_submission_at_utc": "2025-02-01T00:00:00Z",
            },
            {
                "sample_id": 3,
                "authority_bucket": "generic_label_candidate",
                "resolved_family_lc": "trojan",
                "authority_gap_reason": "resolved_token_coarse_behavior",
                "family_slug": "",
                "family_name": "",
                "type_slug": "",
                "raw_vs_authority_status": "authority_unknown",
                "raw_classification_primary": "",
                "raw_classification_subtype": "",
                "vt_first_submission_at_utc": "2024-01-01T00:00:00Z",
            },
            {
                "sample_id": 4,
                "authority_bucket": "authority_family_unknown_type",
                "resolved_family_lc": "hiddenad",
                "authority_gap_reason": "authority_family_missing_type",
                "family_slug": "hiddenad",
                "family_name": "HiddenAd",
                "type_slug": "unknown",
                "raw_vs_authority_status": "authority_unknown",
                "raw_classification_primary": "",
                "raw_classification_subtype": "",
                "vt_first_submission_at_utc": "2024-03-01T00:00:00Z",
            },
        ]
    )
    monkeypatch.setattr(
        reports,
        "load_authority_df",
        lambda require_live_view=False: (authority_df, "live_view", None),
    )

    md_path, json_path, rendering_csv_path, model_err_csv_path, gap_csv_path = (
        reports.write_taxonomy_authority_split_reports(diagnostics_dir, run_id)
    )

    assert md_path and md_path.exists()
    assert json_path and json_path.exists()
    assert rendering_csv_path.exists()
    assert model_err_csv_path.exists()
    assert gap_csv_path.exists()

    md_text = md_path.read_text(encoding="utf-8")
    assert "Scope: `global_authority_catalog`" in md_text
    assert "Scope: `run_cohort_authority`" in md_text
    assert "Source mode: `live_view`" in md_text
    assert "These are rendering/taxonomy issues, not model-family errors." in md_text
    assert "Count: **2**" in md_text
    assert "blankbot" in md_text
    assert "hiddenad" in md_text
    assert "devixor" in md_text

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["authority_scopes"]["global_authority_catalog"]["source_mode"] == "live_view"
    assert payload["authority_scopes"]["run_cohort_authority"]["available"] is True
    assert payload["taxonomy_split"]["model_prediction_error"]["count"] == 2

    assert rendering_csv_path.name == f"taxonomy_consistency_mismatches_{run_id}.csv"
    assert model_err_csv_path.name == f"prediction_errors_{run_id}.csv"

    gap_df = reports.pd.read_csv(gap_csv_path)
    assert "generic_or_coarse_label_issue" in set(gap_df["summary_group"])
    assert "unknown_type_family_issue" in set(gap_df["summary_group"])


def test_taxonomy_authority_split_reports_degrade_when_live_view_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    run_id = "r_split_missing"
    diagnostics_dir = output_root / "runs" / run_id / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        reports.oh.app_config,
        "RUNTIME_OUTPUT_ROOT_BASE",
        str(output_root),
        raising=False,
    )
    monkeypatch.setattr(
        reports.oh.app_config,
        "RUNTIME_SPLIT_SAMPLE_METADATA",
        None,
        raising=False,
    )
    (diagnostics_dir / f"taxonomy_consistency_summary_{run_id}.json").write_text(
        json.dumps({"prediction_error_count": 0}),
        encoding="utf-8",
    )
    (diagnostics_dir / f"taxonomy_consistency_mismatches_{run_id}.csv").write_text(
        "sample_id,mismatch_reason\n",
        encoding="utf-8",
    )
    (diagnostics_dir / f"prediction_errors_{run_id}.csv").write_text(
        "sample_id,predicted_family\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        reports,
        "load_authority_df",
        lambda require_live_view=False: (
            reports.pd.DataFrame(),
            "live_view_missing",
            "Authority view unavailable; run `database/sql/view_android_sample_family_type_authority.sql` against Erebus before using this diagnostic.",
        ),
    )

    md_path, json_path, rendering_csv_path, model_err_csv_path, gap_csv_path = (
        reports.write_taxonomy_authority_split_reports(diagnostics_dir, run_id)
    )

    assert md_path.exists()
    assert json_path.exists()
    assert rendering_csv_path.exists()
    assert model_err_csv_path.exists()
    assert gap_csv_path.exists()

    md_text = md_path.read_text(encoding="utf-8")
    assert "Run cohort filtering unavailable; report is global catalog authority only." in md_text
    assert "_Unavailable for this run._" in md_text

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["authority_scopes"]["global_authority_catalog"]["available"] is False
    assert payload["authority_scopes"]["run_cohort_authority"]["available"] is False
