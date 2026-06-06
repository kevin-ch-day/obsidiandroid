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
    assert lines[0] == "# Publication claim audit (machine-assisted, strict)"
    assert "Primary surface:** locked publication cohort" in text

    claim_row = next(
        line
        for line in lines
        if line.startswith("| Evidence pack / publication-ready status is materially valid without further operator review |")
    )
    assert "\n" not in claim_row
    assert "overall_status=pass; checks_pass=2/2" in claim_row
    assert len(claim_row.split("|")) >= 8
    assert (diagnostics_dir / "publication_claim_audit.md").exists()
    assert (diagnostics_dir / "benchmark_claim_audit.md").exists()
    assert (diagnostics_dir / "research_claim_audit.md").exists()


def test_write_paper_claim_audit_md_can_use_global_latest_ablation_and_model_summary(
    tmp_path,
    monkeypatch,
) -> None:
    diagnostics_dir = tmp_path / "output" / "runs" / "run123" / "diagnostics"
    global_diag = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    global_diag.mkdir(parents=True, exist_ok=True)

    from config import app_config

    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(tmp_path / "output"), raising=False)

    (diagnostics_dir / "paper_mode_compliance_report_run123.json").write_text(
        json.dumps({"overall_status": "pass", "checks": []}),
        encoding="utf-8",
    )
    (global_diag / "ablation_summary.latest.csv").write_text(
        "label_target,experiment,macro_f1_score\n"
        "family_id,full_fused,0.90\n"
        "family_id,vendor_no_parsed_family,0.80\n"
        "family_id,permissions_raw,0.50\n",
        encoding="utf-8",
    )
    (global_diag / "model_comparison_summary.latest.csv").write_text(
        "Model,Macro-F1 Score\nrandom_forest,0.91\nxgboost,0.89\n",
        encoding="utf-8",
    )

    out = write_paper_claim_audit_md(
        diagnostics_dir=diagnostics_dir,
        manifest={
            "paper_mode_compliance_report": str(diagnostics_dir / "paper_mode_compliance_report_run123.json")
        },
        manifest_context={"paper_mode": {"resolved_value": True}},
        run_id="run123",
    )

    text = out.read_text(encoding="utf-8")
    assert "full_fused=0.9; safer_vendor_baseline=0.8" in text
    assert "random_forest / Macro-F1≈0.9100" in text or "random_forest" in text
    assert "publication/evidence mode ON" in text


def test_write_paper_claim_audit_md_uses_benchmark_heading_for_non_publication_surface(tmp_path) -> None:
    out = write_paper_claim_audit_md(
        diagnostics_dir=tmp_path,
        manifest={},
        manifest_context={"benchmark_support_floor": 3, "cohort_prepared_row_count": 1231},
        run_id="run_bench",
    )

    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Benchmark claim audit (machine-assisted, strict)")
    assert "Primary surface:** major-family benchmark surface" in text


def test_write_paper_claim_audit_md_marks_expanded_profile_as_exploratory(tmp_path) -> None:
    out = write_paper_claim_audit_md(
        diagnostics_dir=tmp_path,
        manifest={"profile_params": {"profile_id": "android_malware_expanded_families"}},
        manifest_context={"benchmark_support_floor": 3, "cohort_prepared_row_count": 640},
        run_id="run_expanded",
    )

    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Expanded-family exploratory claim audit (machine-assisted, strict)")
    assert "Primary surface:** expanded-family exploratory surface" in text


def test_write_paper_claim_audit_md_treats_resolved_false_evidence_metadata_as_off(tmp_path) -> None:
    out = write_paper_claim_audit_md(
        diagnostics_dir=tmp_path,
        manifest={"profile_params": {"profile_id": "android_malware_all_current"}},
        manifest_context={
            "evidence_mode": {"resolved_value": False, "source": "profile"},
            "paper_mode": {"resolved_value": False, "source": "profile"},
            "cohort_prepared_row_count": 4563,
        },
        run_id="run_diag",
    )

    text = out.read_text(encoding="utf-8")
    assert "Primary surface:** broad current-corpus diagnostic surface" in text
    assert "locked publication surface" not in text.lower()


def test_write_paper_claim_audit_md_marks_type_taxonomy_surface(tmp_path) -> None:
    out = write_paper_claim_audit_md(
        diagnostics_dir=tmp_path,
        manifest={"profile_params": {"profile_id": "android_malware_type_taxonomy"}},
        manifest_context={"benchmark_support_floor": 3, "cohort_prepared_row_count": 640},
        run_id="run_type_taxonomy",
    )

    text = out.read_text(encoding="utf-8")
    assert text.startswith("# Type-taxonomy claim audit (machine-assisted, strict)")
    assert "Primary surface:** type-taxonomy benchmark surface" in text
