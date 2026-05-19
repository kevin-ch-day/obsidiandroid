from __future__ import annotations

import json

from obsidiandroid.diagnostics.research_validity.paper_claim_audit import (
    _markdown_cell,
    write_paper_claim_audit_md,
)


def test_markdown_cell_collapses_newlines_and_escapes_pipes() -> None:
    text = "alpha |\n beta\t gamma"
    rendered = _markdown_cell(text)
    assert rendered == "alpha \\| beta gamma"


def test_write_paper_claim_audit_md_keeps_table_rows_single_line(tmp_path) -> None:
    diagnostics_dir = tmp_path
    run_id = "run123"

    (diagnostics_dir / f"paper_mode_compliance_report_{run_id}.json").write_text(
        json.dumps(
            {
                "overall_status": "pass",
                "checks": [
                    {"check_id": "split_hash_present", "status": "pass"},
                    {"check_id": "taxonomy_mismatch_budget_respected", "status": "pass"},
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = {
        "paper_mode_compliance_report": str(
            diagnostics_dir / f"paper_mode_compliance_report_{run_id}.json"
        ),
        "cohort_summary": {"n_families": 39},
    }
    manifest_context = {
        "paper_mode": {"resolved_value": True},
        "cohort_prepared_row_count": 1187,
        "aligned_supervised_rows": 1187,
        "post_low_support_training_rows": 964,
        "split": {"train_sample_count": 723, "test_sample_count": 241},
        "model_summary": {"top_model": "random_forest"},
    }

    out = write_paper_claim_audit_md(
        diagnostics_dir=diagnostics_dir,
        manifest=manifest,
        manifest_context=manifest_context,
        run_id=run_id,
    )

    text = out.read_text(encoding="utf-8")
    lines = text.splitlines()

    claim_row = next(
        line
        for line in lines
        if line.startswith("| Evidence pack / publication-safe status is materially valid without further operator review |")
    )
    assert "\n" not in claim_row
    assert "overall_status=pass; checks_pass=2/2" in claim_row
    assert len(claim_row.split("|")) >= 8
    assert (diagnostics_dir / "publication_claim_audit.md").exists()
