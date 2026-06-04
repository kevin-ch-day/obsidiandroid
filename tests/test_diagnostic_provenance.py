"""Tests for run-scoped diagnostic provenance and lifecycle classification."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from obsidiandroid.diagnostics.diagnostic_provenance import (
    record_diagnostic_provenance,
    resolve_post_run_enrichment_target,
)
from obsidiandroid.diagnostics.output_artifact_policy import classify_file
from obsidiandroid.diagnostics.output_inventory import write_run_science_index_md

pytestmark = pytest.mark.integration


def test_record_pipeline_provenance_tracks_run_and_global_artifacts(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    run_root = output_root / "runs" / "r1"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_manifest = run_root / "run_manifest.json"
    run_manifest.write_text("{}", encoding="utf-8")
    global_latest = output_root / "diagnostics" / "run_manifest.latest.json"
    global_latest.parent.mkdir(parents=True, exist_ok=True)
    global_latest.write_text("{}", encoding="utf-8")

    out_path = record_diagnostic_provenance(
        diagnostics_dir=diagnostics_dir,
        run_root=run_root,
        run_id="r1",
        entry_id="pipeline::r1",
        generated_during_pipeline=True,
        source_command="run_pipeline",
        source_run_id="r1",
        artifact_paths=[str(run_manifest), str(global_latest)],
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    entry = payload["entries"][0]
    assert entry["generated_during_pipeline"] is True
    assert entry["source_command"] == "run_pipeline"
    by_path = {row["path"]: row for row in entry["artifacts"]}
    assert by_path["run_manifest.json"]["lifecycle_class"] == "canonical_run_evidence"
    outside_rows = [row for row in entry["artifacts"] if not row["within_run_root"]]
    assert len(outside_rows) == 1
    assert outside_rows[0]["lifecycle_class"] == "operator_convenience_mirror"


def test_record_post_run_provenance_marks_enrichment(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    run_root = output_root / "runs" / "r1"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    audit_csv = diagnostics_dir / "post_run_enrichments" / "audit1" / "family_label_taxonomy_audit.csv"
    audit_csv.parent.mkdir(parents=True, exist_ok=True)
    audit_csv.write_text("x\n1\n", encoding="utf-8")

    out_path = record_diagnostic_provenance(
        diagnostics_dir=diagnostics_dir,
        run_root=run_root,
        run_id="r1",
        entry_id="post_run::audit1",
        generated_during_pipeline=False,
        source_command="scripts/family_label_taxonomy_audit.py --profile malicious_temporal_stability",
        source_run_id="r1",
        artifact_paths=[str(audit_csv)],
        lifecycle_class="post_run_enrichment",
        extra={"audit_id": "audit1"},
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    entry = payload["entries"][0]
    assert entry["generated_during_pipeline"] is False
    assert entry["lifecycle_class"] == "post_run_enrichment"
    assert entry["audit_id"] == "audit1"
    assert entry["artifacts"][0]["lifecycle_class"] == "post_run_enrichment"
    assert entry["artifacts"][0]["path"] == "diagnostics/post_run_enrichments/audit1/family_label_taxonomy_audit.csv"


def test_resolve_post_run_enrichment_target_routes_run_diagnostics_to_subdir(tmp_path: Path) -> None:
    requested = tmp_path / "output" / "runs" / "r1" / "diagnostics"
    target = resolve_post_run_enrichment_target(diagnostics_dir=requested, audit_id="audit1")

    assert target["artifact_dir"] == requested.resolve() / "post_run_enrichments" / "audit1"
    assert target["provenance_dir"] == requested.resolve()
    assert target["run_root"] == (tmp_path / "output" / "runs" / "r1").resolve()
    assert target["source_run_id"] == "r1"
    assert target["is_run_scoped_enrichment"] is True


def test_write_run_science_index_mentions_post_run_enrichment(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    run_root = output_root / "runs" / "r1"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    (run_root / "run_summary.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / "run_observability_summary.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / "cohort_foundation.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / "cohort_funnel.md").write_text("# funnel\n", encoding="utf-8")
    (run_root / "run_evidence_index.md").write_text("# evidence\n", encoding="utf-8")
    latest_local = diagnostics_dir / "trained_family_registry.latest.csv"
    latest_local.write_text("x\n1\n", encoding="utf-8")
    audit_md = diagnostics_dir / "post_run_enrichments" / "audit1" / "family_label_taxonomy_audit.md"
    audit_md.parent.mkdir(parents=True, exist_ok=True)
    audit_md.write_text("# audit\n", encoding="utf-8")
    record_diagnostic_provenance(
        diagnostics_dir=diagnostics_dir,
        run_root=run_root,
        run_id="r1",
        entry_id="post_run::audit1",
        generated_during_pipeline=False,
        source_command="scripts/family_label_taxonomy_audit.py --profile malicious_temporal_stability",
        source_run_id="r1",
        artifact_paths=[str(audit_md)],
        lifecycle_class="post_run_enrichment",
        extra={"audit_id": "audit1"},
    )

    out_path = write_run_science_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id="r1",
        profile_id="malicious_temporal_stability",
        evidence_mode=False,
        cohort_locked=False,
        publication_ready_status="NOT_APPLICABLE",
    )

    text = out_path.read_text(encoding="utf-8")
    assert "Run Science Index (r1)" in text
    assert "post_run_enrichment" in text
    assert "post_run_enrichments" in text
    assert "prefer run-scoped artifacts over any `.latest` file" in text


def test_write_run_science_index_mentions_authority_coverage_diagnostic(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    run_root = output_root / "runs" / "r_auth"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    (run_root / "run_summary.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / "run_observability_summary.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / "cohort_foundation.json").write_text("{}", encoding="utf-8")
    (run_root / "run_evidence_index.md").write_text("# evidence\n", encoding="utf-8")
    authority_md = diagnostics_dir / "family_type_authority_coverage_r_auth.md"
    authority_md.write_text("# Family/Type Authority Coverage Report\n", encoding="utf-8")

    out_path = write_run_science_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id="r_auth",
        profile_id="paper_locked",
        evidence_mode=True,
        cohort_locked=True,
        publication_ready_status="PASS",
    )

    text = out_path.read_text(encoding="utf-8")
    assert "Advisory Authority Diagnostic" in text
    assert str(authority_md) in text


def test_write_run_science_index_mentions_taxonomy_authority_split(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    run_root = output_root / "runs" / "r_tax"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    (run_root / "run_summary.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / "run_observability_summary.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / "cohort_foundation.json").write_text("{}", encoding="utf-8")
    (run_root / "run_evidence_index.md").write_text("# evidence\n", encoding="utf-8")
    taxonomy_md = diagnostics_dir / "taxonomy_authority_split_r_tax.md"
    taxonomy_md.write_text("# Taxonomy Authority Split\n", encoding="utf-8")

    out_path = write_run_science_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id="r_tax",
        profile_id="paper_locked",
        evidence_mode=True,
        cohort_locked=True,
        publication_ready_status="PASS",
    )

    text = out_path.read_text(encoding="utf-8")
    assert "Taxonomy Authority Split" in text
    assert str(taxonomy_md) in text


def test_write_run_science_index_omits_missing_audit_files(tmp_path: Path) -> None:
    """Run science index should not advertise skipped audit artifacts as authoritative."""
    output_root = tmp_path / "output"
    run_root = output_root / "runs" / "r2"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    (run_root / "run_summary.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / "run_observability_summary.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / "cohort_foundation.json").write_text("{}", encoding="utf-8")

    out_path = write_run_science_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id="r2",
        profile_id="dev_smoke",
        evidence_mode=False,
        cohort_locked=False,
        publication_ready_status="NOT_APPLICABLE",
    )

    text = out_path.read_text(encoding="utf-8")
    assert "cohort_funnel.md" not in text


def test_write_run_science_index_includes_skip_reasons_from_observability(tmp_path: Path) -> None:
    """Evidence index should mirror why research/hostile audits were skipped."""
    output_root = tmp_path / "output"
    run_root = output_root / "runs" / "r_skip"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    (run_root / "run_summary.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / "run_observability_summary.json").write_text(
        json.dumps(
            {
                "pipeline_status": "PASS_WITH_WARNINGS",
                "research_validity_status": "SKIPPED",
                "research_validity_skip_reason": "stop_after_samples",
                "hostile_audit_status": "SKIPPED",
                "hostile_audit_skip_reason": "stop_after_samples",
                "publication_ready_status": "NOT_APPLICABLE",
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / "cohort_foundation.json").write_text("{}", encoding="utf-8")

    out_path = write_run_science_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id="r_skip",
        profile_id="dev_smoke",
        evidence_mode=False,
        cohort_locked=False,
        publication_ready_status="NOT_APPLICABLE",
    )

    text = out_path.read_text(encoding="utf-8")
    assert "research_validity_status:** `SKIPPED` (stop_after_samples)" in text
    assert "hostile_audit_status:** `SKIPPED` (stop_after_samples)" in text


def test_write_run_science_index_includes_cohort_filter_highlights(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    run_root = output_root / "runs" / "r_filter"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    (run_root / "run_summary.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / "run_observability_summary.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / "cohort_foundation.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / "cohort_funnel.md").write_text("# funnel\n", encoding="utf-8")
    (diagnostics_dir / "cohort_filter_contract_r_filter.json").write_text(
        json.dumps({"cohort_gates": {"min_malicious_detections": 5}}),
        encoding="utf-8",
    )
    (diagnostics_dir / "analysis_snapshot_filter_summary_r_filter.csv").write_text(
        "mode,source_total,post_filter_total\npaper_locked_snapshot_membership,100,98\n",
        encoding="utf-8",
    )
    (diagnostics_dir / "cohort_gate_counts_r_filter.csv").write_text(
        (
            "run_id,step,gate_name,count_before,count_after,dropped,details\n"
            "r_filter,1,paper_locked_snapshot_membership,100,98,2,"
            "\"sample_id lock applied before dataset/contract gates\"\n"
            "r_filter,2,min_malicious_detections,98,97,1,"
            "\">=5; rescued_unknown_consensus=3\"\n"
        ),
        encoding="utf-8",
    )

    out_path = write_run_science_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id="r_filter",
        profile_id="paper2_demo",
        evidence_mode=False,
        cohort_locked=True,
        publication_ready_status="READY",
    )

    text = out_path.read_text(encoding="utf-8")
    assert "membership_mode:** `paper_locked_snapshot_membership`" in text
    assert "locked_membership_note" in text
    assert "rescued_unknown_consensus=`3`" in text


def test_classify_file_marks_run_local_latest_as_legacy_and_global_latest_as_operator(tmp_path: Path) -> None:
    output_root = tmp_path / "output"
    run_root = output_root / "runs" / "r1"
    run_diag = run_root / "diagnostics"
    run_diag.mkdir(parents=True, exist_ok=True)
    run_latest = run_diag / "taxonomy_consistency_summary.latest.json"
    run_latest.write_text("{}", encoding="utf-8")
    global_latest = output_root / "diagnostics" / "run_manifest.latest.json"
    global_latest.parent.mkdir(parents=True, exist_ok=True)
    global_latest.write_text("{}", encoding="utf-8")

    run_meta = classify_file(run_latest, base=run_root)
    global_meta = classify_file(global_latest, base=output_root)

    assert run_meta["lifecycle_class"] == "legacy_compatibility"
    assert global_meta["lifecycle_class"] == "operator_convenience_mirror"


def test_classify_file_marks_post_run_enrichment_subtree(tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "r1"
    audit_csv = run_root / "diagnostics" / "post_run_enrichments" / "audit1" / "family_label_taxonomy_audit.csv"
    audit_csv.parent.mkdir(parents=True, exist_ok=True)
    audit_csv.write_text("x\n1\n", encoding="utf-8")

    meta = classify_file(audit_csv, base=run_root)

    assert meta["artifact_bucket"] == "diagnostics_optional"
    assert meta["lifecycle_class"] == "post_run_enrichment"
