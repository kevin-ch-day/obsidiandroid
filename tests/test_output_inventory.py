"""Tests for output artifact classification and inventory helpers."""

from __future__ import annotations

import io
import json
from pathlib import Path

from config import app_config
from obsidiandroid.diagnostics import output_artifact_policy
from obsidiandroid.diagnostics import output_inventory
from obsidiandroid.tools import output_retention_audit as ora
from scripts.diagnostics import report_output_inventory as roi
import pytest


@pytest.fixture(scope="module")
def _audit_mod():
    pytest.importorskip("scripts.dev.output_writer_audit", reason="scripts package not on path")
    from scripts.dev import output_writer_audit as mod

    return mod


def test_collect_hits_pipeline_sample(_audit_mod) -> None:
    hits = _audit_mod.collect_hits([Path(__file__).resolve().parents[1] / "src" / "obsidiandroid" / "pipeline"])
    assert hits, "expected output-related writes under obsidiandroid/pipeline"
    assert any("sample_exports.py" in h.rel_path for h in hits)
    assert any("mirror_csv_text_run_then_global" in h.target_expr for h in hits)


def test_emit_csv_header_and_rows(_audit_mod) -> None:
    hits = _audit_mod.collect_hits([Path(__file__).resolve().parents[1] / "src" / "obsidiandroid" / "pipeline"])
    hits = [h for h in hits if "sample_exports.py" in h.rel_path]
    assert hits
    buf = io.StringIO()
    _audit_mod.emit_csv(hits, buf)
    lines = buf.getvalue().splitlines()
    assert lines[0].startswith("module,function,write_pattern")
    assert len(lines) >= 2


def test_classify_run_manifest_is_evidence_required() -> None:
    meta = output_artifact_policy.classify_relative_path("run_manifest.json")
    assert meta["artifact_bucket"] == "evidence_required"


def test_classify_unknown_defaults_optional() -> None:
    meta = output_artifact_policy.classify_relative_path("diagnostics/foo_bar_unknown.xyz")
    assert meta["artifact_bucket"] == "diagnostics_optional"


def test_build_inventory_rows_counts_files(tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "r1"
    (run_root / "diagnostics").mkdir(parents=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    (run_root / "diagnostics" / "note.txt").write_text("x", encoding="utf-8")
    rows = output_inventory.build_inventory_rows(run_root)
    assert len(rows) == 2
    kinds = {r["path"]: r["artifact_type"] for r in rows}
    assert kinds["run_manifest.json"] == "evidence_required"


def test_report_output_inventory_resolves_archived_run_id(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    run_id = "20260303T000000Z__abc123"
    run_root = repo_root / "output" / "runs" / "_archived" / "kept" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text(
        json.dumps({"run_id": run_id, "run_root": str(run_root), "created_at_utc": "2026-03-03T00:00:00+00:00"}),
        encoding="utf-8",
    )

    got = roi._resolve_run_root(  # pylint: disable=protected-access
        repo_root=repo_root,
        run_root_arg="",
        run_id=run_id,
        latest=False,
    )

    assert got == run_root.resolve()


def test_report_output_inventory_latest_prefers_manifest_backed_run(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    run_id = "20260303T000000Z__abc123"
    run_root = repo_root / "output" / "runs" / "_archived" / "kept" / run_id
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text(
        json.dumps({"run_id": run_id, "run_root": str(run_root), "created_at_utc": "2026-03-03T00:00:00+00:00"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(roi.rl, "read_latest_run_id", lambda: run_id)

    got = roi._resolve_run_root(  # pylint: disable=protected-access
        repo_root=repo_root,
        run_root_arg="",
        run_id="",
        latest=True,
    )

    assert got == run_root.resolve()


def test_report_output_inventory_uses_manifest_run_id_for_slot_root(tmp_path: Path) -> None:
    run_id = "20260604T033648Z__d79069"
    run_root = tmp_path / "output" / "runs" / "majorfam_benchmark"
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text(
        json.dumps({"run_id": run_id, "run_root": str(run_root)}),
        encoding="utf-8",
    )

    got = roi._resolve_run_id(run_root)  # pylint: disable=protected-access

    assert got == run_id


def test_write_artifact_inventory_bundle_separates_legacy_latest_compatibility(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "output" / "runs" / "r_inv"
    diagnostics_dir = run_root / "diagnostics"
    figures_dir = run_root / "bundles" / "permission_trends" / "figures"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    (figures_dir / "type_permission_heatmap.latest.png").write_text("x", encoding="utf-8")

    paths, summary = output_inventory.write_artifact_inventory_bundle(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id="r_inv",
        manifest_paths=[],
        extra_summary=None,
    )

    assert paths == [
        str(diagnostics_dir / "artifact_inventory.json"),
        str(diagnostics_dir / "artifact_inventory.csv"),
    ]
    assert not (diagnostics_dir / "artifact_inventory.md").exists()
    assert summary["duplicate_latest_inside_run"] == 1
    assert summary["duplicate_latest_inside_run_legacy_compatibility"] == 1
    assert summary["duplicate_latest_inside_run_policy_drift"] == 0


@pytest.mark.integration
def test_write_run_evidence_index_prefers_canonical_feature_build_coverage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    run_id = "r_cov"
    run_root = output_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)

    (diagnostics_dir / f"feature_build_coverage_{run_id}.json").write_text(
        json.dumps({"missing_from_feature_matrix_count": 7}),
        encoding="utf-8",
    )
    (diagnostics_dir / "run_observability_summary.json").write_text("{}", encoding="utf-8")

    out_path = output_inventory.write_run_evidence_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="dev_smoke",
        paper_mode=False,
        cohort_size=10,
        manifest={},
        manifest_context={},
        trained_models=[],
        publication_ready_status="NOT_APPLICABLE",
        publication_ready_reasons=[],
    )

    text = out_path.read_text(encoding="utf-8")
    assert "Missing-from-feature-matrix count (coverage export):** 7" in text


@pytest.mark.integration
def test_write_run_evidence_index_includes_authority_coverage_pointer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    run_id = "r_auth"
    run_root = output_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)

    (diagnostics_dir / f"family_type_authority_coverage_{run_id}.md").write_text(
        "# Family/Type Authority Coverage Report\n",
        encoding="utf-8",
    )
    (diagnostics_dir / "run_observability_summary.json").write_text("{}", encoding="utf-8")

    out_path = output_inventory.write_run_evidence_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="paper_locked",
        paper_mode=True,
        cohort_size=10,
        manifest={},
        manifest_context={},
        trained_models=[],
        publication_ready_status="PASS",
        publication_ready_reasons=[],
    )

    text = out_path.read_text(encoding="utf-8")
    assert "Authority coverage diagnostic:" in text
    assert f"family_type_authority_coverage_{run_id}.md" in text


@pytest.mark.integration
def test_write_run_evidence_index_includes_taxonomy_authority_split_pointer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    run_id = "r_taxsplit"
    run_root = output_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)

    (diagnostics_dir / f"taxonomy_authority_split_{run_id}.md").write_text(
        "# Taxonomy Authority Split\n",
        encoding="utf-8",
    )
    (diagnostics_dir / "run_observability_summary.json").write_text("{}", encoding="utf-8")

    out_path = output_inventory.write_run_evidence_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="paper_locked",
        paper_mode=True,
        cohort_size=10,
        manifest={},
        manifest_context={},
        trained_models=[],
        publication_ready_status="PASS",
        publication_ready_reasons=[],
    )

    text = out_path.read_text(encoding="utf-8")
    assert "Taxonomy authority split:" in text
    assert f"taxonomy_authority_split_{run_id}.md" in text


@pytest.mark.integration
def test_write_run_evidence_index_surfaces_label_resolution_disabled_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    run_id = "r_obs_disabled"
    run_root = output_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)

    (diagnostics_dir / "run_observability_summary.json").write_text(
        json.dumps(
            {
                "pipeline_status": "PASS",
                "research_validity_status": "SKIPPED",
                "hostile_audit_status": "SKIPPED",
                "publication_ready_status": "NOT_APPLICABLE",
                "label_resolution_enabled": False,
            }
        ),
        encoding="utf-8",
    )

    out_path = output_inventory.write_run_evidence_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="dev_smoke",
        paper_mode=False,
        cohort_size=10,
        manifest={},
        manifest_context={},
        trained_models=[],
        publication_ready_status="NOT_APPLICABLE",
        publication_ready_reasons=[],
    )

    text = out_path.read_text(encoding="utf-8")
    assert "**label_resolution:** `DISABLED`" in text
    assert "**type_guard_family_suppressions:** unavailable (label resolution disabled)" in text


@pytest.mark.integration
def test_write_run_science_index_surfaces_type_guard_suppression_count(
    tmp_path: Path,
) -> None:
    run_id = "r_obs_enabled"
    run_root = tmp_path / "output" / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    (run_root / "run_summary.json").write_text("{}", encoding="utf-8")
    (run_root / "run_evidence_index.md").write_text("# evidence\n", encoding="utf-8")
    (diagnostics_dir / "artifact_inventory.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / "run_observability_summary.json").write_text(
        json.dumps(
            {
                "pipeline_status": "PASS",
                "research_validity_status": "PASS",
                "hostile_audit_status": "PASS",
                "publication_ready_status": "PASS",
                "label_resolution_enabled": True,
                "type_guard_family_suppressed_count": 6,
            }
        ),
        encoding="utf-8",
    )

    out_path = output_inventory.write_run_science_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="dev_smoke",
        evidence_mode=False,
        cohort_locked=False,
        publication_ready_status="NOT_APPLICABLE",
    )

    text = out_path.read_text(encoding="utf-8")
    assert "**label_resolution:** `ENABLED`" in text
    assert "**type_guard_family_suppressions:** 6" in text


@pytest.mark.integration
def test_write_run_evidence_index_surfaces_claim_surface_and_claim_audit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    run_id = "r_claim_index"
    run_root = output_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)

    (diagnostics_dir / "run_observability_summary.json").write_text(
        json.dumps(
            {
                "claim_surface_label": "Current-corpus diagnostic surface",
                "claim_audit_summary": str(diagnostics_dir / "research_claim_audit.md"),
            }
        ),
        encoding="utf-8",
    )

    out_path = output_inventory.write_run_evidence_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="android_malware_all_current",
        paper_mode=False,
        cohort_size=10,
        manifest={},
        manifest_context={},
        trained_models=[],
        publication_ready_status="NOT_APPLICABLE",
        publication_ready_reasons=[],
    )

    text = out_path.read_text(encoding="utf-8")
    assert "**claim_surface:** `Current-corpus diagnostic surface`" in text
    assert "research_claim_audit.md" in text


@pytest.mark.integration
def test_write_run_evidence_index_lists_v3_seed_exports(tmp_path: Path, monkeypatch) -> None:
    output_root = tmp_path / "output"
    run_id = "r_v3_seed"
    run_root = output_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)

    for name in (
        f"v3_label_contract_{run_id}.md",
        f"permission_pattern_contract_{run_id}.md",
        f"ml_run_manifest_{run_id}.json",
        f"ml_sample_label_fact_{run_id}.csv",
        f"ml_permission_vocabulary_{run_id}.json",
        f"ml_permission_pattern_fact_{run_id}.csv",
        f"split_freeze_headline_{run_id}.csv",
        f"v3_dl_handoff_summary_{run_id}.json",
    ):
        if name.endswith(".json"):
            (diagnostics_dir / name).write_text(
                json.dumps({"dl_seed_status": "ready"}),
                encoding="utf-8",
            )
        else:
            (diagnostics_dir / name).write_text("x\n", encoding="utf-8")

    out_path = output_inventory.write_run_evidence_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="android_malware_major_families",
        paper_mode=False,
        cohort_size=10,
        manifest={},
        manifest_context={},
        trained_models=[],
        publication_ready_status="NOT_APPLICABLE",
        publication_ready_reasons=[],
    )

    text = out_path.read_text(encoding="utf-8")
    assert "## V3 research contracts (open first)" in text
    assert "ML sample label fact" in text
    assert "ML permission vocabulary" in text
    assert "ML permission pattern fact" in text
    assert "DL seed handoff status" in text
    assert "V3 DL handoff summary" in text
    assert "Frozen train/test split ledger" in text


@pytest.mark.integration
def test_write_run_science_index_surfaces_claim_surface_and_claim_audit(
    tmp_path: Path,
) -> None:
    run_id = "r_claim_science"
    run_root = tmp_path / "output" / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    (run_root / "run_summary.json").write_text("{}", encoding="utf-8")
    (run_root / "run_evidence_index.md").write_text("# evidence\n", encoding="utf-8")
    (diagnostics_dir / "artifact_inventory.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / "run_observability_summary.json").write_text(
        json.dumps(
            {
                "claim_surface_label": "Support-gated benchmark cohort",
                "claim_audit_summary": str(diagnostics_dir / "benchmark_claim_audit.md"),
                "publication_ready_status": "NOT_APPLICABLE",
            }
        ),
        encoding="utf-8",
    )

    out_path = output_inventory.write_run_science_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="android_malware_major_families",
        evidence_mode=False,
        cohort_locked=False,
        publication_ready_status="NOT_APPLICABLE",
    )

    text = out_path.read_text(encoding="utf-8")
    assert "claim_surface: `Support-gated benchmark cohort`" in text
    assert "benchmark_claim_audit.md" in text


@pytest.mark.integration
def test_write_run_evidence_index_includes_shared_backlog_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    run_id = "r_backlog"
    run_root = output_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    (diagnostics_dir / "run_observability_summary.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / f"backlog_debt_summary_{run_id}.md").write_text("# Backlog\n", encoding="utf-8")

    monkeypatch.setattr(
        output_inventory,
        "get_cohort_readiness_snapshot",
        lambda: {
            "status": "ok",
            "warnings": [],
            "taxonomy_signals": {
                "missing_primary_label_samples": 11,
                "missing_primary_label_raw_samples": 11,
                "missing_primary_label_actionable_samples": 0,
                "missing_primary_label_residual_samples": 11,
                "missing_primary_label_suppressed_samples": 4,
                "missing_primary_label_active_residual_samples": 7,
                "missing_primary_label_lane_counts": {
                    "public_package_identity_provenance_review": 7,
                    "already_sample_suppressed": 4,
                },
                "unresolved_family_samples": 0,
                "policy_held_family_samples": 4,
                "family_type_conflict_count": 2,
            },
        },
    )
    monkeypatch.setattr(
        output_inventory,
        "read_android_missing_resolution_snapshot",
        lambda **_kwargs: {
            "path": output_root / "diagnostics" / "android_missing_resolution_triage_latest.csv",
            "row_count": 9,
            "freshness": "current",
            "top_lane": "blank_package_review",
            "top_lane_count": 5,
            "lane_counts": {"blank_package_review": 5},
        },
    )
    monkeypatch.setattr(
        output_inventory,
        "read_false_positive_triage_snapshot",
        lambda **_kwargs: {
            "path": output_root / "diagnostics" / "vt_false_positive_review_triage_latest.csv",
            "row_count": 3,
            "freshness": "current",
            "top_lane": "file_artifact_review",
            "top_lane_count": 2,
            "lane_counts": {"file_artifact_review": 2},
        },
    )
    monkeypatch.setattr(
        output_inventory,
        "read_policy_held_token_risk_snapshot",
        lambda **_kwargs: {
            "path": output_root / "diagnostics" / "android_policy_held_token_risk_latest.csv",
            "row_count": 4,
            "freshness": "current",
            "top_lane": "class_label_not_family",
            "top_lane_count": 2,
            "lane_counts": {"class_label_not_family": 2},
            "token_kind_counts": {"behavior_class_token": 2},
        },
    )

    out_path = output_inventory.write_run_evidence_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="paper_locked",
        paper_mode=True,
        cohort_size=10,
        manifest={},
        manifest_context={},
        trained_models=[],
        publication_ready_status="PASS",
        publication_ready_reasons=[],
    )

    text = out_path.read_text(encoding="utf-8")
    assert "## Backlog and operator queues" in text
    assert "Focus area:** Missing primary labels (11 row(s))" in text
    assert "Focus detail:** Active/actionable Android + PI missing-primary debt; raw_missing=11; actionable=0; suppressed=4; active_residual=7." in text
    assert "Missing-primary lane split:** public_package_identity_provenance_review=7, already_sample_suppressed=4" in text
    assert "Priority queue:** Android missing-resolution triage [freshness=current]" in text
    assert "android missing-resolution triage:" in text
    assert "vt false-positive triage:" in text
    assert "policy-held token risk:" in text
    assert f"backlog_debt_summary_{run_id}.md" in text


def test_write_artifact_inventory_bundle_removes_stale_markdown_copy(tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "r_stale"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    stale_md = diagnostics_dir / "artifact_inventory.md"
    stale_md.write_text("# stale\n", encoding="utf-8")

    output_inventory.write_artifact_inventory_bundle(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id="r_stale",
        manifest_paths=[],
        extra_summary=None,
    )

    assert not stale_md.exists()


@pytest.mark.integration
def test_write_run_science_index_includes_backlog_authoritative_pointer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_id = "r_science_backlog"
    run_root = tmp_path / "output" / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    (run_root / "run_summary.json").write_text("{}", encoding="utf-8")
    (run_root / "run_evidence_index.md").write_text("# evidence\n", encoding="utf-8")
    (diagnostics_dir / "artifact_inventory.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / "run_observability_summary.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / f"backlog_debt_summary_{run_id}.md").write_text("# Backlog\n", encoding="utf-8")

    monkeypatch.setattr(
        output_inventory,
        "get_cohort_readiness_snapshot",
        lambda: {
            "status": "ok",
            "warnings": [],
            "taxonomy_signals": {
                "missing_primary_label_samples": 7,
                "unresolved_family_samples": 1,
                "policy_held_family_samples": 5,
                "family_type_conflict_count": 3,
                "high_priority_conflict_count": 2,
                "family_type_conflict_action_counts": {
                    "review_db_type_mapping": 2,
                    "add_db_family_mapping": 1,
                },
                "family_type_conflict_issue_counts": {
                    "type_mismatch": 2,
                    "db_family_missing": 1,
                },
            },
        },
    )
    monkeypatch.setattr(
        output_inventory,
        "read_android_missing_resolution_snapshot",
        lambda **_kwargs: {
            "path": run_root.parent.parent / "diagnostics" / "android_missing_resolution_triage_latest.csv",
            "row_count": 2,
            "freshness": "aging",
            "top_lane": "vt_tail_review",
            "top_lane_count": 1,
            "lane_counts": {"vt_tail_review": 1},
        },
    )
    monkeypatch.setattr(
        output_inventory,
        "read_false_positive_triage_snapshot",
        lambda **_kwargs: {
            "path": run_root.parent.parent / "diagnostics" / "vt_false_positive_review_triage_latest.csv",
            "row_count": 6,
            "freshness": "current",
            "top_lane": "generic_placeholder_review",
            "top_lane_count": 4,
            "lane_counts": {"generic_placeholder_review": 4},
        },
    )
    monkeypatch.setattr(
        output_inventory,
        "read_policy_held_token_risk_snapshot",
        lambda **_kwargs: {
            "path": run_root.parent.parent / "diagnostics" / "android_policy_held_token_risk_latest.csv",
            "row_count": 5,
            "freshness": "current",
            "top_lane": "generic_family_token_review",
            "top_lane_count": 3,
            "lane_counts": {"generic_family_token_review": 3},
            "token_kind_counts": {"generic_family_token": 3},
        },
    )

    out_path = output_inventory.write_run_science_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="dev_smoke",
        evidence_mode=False,
        cohort_locked=False,
        publication_ready_status="NOT_APPLICABLE",
    )

    text = out_path.read_text(encoding="utf-8")
    assert "## Backlog and operator queues" in text
    assert f"backlog_debt_summary_{run_id}.md" in text
    assert "android_policy_held_token_risk_latest.csv" in text
    assert "Priority queue:** VT false-positive triage [freshness=current]" in text
    assert "Family taxonomy posture:** Taxonomy curation discipline: high-priority conflicts=2/3; dominant action=review_db_type_mapping (2); dominant issue=type_mismatch (2)." in text


@pytest.mark.integration
def test_write_run_science_index_surfaces_policy_held_focus_detail(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_id = "r_science_policy_held"
    run_root = tmp_path / "output" / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text("{}", encoding="utf-8")
    (run_root / "run_summary.json").write_text("{}", encoding="utf-8")
    (run_root / "run_evidence_index.md").write_text("# evidence\n", encoding="utf-8")
    (diagnostics_dir / "artifact_inventory.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / "run_observability_summary.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / f"backlog_debt_summary_{run_id}.md").write_text("# Backlog\n", encoding="utf-8")

    monkeypatch.setattr(
        output_inventory,
        "get_cohort_readiness_snapshot",
        lambda: {
            "status": "ok",
            "warnings": [],
            "taxonomy_signals": {
                "policy_held_family_samples": 129,
                "policy_held_family_token_kind_counts": {
                    "behavior_class_token": 45,
                    "generic_family_token": 39,
                    "campaign_actor_token": 19,
                    "placeholder_token": 16,
                },
            },
        },
    )
    monkeypatch.setattr(output_inventory, "read_android_missing_resolution_snapshot", lambda **_kwargs: {})
    monkeypatch.setattr(output_inventory, "read_false_positive_triage_snapshot", lambda **_kwargs: {})
    monkeypatch.setattr(
        output_inventory,
        "read_policy_held_token_risk_snapshot",
        lambda **_kwargs: {
            "path": run_root.parent.parent / "diagnostics" / "android_policy_held_token_risk_latest.csv",
            "row_count": 129,
            "freshness": "current",
            "top_lane": "class_label_not_family",
            "top_lane_count": 45,
            "top_token_kind": "behavior_class_token",
            "top_token_kind_count": 45,
            "top_policy_held_token": "banker",
            "top_policy_held_token_count": 31,
            "top_android_package_name": "com.example.banker",
            "top_android_package_name_count": 12,
            "high_or_strong_row_count": 27,
            "top_high_or_strong_policy_held_token": "banker",
            "top_high_or_strong_policy_held_token_count": 10,
            "top_high_or_strong_android_package_name": "com.example.banker",
            "top_high_or_strong_android_package_name_count": 6,
            "lane_counts": {"class_label_not_family": 45},
            "token_kind_counts": {"behavior_class_token": 45},
        },
    )

    out_path = output_inventory.write_run_science_index_md(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="dev_smoke",
        evidence_mode=False,
        cohort_locked=False,
        publication_ready_status="NOT_APPLICABLE",
    )

    text = out_path.read_text(encoding="utf-8")
    assert "Focus area:** Policy-held family noise (129 row(s))" in text
    assert "No true unresolved family debt in this slice; remaining resolved-family rows are intentionally held by generic/coarse token policy; token_classes=behavior_class_token=45, generic_family_token=39, campaign_actor_token=19, placeholder_token=16." in text
    assert "top_lane=class_label_not_family (45); top_token_kind=behavior_class_token (45); top_token=banker (31); top_package=com.example.banker (12); high_or_strong=27; top_high_token=banker (10); top_high_package=com.example.banker (6); freshness=current." in text
    assert "Open the policy-held token risk export and review the dominant high/strong hold lane plus token/package cluster" in text


def test_publication_ready_summary_status_not_applicable_when_paper_mode_off() -> None:
    status, reasons = output_inventory.evaluate_publication_ready_summary_status(
        paper_mode=False,
        manifest={},
        compliance_report=None,
    )
    assert status == "NOT_APPLICABLE"
    assert reasons == []


def test_publication_ready_summary_status_pass_when_compliance_passes() -> None:
    status, reasons = output_inventory.evaluate_publication_ready_summary_status(
        paper_mode=True,
        manifest={},
        compliance_report={"overall_status": "pass"},
    )
    assert status == "PASS"
    assert reasons == []


def test_publication_ready_summary_status_fail_when_compliance_fails() -> None:
    status, reasons = output_inventory.evaluate_publication_ready_summary_status(
        paper_mode=True,
        manifest={},
        compliance_report={"overall_status": "fail"},
    )
    assert status == "FAIL"
    assert "paper_compliance_not_pass" in reasons


def test_output_hygiene_terminal_summary_omits_open_first(capsys, tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "r_out"
    run_root.mkdir(parents=True, exist_ok=True)

    output_inventory.print_output_hygiene_terminal_summary(
        run_root=run_root,
        summary={
            "total_artifacts": 10,
            "bucket_counts": {
                "evidence_required": 1,
                "diagnostics_required": 2,
                "diagnostics_optional": 3,
                "debug_only": 0,
            },
            "duplicate_latest_inside_run_policy_drift": 0,
            "duplicate_latest_inside_run_legacy_compatibility": 2,
        },
        evidence_index_path=run_root / "run_evidence_index.md",
        publication_ready_status="PASS",
    )

    out = capsys.readouterr().out
    assert "Output Summary" in out
    assert "Open first" not in out
    assert "Legacy .latest compatibility copies" in out


def _write_run_manifest(run_dir: Path, payload: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_manifest.json").write_text(json.dumps(payload), encoding="utf-8")


def test_parse_run_record_reads_manifest_metadata(tmp_path: Path) -> None:
    run_dir = tmp_path / "output" / "runs" / "20260519T182900Z__b22294"
    _write_run_manifest(
        run_dir,
        {
            "run_id": "20260519T182900Z__b22294",
            "profile_id": "malicious_temporal_stability_locked",
            "run_status": "complete",
            "publication_ready_status": "PASS",
            "evidence_mode": True,
            "timestamp_utc": "2026-05-19T18:29:00.573052+00:00",
            "profile_params": {
                "description": "Cohort-locked multi-type malicious corpus contract anchored to a preserved baseline run.",
            },
        },
    )
    record = ora.parse_run_record(run_dir)
    assert record.run_id == "20260519T182900Z__b22294"
    assert record.profile_id == "malicious_temporal_stability_locked"
    assert record.status_bucket == "complete/pass"
    assert record.mode == "evidence/publication"
    assert record.timestamp_utc is not None


def test_classify_runs_protects_latest_and_promoted_and_evidence_pass(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    runs_dir = output_dir / "runs"
    diagnostics_dir = output_dir / "diagnostics"
    promoted_dir = output_dir / "promoted"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    promoted_dir.mkdir(parents=True, exist_ok=True)

    run_latest = runs_dir / "20260519T071502Z__c09270"
    _write_run_manifest(
        run_latest,
        {
            "run_id": "20260519T071502Z__c09270",
            "profile_id": "malicious_temporal_stability_locked",
            "run_status": "complete",
            "publication_ready_status": "PASS",
            "evidence_mode": True,
            "timestamp_utc": "2026-05-19T07:15:02.442806+00:00",
        },
    )
    run_older = runs_dir / "20260519T070012Z__0e798e"
    _write_run_manifest(
        run_older,
        {
            "run_id": "20260519T070012Z__0e798e",
            "profile_id": "malicious_temporal_stability_locked",
            "run_status": "complete",
            "publication_ready_status": "PASS",
            "evidence_mode": True,
            "timestamp_utc": "2026-05-19T07:00:12.429390+00:00",
        },
    )
    (diagnostics_dir / "latest_run_pointer.json").write_text(
        json.dumps({"run_id": "20260519T071502Z__c09270"}),
        encoding="utf-8",
    )
    (promoted_dir / "latest_run_manifest.json").write_text(
        json.dumps({"run_id": "20260519T071502Z__c09270"}),
        encoding="utf-8",
    )

    audit = ora.audit_output_retention(
        output_dir,
        policy=ora.RetentionPolicy(recent_days=0, keep_last_full_per_profile=0, keep_last_dev_runs_total=0),
        now_utc=ora._parse_iso_utc("2026-05-30T00:00:00+00:00"),
    )
    classes = {record.run_id: record.retention_class for record in audit.run_records}
    assert classes["20260519T071502Z__c09270"] == "protected"
    assert classes["20260519T070012Z__0e798e"] == "protected"


def test_classify_runs_marks_old_dev_smoke_complete_as_disposable(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    run_dir = output_dir / "runs" / "20260515T203118Z__cbe82d"
    _write_run_manifest(
        run_dir,
        {
            "run_id": "20260515T203118Z__cbe82d",
            "run_status": "complete",
            "evidence_mode": False,
            "timestamp_utc": "2026-05-15T20:31:18.752751+00:00",
            "profile_params": {
                "description": "Ultra-fast smoke profile for rapid CLI and pipeline sanity checks.",
            },
        },
    )
    audit = ora.audit_output_retention(
        output_dir,
        policy=ora.RetentionPolicy(recent_days=1, keep_last_full_per_profile=0, keep_last_dev_runs_total=0),
        now_utc=ora._parse_iso_utc("2026-05-19T00:00:00+00:00"),
    )
    assert audit.run_records[0].retention_class == "disposable"
    assert "older dev/smoke run outside default keep window" in audit.run_records[0].reasons


def test_missing_metadata_is_unknown_not_disposable(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    run_dir = output_dir / "runs" / "r1"
    run_dir.mkdir(parents=True, exist_ok=True)
    audit = ora.audit_output_retention(
        output_dir,
        now_utc=ora._parse_iso_utc("2026-05-19T00:00:00+00:00"),
    )
    assert audit.run_records[0].retention_class == "unknown"
    assert "missing metadata" in audit.run_records[0].reasons


def test_main_dry_run_does_not_delete_files(tmp_path: Path, capsys) -> None:
    output_dir = tmp_path / "output"
    diagnostics_dir = output_dir / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    run_dir = output_dir / "runs" / "20260515T203118Z__cbe82d"
    _write_run_manifest(
        run_dir,
        {
            "run_id": "20260515T203118Z__cbe82d",
            "run_status": "complete",
            "evidence_mode": False,
            "timestamp_utc": "2026-05-15T20:31:18.752751+00:00",
            "profile_params": {
                "description": "Ultra-fast smoke profile for rapid CLI and pipeline sanity checks.",
            },
        },
    )
    payload_path = run_dir / "payload.txt"
    payload_path.write_text("x", encoding="utf-8")

    rc = ora.main(
        [
            "--output-dir",
            str(output_dir),
            "--recent-days",
            "1",
            "--keep-last-full-per-profile",
            "0",
            "--keep-last-dev-runs-total",
            "0",
        ]
    )

    out = capsys.readouterr().out
    assert rc == 0
    assert "Output Retention Audit (dry-run)" in out
    assert "Disposable candidates" in out
    assert payload_path.exists()
