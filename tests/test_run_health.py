"""Tests for existence-aware run-health open-first hints."""

from __future__ import annotations

import json
from pathlib import Path

from obsidiandroid.observability.pipeline_observability import finalize as obs_finalize
from obsidiandroid.observability.pipeline_observability import run_health


def test_top_artifacts_to_open_only_lists_existing_files(tmp_path: Path) -> None:
    """Skipped audit bundles should not advertise files that do not exist."""
    run_root = tmp_path / "output" / "runs" / "r1"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    existing = [
        run_root / "run_evidence_index.md",
        diagnostics_dir / "run_observability_summary.json",
        diagnostics_dir / "pipeline_stage_summary.md",
    ]
    for path in existing:
        path.write_text("x\n", encoding="utf-8")

    hints = obs_finalize._top_artifacts_to_open(  # pylint: disable=protected-access
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id="r1",
        verbose_run_artifacts=True,
        research_validity_enabled=True,
        paper_mode=False,
    )

    assert hints == [str(path) for path in existing]


def test_top_artifacts_to_open_includes_authority_coverage_when_present(tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "r_auth"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    existing = [
        run_root / "run_evidence_index.md",
        diagnostics_dir / "run_observability_summary.json",
        diagnostics_dir / "family_type_authority_coverage_r_auth.md",
    ]
    for path in existing:
        path.write_text("x\n", encoding="utf-8")

    hints = obs_finalize._top_artifacts_to_open(  # pylint: disable=protected-access
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id="r_auth",
        verbose_run_artifacts=True,
        research_validity_enabled=True,
        paper_mode=False,
    )

    assert hints == [str(path) for path in existing]


def test_top_artifacts_to_open_includes_taxonomy_authority_split_when_present(tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "r_tax"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    existing = [
        diagnostics_dir / "taxonomy_authority_split_r_tax.md",
        run_root / "run_evidence_index.md",
        diagnostics_dir / "run_observability_summary.json",
    ]
    for path in existing:
        path.write_text("x\n", encoding="utf-8")

    hints = obs_finalize._top_artifacts_to_open(  # pylint: disable=protected-access
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id="r_tax",
        verbose_run_artifacts=True,
        research_validity_enabled=True,
        paper_mode=False,
    )

    assert hints == [str(path) for path in existing]


def test_print_unified_run_health_includes_skip_reasons(tmp_path: Path, capsys) -> None:
    """Run health should explain when audit bundles were intentionally skipped."""
    run_root = tmp_path / "output" / "runs" / "r_skip"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    obs_path = diagnostics_dir / "run_observability_summary.json"
    obs_path.write_text(
        json.dumps(
            {
                "run_id": "r_skip",
                "profile_id": "p_skip",
                "pipeline_status": "PASS_WITH_WARNINGS",
                "research_validity_status": "SKIPPED",
                "research_validity_skip_reason": "stop_after_samples",
                "hostile_audit_status": "SKIPPED",
                "hostile_audit_skip_reason": "stop_after_samples",
                "paper_mode": False,
                "evidence_mode": False,
                "verbose_run_artifacts": False,
                "research_validity_bundle_enabled": False,
                "publication_ready_status": "NOT_APPLICABLE",
                "publication_ready_reasons": [],
                "top_artifacts_to_open_first": [],
                "paths": {},
            }
        ),
        encoding="utf-8",
    )

    run_health.print_unified_run_health(
        inventory_summary={},
        observability_json_path=obs_path,
        evidence_index_path=None,
        run_root=run_root,
    )

    out = capsys.readouterr().out
    assert "Research validity bundle" in out
    assert "SKIPPED (stop_after_samples)" in out
    assert "Skeptic audit" in out


def test_print_unified_run_health_avoids_repeating_artifact_counts_and_truncates_warning_list(
    tmp_path: Path,
    capsys,
) -> None:
    run_root = tmp_path / "output" / "runs" / "r_warn"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    obs_path = diagnostics_dir / "run_observability_summary.json"
    obs_path.write_text(
        json.dumps(
            {
                "run_id": "r_warn",
                "profile_id": "p_warn",
                "pipeline_status": "PASS_WITH_WARNINGS",
                "research_validity_status": "PASS",
                "paper_mode": False,
                "evidence_mode": False,
                "verbose_run_artifacts": False,
                "research_validity_bundle_enabled": False,
                "publication_ready_status": "NOT_APPLICABLE",
                "publication_ready_reasons": [],
                "research_warnings_top": [
                    "warn 1",
                    "warn 2",
                    "warn 3",
                    "warn 4",
                ],
                "top_artifacts_to_open_first": [],
                "paths": {},
            }
        ),
        encoding="utf-8",
    )

    run_health.print_unified_run_health(
        inventory_summary={"bucket_counts": {"evidence_required": 1, "diagnostics_required": 2}},
        observability_json_path=obs_path,
        evidence_index_path=None,
        run_root=run_root,
    )

    out = capsys.readouterr().out
    assert "Artifact inventory (evidence/diag/debug)" not in out
    assert "warn 1" in out and "warn 2" in out and "warn 3" in out
    assert "warn 4" not in out
    assert "+1 more in diagnostics" in out


def test_print_unified_run_health_shows_label_strategy_targets(tmp_path: Path, capsys) -> None:
    run_root = tmp_path / "output" / "runs" / "r_labels"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    obs_path = diagnostics_dir / "run_observability_summary.json"
    obs_path.write_text(
        json.dumps(
            {
                "run_id": "r_labels",
                "profile_id": "dev_fast",
                "pipeline_status": "PASS",
                "research_validity_status": "PASS",
                "paper_mode": False,
                "evidence_mode": False,
                "verbose_run_artifacts": False,
                "research_validity_bundle_enabled": False,
                "publication_ready_status": "NOT_APPLICABLE",
                "publication_ready_reasons": [],
                "main_training_row_authority": "governed_cohort",
                "label_strategy": {
                    "preferred_family_target": "family_id",
                    "preferred_type_target": "type_slug",
                    "avoid_for_primary_claims": ["category_primary"],
                },
                "top_artifacts_to_open_first": [],
                "paths": {},
            }
        ),
        encoding="utf-8",
    )

    run_health.print_unified_run_health(
        inventory_summary={},
        observability_json_path=obs_path,
        evidence_index_path=None,
        run_root=run_root,
    )

    out = capsys.readouterr().out
    assert "Family target" in out
    assert "family_id" in out
    assert "Type target" in out
    assert "type_slug" in out


def test_print_unified_run_health_compact_shortens_labels(tmp_path: Path, capsys) -> None:
    run_root = tmp_path / "output" / "runs" / "r_compact"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    obs_path = diagnostics_dir / "run_observability_summary.json"
    obs_path.write_text(
        json.dumps(
            {
                "run_id": "r_compact",
                "profile_id": "p_compact",
                "pipeline_status": "PASS_WITH_WARNINGS",
                "research_validity_status": "PASS",
                "paper_mode": False,
                "evidence_mode": False,
                "verbose_run_artifacts": False,
                "research_validity_bundle_enabled": False,
                "publication_ready_status": "NOT_APPLICABLE",
                "publication_ready_reasons": [],
                "counts": {
                    "cohort_sql_scope_row_count": 100,
                    "cohort_prepared_row_count": 80,
                    "feature_matrix_rows": 80,
                    "aligned_supervised_rows": 75,
                    "post_low_support_training_rows": 70,
                    "train_rows": 35,
                    "test_rows": 35,
                },
                "features": {
                    "pre_prune": 120,
                    "post_prune": 90,
                },
                "research_warnings_top": ["warn 1", "warn 2"],
                "top_artifacts_to_open_first": ["foo.md", "bar.json"],
                "paths": {},
            }
        ),
        encoding="utf-8",
    )

    from config import app_config
    setattr(app_config, "ML_CONSOLE_MODE", "research")
    setattr(app_config, "ML_TERMINAL_COMPACT", True)
    run_health.print_unified_run_health(
        inventory_summary={},
        observability_json_path=obs_path,
        evidence_index_path=None,
        run_root=run_root,
    )

    out = capsys.readouterr().out
    assert "Feature columns" in out
    assert "120 → 90" in out
    assert "NEXT ARTIFACTS" in out


def test_print_unified_run_health_surfaces_scientific_adequacy(tmp_path: Path, capsys) -> None:
    run_root = tmp_path / "output" / "runs" / "r_science"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    obs_path = diagnostics_dir / "run_observability_summary.json"
    obs_path.write_text(
        json.dumps(
            {
                "run_id": "r_science",
                "profile_id": "malicious_temporal_stability_locked",
                "pipeline_status": "PASS",
                "research_validity_status": "PASS",
                "paper_mode": True,
                "evidence_mode": True,
                "publication_ready_status": "PASS",
                "publication_ready_reasons": [],
                "scientific_adequacy": {
                    "posture": "Weak",
                    "blockers": [
                        "headline family Macro-F1 is weak (0.3261)",
                        "dataset foundation does not mark supervised family claims as suitable",
                        "temporal holdout dropped 219 future-only family row(s)",
                    ],
                },
                "top_artifacts_to_open_first": [],
                "paths": {},
            }
        ),
        encoding="utf-8",
    )

    run_health.print_unified_run_health(
        inventory_summary={},
        observability_json_path=obs_path,
        evidence_index_path=None,
        run_root=run_root,
    )

    out = capsys.readouterr().out
    assert "Publication status" in out
    assert "PASS" in out
    assert "Scientific adequacy" in out
    assert "Weak" in out


def test_print_unified_run_health_shows_disabled_label_resolution(tmp_path: Path, capsys) -> None:
    run_root = tmp_path / "output" / "runs" / "r_label_off"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    obs_path = diagnostics_dir / "run_observability_summary.json"
    obs_path.write_text(
        json.dumps(
            {
                "run_id": "r_label_off",
                "profile_id": "dev_smoke",
                "pipeline_status": "PASS",
                "research_validity_status": "SKIPPED",
                "paper_mode": False,
                "evidence_mode": False,
                "publication_ready_status": "NOT_APPLICABLE",
                "publication_ready_reasons": [],
                "label_resolution_enabled": False,
                "top_artifacts_to_open_first": [],
                "paths": {},
            }
        ),
        encoding="utf-8",
    )

    run_health.print_unified_run_health(
        inventory_summary={},
        observability_json_path=obs_path,
        evidence_index_path=None,
        run_root=run_root,
    )

    out = capsys.readouterr().out
    assert "Label resolution" in out
    assert "DISABLED" in out
    assert "Type-guard suppressions" in out
    assert "unavailable (label resolution disabled)" in out


def test_print_unified_run_health_shows_type_guard_suppression_count(tmp_path: Path, capsys) -> None:
    run_root = tmp_path / "output" / "runs" / "r_label_on"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    obs_path = diagnostics_dir / "run_observability_summary.json"
    obs_path.write_text(
        json.dumps(
            {
                "run_id": "r_label_on",
                "profile_id": "dev_smoke",
                "pipeline_status": "PASS",
                "research_validity_status": "SKIPPED",
                "paper_mode": False,
                "evidence_mode": False,
                "publication_ready_status": "NOT_APPLICABLE",
                "publication_ready_reasons": [],
                "label_resolution_enabled": True,
                "type_guard_family_suppressed_count": 5,
                "top_artifacts_to_open_first": [],
                "paths": {},
            }
        ),
        encoding="utf-8",
    )

    run_health.print_unified_run_health(
        inventory_summary={},
        observability_json_path=obs_path,
        evidence_index_path=None,
        run_root=run_root,
    )

    out = capsys.readouterr().out
    assert "Label resolution" in out
    assert "ENABLED" in out
    assert "Type-guard suppressions" in out
    assert "5" in out


def test_print_unified_run_health_shows_stage_loss_summaries(tmp_path: Path, capsys) -> None:
    run_root = tmp_path / "output" / "runs" / "r_stage_losses"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    obs_path = diagnostics_dir / "run_observability_summary.json"
    obs_path.write_text(
        json.dumps(
            {
                "run_id": "r_stage_losses",
                "profile_id": "malicious_temporal_stability_locked",
                "pipeline_status": "PASS",
                "research_validity_status": "PASS",
                "paper_mode": True,
                "evidence_mode": True,
                "publication_ready_status": "PASS",
                "publication_ready_reasons": [],
                "alignment_non_authoritative_family_drop_count": 4,
                "alignment_live_authority_rescue_count": 179,
                "alignment_live_authority_rescue_families_top": "Applite=159, Wroba=15, Piom=5",
                "alignment_non_authoritative_family_drops_top": "unknown_family=4",
                "low_support_family_drop_count": 3,
                "low_support_row_drop_count": 4,
                "low_support_family_drops_top": "BrowBot=1, GINP=1, BRATA=2",
                "temporal_future_only_family_drops_top": "Zanubis=4, Alien=3",
                "top_artifacts_to_open_first": [],
                "paths": {},
            }
        ),
        encoding="utf-8",
    )

    run_health.print_unified_run_health(
        inventory_summary={},
        observability_json_path=obs_path,
        evidence_index_path=None,
        run_root=run_root,
    )

    out = capsys.readouterr().out
    assert "Support exclusions" in out
    assert "4 rows / 3 families" in out
    assert "Excluded families" in out
    assert "GINP=1" in out
    assert "BRATA=2" in out


def test_print_unified_run_health_separates_benchmark_support_exclusions(tmp_path: Path, capsys) -> None:
    run_root = tmp_path / "output" / "runs" / "r_benchmark_support"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    obs_path = diagnostics_dir / "run_observability_summary.json"
    obs_path.write_text(
        json.dumps(
            {
                "run_id": "r_benchmark_support",
                "profile_id": "android_malware_major_families",
                "pipeline_status": "PASS_WITH_WARNINGS",
                "research_validity_status": "SKIPPED",
                "paper_mode": False,
                "evidence_mode": False,
                "publication_ready_status": "NOT_APPLICABLE",
                "publication_ready_reasons": [],
                "benchmark_support_floor": 3,
                "benchmark_support_excluded_sample_count": 2,
                "benchmark_support_excluded_family_count": 2,
                "benchmark_support_excluded_families_top": "ginp=1, marcher=1",
                "top_artifacts_to_open_first": [],
                "paths": {},
            }
        ),
        encoding="utf-8",
    )

    run_health.print_unified_run_health(
        inventory_summary={},
        observability_json_path=obs_path,
        evidence_index_path=None,
        run_root=run_root,
    )

    out = capsys.readouterr().out
    assert "Support gate" in out
    assert "n>=3" in out
    assert "Support exclusions" in out
    assert "2 rows / 2 families" in out
    assert "Excluded families" in out
    assert "GINP=1, Marcher=1" in out


def test_print_unified_run_health_sample_only_run_does_not_invent_macro_f1_blockers(
    tmp_path: Path,
    capsys,
) -> None:
    run_root = tmp_path / "output" / "runs" / "r_samples_only"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    obs_path = diagnostics_dir / "run_observability_summary.json"
    obs_path.write_text(
        json.dumps(
            {
                "run_id": "r_samples_only",
                "profile_id": "android_malware_major_families",
                "run_status": "partial",
                "completed_stage": "samples",
                "pipeline_status": "PASS_WITH_WARNINGS",
                "research_validity_status": "SKIPPED",
                "paper_mode": False,
                "evidence_mode": False,
                "publication_ready_status": "NOT_APPLICABLE",
                "publication_ready_reasons": [],
                "scientific_adequacy": {
                    "posture": "Not assessed",
                    "blockers": [],
                },
                "top_artifacts_to_open_first": [],
                "paths": {},
            }
        ),
        encoding="utf-8",
    )

    run_health.print_unified_run_health(
        inventory_summary={},
        observability_json_path=obs_path,
        evidence_index_path=None,
        run_root=run_root,
    )

    out = capsys.readouterr().out
    assert "Scientific adequacy" in out
    assert "Not assessed" in out


def test_print_unified_run_health_structures_warning_lines(tmp_path: Path, capsys) -> None:
    run_root = tmp_path / "output" / "runs" / "r_warn_structured"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    obs_path = diagnostics_dir / "run_observability_summary.json"
    obs_path.write_text(
        json.dumps(
            {
                "run_id": "r_warn_structured",
                "run_slot": "majorfam_benchmark",
                "run_instance_id": "20260602T010627Z__33e5dd",
                "run_mode": "benchmark",
                "run_started_at_utc": "2026-06-02T01:06:27+00:00",
                "profile_id": "android_malware_major_families",
                "pipeline_status": "PASS",
                "research_validity_status": "PASS",
                "paper_mode": False,
                "evidence_mode": False,
                "publication_ready_status": "NOT_APPLICABLE",
                "publication_ready_reasons": [],
                "research_warnings_top": [
                    "banker share 88.69% exceeds 60.00%",
                    "raw family label differs from canonical family: 22",
                ],
                "top_artifacts_to_open_first": [],
                "paths": {},
            }
        ),
        encoding="utf-8",
    )

    run_health.print_unified_run_health(
        inventory_summary={},
        observability_json_path=obs_path,
        evidence_index_path=None,
        run_root=run_root,
    )

    out = capsys.readouterr().out
    assert "[HIGH] Banker share: 88.69% exceeds 60.00%" in out
    assert "[MEDIUM] Family conflicts: raw-vs-canonical conflicts=22" in out
    assert "Run slot" in out
    assert "majorfam_benchmark" in out


def test_open_first_hints_respects_compact_tuning_flags(tmp_path: Path) -> None:
    run_root = tmp_path / "output" / "runs" / "r_compact"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    evidence = run_root / "run_evidence_index.md"
    evidence.write_text("# evidence\n", encoding="utf-8")
    for name in (
        "publication_claim_audit.md",
        "paper_claim_audit.md",
        "cohort_funnel.md",
        "recommended_findings.md",
        "figure_validity_audit.md",
        "pipeline_stage_summary.md",
        "logging_audit.md",
    ):
        (run_root / name).write_text("x\n", encoding="utf-8")

    hints = run_health._open_first_hints(  # pylint: disable=protected-access
        evidence,
        run_root / "logging_audit.md",
        verbose_run_artifacts=False,
        research_validity_enabled=False,
    )

    assert str(evidence) in hints
    assert str(run_root / "pipeline_stage_summary.md") in hints
    assert str(run_root / "publication_claim_audit.md") not in hints
    assert str(run_root / "paper_claim_audit.md") not in hints
    assert str(run_root / "logging_audit.md") not in hints
