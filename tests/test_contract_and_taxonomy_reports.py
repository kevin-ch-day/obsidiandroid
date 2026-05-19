"""Tests for run-scoped contract/taxonomy report hygiene."""

from __future__ import annotations

import json
from pathlib import Path

from obsidiandroid.diagnostics import contract_and_taxonomy_reports as reports


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
