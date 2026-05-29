"""Tests for the Review Latest Run operator flow."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time

import pytest

from obsidiandroid.cli import startup_menu_review


def _seed_review_run_artifacts(
    write_text_file,
    out_root: Path,
    run_id: str,
    rdiag: Path,
    *,
    include_manifest: bool = True,
    manifest_payload: dict[str, object] | None = None,
    extra_run_files: dict[str, str] | None = None,
) -> None:
    write_text_file(rdiag / "run_science_index.md", "# run science\n")
    write_text_file(rdiag / "cohort_foundation.json", "{}")
    write_text_file(rdiag / "diagnostic_provenance.json", '{"entries":[]}')
    for rel_path, content in (extra_run_files or {}).items():
        write_text_file(rdiag / rel_path, content)
    if include_manifest:
        payload = {"run_id": run_id, "profile_params": {"profile_id": "malicious_temporal_stability"}}
        payload.update(manifest_payload or {})
        write_text_file(
            out_root / "diagnostics" / "run_manifest.latest.json",
            json.dumps(payload),
        )


@pytest.fixture(autouse=True)
def _stub_cohort_readiness_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(
        startup_menu_review,
        "get_cohort_readiness_snapshot",
        lambda: {"status": "ok", "warnings": [], "buckets": {}},
    )
    monkeypatch.setattr(
        startup_menu_review,
        "infer_cohort_readiness_signal",
        lambda _profile_id: {
            "bucket": None,
            "summary": "No readiness bucket mapped for this profile; review cohort filters manually.",
            "detail": "This guidance is advisory only and does not enforce sample selection.",
        },
    )


def test_compact_review_summary_includes_identity_health_and_tuning(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(
        write_text_file,
        out_root,
        run_id,
        rdiag,
        manifest_payload={"publication_ready_status": "NOT_APPLICABLE"},
        extra_run_files={
            "cohort_funnel.md": "# funnel\n",
            "feature_set_ablation_summary.md": "# ablation\n",
            "figure_validity_audit.md": "# figure audit\n",
        },
    )
    write_text_file(
        rdiag / f"taxonomy_consistency_summary_{run_id}.json",
        json.dumps(
            {
                "taxonomy_mismatch_count": 278,
                "paper_facing_taxonomy_mismatch_count": 0,
                "type_mismatch_count": 100,
                "type_noncanonical_count": 150,
                "type_missing_label_count": 28,
                "family_label_mismatch_count": 0,
            }
        ),
    )
    write_text_file(
        rdiag / f"taxonomy_authority_split_{run_id}.json",
        json.dumps(
            {
                "authority_scopes": {
                    "global_authority_catalog": {"bucket_counts": {"resolved_but_no_authority_family": 12}},
                    "run_cohort_authority": {"available": True, "bucket_counts": {"resolved_but_no_authority_family": 4}},
                },
                "taxonomy_split": {
                    "type_authority_vs_rendering_mismatch": {
                        "counts": {
                            "type_mapping_mismatch": 100,
                            "type_label_missing": 28,
                            "type_label_noncanonical": 150,
                            "label_family_mismatch": 0,
                        }
                    },
                    "model_prediction_error": {"count": 3},
                },
            }
        ),
    )
    write_text_file(rdiag / f"taxonomy_authority_split_{run_id}.md", "# Taxonomy Authority Split\n")
    write_text_file(
        rdiag / "modality_contribution_summary.json",
        json.dumps({"permission_signal_pct": 97.31}),
    )
    monkeypatch.setattr(
        startup_menu_review,
        "get_cohort_readiness_snapshot",
        lambda: {
            "status": "ok",
            "warnings": [],
            "buckets": {
                "all_catalog": {"sample_count": 10, "family_count": 3},
                "android_platform": {"sample_count": 9, "family_count": 2},
            },
        },
    )
    monkeypatch.setattr(
        startup_menu_review,
        "infer_cohort_readiness_signal",
        lambda _profile_id: {
            "bucket": "android_with_permission_obs",
            "summary": "Best matching readiness bucket: android_with_permission_obs",
            "detail": "Android malicious permission-feature profile intent is best compared against the Android cohort with permission observations. Advisory only; this does not enforce sample selection.",
        },
    )

    summary = startup_menu_review.build_review_latest_run_summary(output_root=out_root, latest_run_id=run_id)

    assert summary["run_id"] == run_id
    assert summary["profile_id"] == "malicious_temporal_stability"
    assert summary["run_class"] == "Research"
    assert summary["cohort_lock_status"] == "unlocked"
    assert summary["publication_ready_status"] == "No — exploratory run"
    labels = {str(row["label"]): str(row["status"]) for row in summary["health_rows"]}
    assert labels["Cohort / labels"] == "GREEN"
    assert labels["Taxonomy consistency"] == "YELLOW"
    assert labels["Ablation / signal contribution"] == "GREEN"
    assert labels["Figure validity"] == "GREEN"
    assert any("278 total mismatches" in warning for warning in summary["warnings"])
    assert any("(0 claim-facing)" in warning for warning in summary["warnings"])
    assert any("Next:" in warning for warning in summary["warnings"])
    assert str(summary["open_first"][0]["label"]) == "Run science index"
    assert any("Review taxonomy authority split" in action for action in summary["tuning_actions"])
    assert "taxonomy_support_summary" in summary
    assert "permission_tuning_summary" in summary
    assert "cohort_readiness_summary" in summary
    assert "backlog_debt_summary" in summary


def test_compact_review_screen_avoids_debug_path_dump(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
    capsys,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(write_text_file, out_root, run_id, rdiag)
    monkeypatch.delenv("OBSIDIANDROID_DISPLAY_MODE", raising=False)
    monkeypatch.setattr(
        startup_menu_review,
        "get_cohort_readiness_snapshot",
        lambda: {
            "status": "degraded",
            "warnings": ["Permission Intel unavailable for readiness counts."],
            "buckets": {
                "all_catalog": {"sample_count": 10, "family_count": 3},
                "android_platform": {"sample_count": 9, "family_count": 2},
                "android_with_permission_obs": {"sample_count": None, "family_count": None},
            },
        },
    )
    monkeypatch.setattr(
        startup_menu_review,
        "infer_cohort_readiness_signal",
        lambda _profile_id: {
            "bucket": "android_banker_with_permission_obs",
            "summary": "Best matching readiness bucket: android_banker_with_permission_obs",
            "detail": "Banker-focused profile intent is best compared against the Android banker cohort with permission observations. Advisory only; this does not enforce sample selection.",
        },
    )

    startup_menu_review.print_compact_review_latest_run(output_root=out_root, latest_run_id=run_id)
    out = capsys.readouterr().out

    assert "REVIEW LATEST RUN" in out
    assert "Run science index" in out
    assert "Publication-ready" in out
    assert "unknown" not in out.lower()
    assert "Detailed paths" not in out
    assert "diagnostics_dir" not in out
    assert "Cohort Readiness" in out
    assert "android_with_permission_obs" in out
    assert "Best matching readiness bucket: android_banker_with_permission_obs" in out
    assert "does not enforce sample selection" in out
    assert "Observed readiness for `android_banker_with_permission_obs`: samples=unavailable" in out or "Observed readiness for `android_banker_with_permission_obs` is unavailable" in out or "Observed readiness for `android_banker_with_permission_obs`: samples=0" in out
    assert "Permission Intel unavailable for readiness counts." in out
    assert "Taxonomy & Support Tuning" in out
    assert "Model prediction errors vs type/rendering" in out
    assert "Permission Coverage Tuning" in out


def test_compact_review_screen_surfaces_android_missing_resolution_triage(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
    capsys,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(write_text_file, out_root, run_id, rdiag)
    write_text_file(
        out_root / "diagnostics" / "android_missing_resolution_triage_latest.csv",
        "\n".join(
            [
                "sample_id,sha256,review_lane,recommended_action,package_cluster_key",
                "1,abc,package_cluster_review,inspect_package_cluster,com.example.app",
                "2,def,vt_tail_review,review_vt_tail,<blank>",
                "3,ghi,blank_package_review,review_missing_package,<blank>",
            ]
        ),
    )
    write_text_file(
        out_root / "diagnostics" / "vt_false_positive_review_triage_latest.csv",
        "\n".join(
            [
                "sample_id,review_lane,recommended_triage_action,global_policy_bucket",
                "10,file_artifact_review,review_artifact_name,single_vendor_low_context_review",
                "11,other_review,manual_review,no_global_policy_match",
            ]
        ),
    )
    monkeypatch.setattr(
        startup_menu_review,
        "get_cohort_readiness_snapshot",
        lambda: {"status": "ok", "warnings": [], "buckets": {}},
    )

    startup_menu_review.print_compact_review_latest_run(output_root=out_root, latest_run_id=run_id)
    out = capsys.readouterr().out

    assert "Android Missing-Resolution Triage" in out
    assert "Triage rows" in out
    assert "package_cluster_review=1" in out
    assert "vt_tail_review=1" in out
    assert "Package clusters" in out
    assert "Export freshness: current" in out
    assert "Priority Backlog" in out
    assert "Focus first" in out
    assert "Android missing-resolution triage" in out
    assert "Dominant lane: blank_package_review (1)" in out


def test_compact_review_summary_builds_ranked_backlog_debt_ledger(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(write_text_file, out_root, run_id, rdiag)
    write_text_file(
        out_root / "diagnostics" / "vt_false_positive_review_triage_latest.csv",
        "sample_id,review_lane,global_policy_bucket\n1,real_malware_family_or_class_review,single_vendor_low_context_review\n",
    )
    write_text_file(
        out_root / "diagnostics" / "android_missing_resolution_triage_latest.csv",
        "sample_id,review_lane,package_cluster_key,recommended_action\n1,blank_package_review,<blank>,review\n2,blank_package_review,<blank>,review\n3,package_cluster_review,com.ubnt,review\n",
    )
    monkeypatch.setattr(
        startup_menu_review,
        "get_cohort_readiness_snapshot",
        lambda: {
            "status": "ok",
            "warnings": [],
            "buckets": {},
                "taxonomy_signals": {
                    "missing_primary_label_samples": 153,
                    "missing_primary_label_raw_samples": 153,
                    "missing_primary_label_actionable_samples": 4,
                    "missing_primary_label_residual_samples": 149,
                    "missing_primary_label_suppressed_samples": 0,
                    "missing_primary_label_active_residual_samples": 149,
                    "missing_primary_label_lane_counts": {
                        "public_package_identity_provenance_review": 70,
                        "unknown_family_low_consensus_review": 40,
                        "high_strong_primary_backfill_review": 4,
                    },
                    "unresolved_family_samples": 76,
                    "policy_held_family_samples": 44,
                    "family_type_conflict_count": 12,
                    "high_priority_conflict_count": 9,
                    "family_type_conflict_action_counts": {
                        "review_db_type_mapping": 7,
                        "add_db_family_mapping": 3,
                        "replace_unknown_db_type": 2,
                    },
                    "family_type_conflict_issue_counts": {
                        "type_mismatch": 7,
                        "db_family_missing": 3,
                        "type_unknown": 2,
                    },
                },
            },
        )
    monkeypatch.setattr(
        startup_menu_review,
        "read_false_positive_triage_snapshot",
        lambda **_kwargs: {
            "row_count": 1,
            "freshness": "current",
            "top_lane": "real_malware_family_or_class_review",
            "top_lane_count": 1,
            "lane_counts": {"real_malware_family_or_class_review": 1},
        },
    )
    monkeypatch.setattr(
        startup_menu_review,
        "read_android_missing_resolution_snapshot",
        lambda **_kwargs: {
            "row_count": 3,
            "freshness": "current",
            "top_lane": "blank_package_review",
            "top_lane_count": 2,
            "lane_counts": {"blank_package_review": 2, "package_cluster_review": 1},
            "cluster_counts": {"<blank>": 2, "com.ubnt": 1},
        },
    )

    summary = startup_menu_review.build_review_latest_run_summary(output_root=out_root, latest_run_id=run_id)

    debt = summary["backlog_debt_summary"]
    assert debt["focus_code"] == "missing_primary_labels"
    assert debt["focus_label"] == "Missing primary labels"
    assert debt["focus_count"] == 153
    assert debt["focus_detail"] == "Active/actionable Android + PI missing-primary debt; raw_missing=153; actionable=4; suppressed=0; active_residual=149."
    assert debt["missing_primary_label_lanes"][:2] == [
        {"lane": "public_package_identity_provenance_review", "sample_count": 70},
        {"lane": "unknown_family_low_consensus_review", "sample_count": 40},
    ]
    posture = debt["taxonomy_curation_posture"]
    assert posture["conflict_count"] == 12
    assert posture["high_priority_count"] == 9
    assert posture["dominant_action"] == "review_db_type_mapping"
    assert posture["dominant_issue"] == "type_mismatch"
    assert "high-priority conflicts=9/12" in str(posture["note"])
    rows = debt["rows"]
    assert rows[0]["code"] == "missing_primary_labels"
    assert rows[0]["label"] == "Missing primary labels"
    assert rows[1]["code"] == "true_unresolved_family"
    assert rows[1]["label"] == "True unresolved family debt"
    assert any(row["code"] == "android_missing_resolution" and row["count"] == 3 for row in rows)
    assert any(row["code"] == "vt_false_positive_review" and row["count"] == 1 for row in rows)


def test_compact_review_summary_marks_live_backlog_when_run_snapshot_differs(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(write_text_file, out_root, run_id, rdiag)
    write_text_file(
        rdiag / f"backlog_debt_summary_{run_id}.md",
        "\n".join(
            [
                f"# Backlog debt summary — `{run_id}`",
                "",
                "- **Focus area:** Missing primary labels (153 row(s))",
                "- **Ranked debt:**",
                "  - Missing primary labels: 153",
            ]
        )
        + "\n",
    )
    monkeypatch.setattr(
        startup_menu_review,
        "get_cohort_readiness_snapshot",
        lambda: {
            "status": "ok",
            "warnings": [],
            "buckets": {},
            "taxonomy_signals": {
                "missing_primary_label_samples": 93,
                "unresolved_family_samples": 12,
                "policy_held_family_samples": 4,
            },
        },
    )

    summary = startup_menu_review.build_review_latest_run_summary(output_root=out_root, latest_run_id=run_id)

    debt = summary["backlog_debt_summary"]
    assert debt["focus_count"] == 93
    assert debt["source_note"] == "live DB now (reviewing an older run may differ)"
    assert debt["snapshot_compare_note"] == (
        "missing primary labels were 153 at run time; live DB now shows 93"
    )
    assert any("run snapshot differs from current live db" in str(note).lower() for note in summary["warnings"])


def test_compact_review_screen_prints_backlog_debt_section(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
    capsys,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(write_text_file, out_root, run_id, rdiag)
    monkeypatch.setattr(
        startup_menu_review,
        "get_cohort_readiness_snapshot",
        lambda: {
            "status": "ok",
            "warnings": [],
            "buckets": {},
            "taxonomy_signals": {
                "missing_primary_label_samples": 12,
                "missing_primary_label_raw_samples": 12,
                "missing_primary_label_actionable_samples": 0,
                "missing_primary_label_residual_samples": 12,
                "missing_primary_label_suppressed_samples": 4,
                "missing_primary_label_active_residual_samples": 8,
                "missing_primary_label_lane_counts": {
                    "public_package_identity_provenance_review": 8,
                    "already_sample_suppressed": 4,
                },
                "unresolved_family_samples": 7,
                "policy_held_family_samples": 4,
                "family_type_conflict_count": 2,
            },
        },
    )

    startup_menu_review.print_compact_review_latest_run(output_root=out_root, latest_run_id=run_id)
    out = capsys.readouterr().out

    assert "Backlog Debt" in out
    assert "Focus area" in out
    assert "Missing primary labels" in out
    assert "Active/actionable Android + PI missing-primary debt; raw_missing=12; actionable=0; suppressed=4; active_residual=8." in out
    assert "Missing-primary lane split: public_package_identity_provenance_review=8, already_sample_suppressed=4" in out


def test_compact_review_screen_prints_policy_held_token_risk(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
    capsys,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(write_text_file, out_root, run_id, rdiag)
    monkeypatch.setattr(
        startup_menu_review,
        "get_cohort_readiness_snapshot",
        lambda: {"status": "ok", "warnings": [], "buckets": {}, "taxonomy_signals": {}},
    )
    monkeypatch.setattr(
        startup_menu_review,
        "read_policy_held_token_risk_snapshot",
        lambda **_kwargs: {
            "path": out_root / "diagnostics" / "android_policy_held_token_risk_latest.csv",
            "row_count": 142,
            "freshness": "current",
            "lane_counts": {
                "class_label_not_family": 47,
                "generic_family_token_review": 44,
                "campaign_or_actor_not_family": 21,
            },
            "token_kind_counts": {
                "behavior_class_token": 47,
                "generic_family_token": 44,
                "campaign_actor_token": 21,
            },
        },
    )

    startup_menu_review.print_compact_review_latest_run(output_root=out_root, latest_run_id=run_id)
    out = capsys.readouterr().out

    assert "Policy-Held Token Risk" in out
    assert "Triage rows" in out
    assert "class_label_not_family=47" in out
    assert "behavior_class_token=47" in out
    assert "hold-policy review, not safe family-authority promotion" in out


def test_compact_review_screen_surfaces_policy_held_focus_detail(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
    capsys,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(write_text_file, out_root, run_id, rdiag)
    monkeypatch.setattr(
        startup_menu_review,
        "get_cohort_readiness_snapshot",
        lambda: {
            "status": "ok",
            "warnings": [],
            "buckets": {},
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
    monkeypatch.setattr(startup_menu_review, "read_false_positive_triage_snapshot", lambda **_kwargs: {})
    monkeypatch.setattr(startup_menu_review, "read_android_missing_resolution_snapshot", lambda **_kwargs: {})
    monkeypatch.setattr(
        startup_menu_review,
        "read_policy_held_token_risk_snapshot",
        lambda **_kwargs: {
            "path": out_root / "diagnostics" / "android_policy_held_token_risk_latest.csv",
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

    startup_menu_review.print_compact_review_latest_run(output_root=out_root, latest_run_id=run_id)
    out = capsys.readouterr().out

    assert "Focus area: Policy-held family noise (129 row(s))" in out
    assert "top_lane=class_label_not_family (45); top_token_kind=behavior_class_token (45); top_token=banker (31); top_package=com.example.banker (12); high_or_strong=27; top_high_token=banker (10); top_high_package=com.example.banker (6); freshness=current." in out
    assert "Open the policy-held token risk export and review the dominant high/strong hold lane plus token/package cluster" in out


def test_compact_review_screen_prints_live_backlog_source_and_run_snapshot_delta(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
    capsys,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(write_text_file, out_root, run_id, rdiag)
    write_text_file(
        rdiag / f"backlog_debt_summary_{run_id}.md",
        "\n".join(
            [
                f"# Backlog debt summary — `{run_id}`",
                "",
                "- **Focus area:** Missing primary labels (153 row(s))",
            ]
        )
        + "\n",
    )
    monkeypatch.setattr(
        startup_menu_review,
        "get_cohort_readiness_snapshot",
        lambda: {
            "status": "ok",
            "warnings": [],
            "buckets": {},
            "taxonomy_signals": {
                "missing_primary_label_samples": 93,
                "unresolved_family_samples": 7,
                "policy_held_family_samples": 4,
            },
        },
    )

    startup_menu_review.print_compact_review_latest_run(output_root=out_root, latest_run_id=run_id)
    out = capsys.readouterr().out

    assert "Source: live DB now (reviewing an older run may differ)" in out
    assert "Run snapshot: missing primary labels were 153 at run time; live DB now shows 93" in out


def test_compact_review_screen_warns_when_taxonomy_support_uses_global_latest_mirror(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
    capsys,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(write_text_file, out_root, run_id, rdiag)
    write_text_file(
        out_root / "diagnostics" / "taxonomy_authority_split.latest.json",
        json.dumps(
            {
                "authority_scopes": {
                    "global_authority_catalog": {"bucket_counts": {"resolved_but_no_authority_family": 12}},
                    "run_cohort_authority": {"available": False, "bucket_counts": {}},
                },
                "taxonomy_split": {
                    "type_authority_vs_rendering_mismatch": {
                        "counts": {
                            "type_mapping_mismatch": 1,
                            "type_label_missing": 0,
                            "type_label_noncanonical": 0,
                            "label_family_mismatch": 0,
                        }
                    },
                    "model_prediction_error": {"count": 1},
                },
            }
        ),
    )
    write_text_file(out_root / "diagnostics" / "taxonomy_authority_split.latest.md", "# split\n")
    write_text_file(out_root / "diagnostics" / "taxonomy_consistency_summary.latest.json", json.dumps({"taxonomy_mismatch_count": 1}))
    write_text_file(out_root / "diagnostics" / "taxonomy_target_surfaces.latest.json", json.dumps({"label_strategy": {"preferred_family_target": "family_id"}}))
    write_text_file(rdiag / "family_label_taxonomy_audit.csv", "family_canonical,aligned_rows,support_status,configured_min_samples_per_family\nfamA,5,retained,3\n")
    monkeypatch.setattr(
        startup_menu_review,
        "get_cohort_readiness_snapshot",
        lambda: {"status": "ok", "warnings": [], "buckets": {}},
    )

    startup_menu_review.print_compact_review_latest_run(output_root=out_root, latest_run_id=run_id)
    out = capsys.readouterr().out

    assert "Artifact provenance" in out
    assert "global_latest_mirror" in out
    assert "cross-run guidance" in out.lower()


def test_review_summary_stale_priority_backlog_prefers_refresh_action(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(write_text_file, out_root, run_id, rdiag)
    stale_path = out_root / "diagnostics" / "android_missing_resolution_triage_latest.csv"
    write_text_file(
        stale_path,
        "\n".join(
            [
                "sample_id,sha256,review_lane,recommended_action,package_cluster_key",
                "1,abc,blank_package_review,review_missing_package,<blank>",
                "2,def,blank_package_review,review_missing_package,<blank>",
            ]
        ),
    )
    fresh_fp = out_root / "diagnostics" / "vt_false_positive_review_triage_latest.csv"
    write_text_file(
        fresh_fp,
        "\n".join(
            [
                "sample_id,review_lane,recommended_triage_action,global_policy_bucket",
                "10,file_artifact_review,review_artifact_name,single_vendor_low_context_review",
            ]
        ),
    )
    stale_epoch = time.time() - (96 * 3600)
    os.utime(stale_path, (stale_epoch, stale_epoch))
    monkeypatch.setattr(
        startup_menu_review,
        "get_cohort_readiness_snapshot",
        lambda: {"status": "ok", "warnings": [], "buckets": {}},
    )

    summary = startup_menu_review.build_review_latest_run_summary(output_root=out_root, latest_run_id=run_id)

    priority = summary.get("priority_backlog_summary", {})
    warnings = [str(note) for note in summary.get("warnings", [])]
    tuning_actions = [str(note) for note in summary.get("tuning_actions", [])]
    assert str(priority.get("label")) == "Android missing-resolution triage"
    assert str(priority.get("freshness")) == "stale"
    assert "Refresh android missing-resolution triage export first" in str(priority.get("action", ""))
    assert any("latest export is stale" in note for note in warnings)
    assert any("Refresh the Android missing-resolution triage export" in note for note in tuning_actions)


def test_review_summary_surfaces_live_readiness_gap_notes(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(write_text_file, out_root, run_id, rdiag)
    monkeypatch.setattr(
        startup_menu_review,
        "get_cohort_readiness_snapshot",
        lambda: {
            "status": "degraded",
            "permission_obs_available": False,
            "warnings": ["Permission Intel unavailable for readiness counts."],
            "buckets": {
                "android_high_or_strong_vt_with_permission_obs": {
                    "sample_count": None,
                    "family_count": None,
                }
            },
            "taxonomy_signals": {
                "repair_candidate_count": 5,
                "known_unresolved_family_count": 2,
                "policy_held_family_count": 7,
                "family_type_conflict_count": 4,
                "high_priority_conflict_count": 2,
                "family_type_conflict_action_counts": {
                    "review_db_type_mapping": 3,
                    "add_db_family_mapping": 1,
                },
                "family_type_conflict_issue_counts": {
                    "type_mismatch": 3,
                    "db_family_missing": 1,
                },
            },
        },
    )
    monkeypatch.setattr(
        startup_menu_review,
        "infer_cohort_readiness_signal",
        lambda _profile_id: {
            "bucket": "android_high_or_strong_vt_with_permission_obs",
            "summary": "Best matching readiness bucket: android_high_or_strong_vt_with_permission_obs",
            "detail": "Android malicious evidence-style profile intent is best compared against the Android cohort with permission observations and high/strong VT confidence. Advisory only; this does not enforce sample selection.",
        },
    )

    summary = startup_menu_review.build_review_latest_run_summary(output_root=out_root, latest_run_id=run_id)

    gap_notes = [str(note) for note in summary.get("cohort_readiness_gap_notes", [])]
    warnings = [str(note) for note in summary.get("warnings", [])]
    tuning_actions = [str(note) for note in summary.get("tuning_actions", [])]
    assert any("does not currently verify a matching PI-observed cohort" in note for note in gap_notes)
    assert any("repair candidates=5, known unresolved families=2, policy-held tokens=7" in note for note in gap_notes)
    assert any("high-priority conflicts=2/4; dominant action=review_db_type_mapping (3); dominant issue=type_mismatch (3)." in note for note in gap_notes)
    assert any("Compare against an unlocked/current cohort" in note for note in gap_notes)
    assert any("Live readiness / authority-taxonomy split" in note for note in warnings)
    assert any("Check live readiness mismatch, true authority debt, and policy-held token residue" in note for note in tuning_actions)


def test_review_summary_can_state_when_only_policy_held_token_noise_remains(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(write_text_file, out_root, run_id, rdiag)
    monkeypatch.setattr(
        startup_menu_review,
        "get_cohort_readiness_snapshot",
        lambda: {
            "status": "ok",
            "warnings": [],
            "permission_obs_available": True,
            "buckets": {
                "android_high_or_strong_vt_with_permission_obs": {"sample_count": 10, "family_count": 2},
            },
            "taxonomy_signals": {
                "repair_candidate_count": 0,
                "known_unresolved_family_count": 0,
                "unresolved_family_count": 0,
                "policy_held_family_count": 11,
            },
        },
    )
    monkeypatch.setattr(
        startup_menu_review,
        "infer_cohort_readiness_signal",
        lambda _profile_id: {
            "bucket": "android_high_or_strong_vt_with_permission_obs",
            "summary": "Best matching readiness bucket: android_high_or_strong_vt_with_permission_obs",
            "detail": "Advisory only; this does not enforce sample selection.",
        },
    )

    summary = startup_menu_review.build_review_latest_run_summary(output_root=out_root, latest_run_id=run_id)

    gap_notes = [str(note) for note in summary.get("cohort_readiness_gap_notes", [])]
    assert any("no true unresolved family slugs" in note.lower() for note in gap_notes)
    assert any("policy-held token noise" in note.lower() for note in gap_notes)


def test_detailed_review_screen_can_show_deeper_paths(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
    capsys,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(write_text_file, out_root, run_id, rdiag)
    monkeypatch.setenv("OBSIDIANDROID_DISPLAY_MODE", "detailed")
    monkeypatch.setattr(
        startup_menu_review,
        "get_cohort_readiness_snapshot",
        lambda: {"status": "ok", "warnings": [], "buckets": {}},
    )

    startup_menu_review.print_compact_review_latest_run(output_root=out_root, latest_run_id=run_id)
    out = capsys.readouterr().out

    assert "Detailed paths" in out
    assert "diagnostics dir" in out.lower()


def test_run_history_remains_reachable_from_review_menu(monkeypatch) -> None:
    choices = iter([9, 1, 0, 0])
    calls = {"history": 0, "compare": 0}
    monkeypatch.setattr(startup_menu_review, "print_compact_review_latest_run", lambda **_: None)
    monkeypatch.setattr(
        startup_menu_review,
        "build_review_latest_run_summary",
        lambda **_: {
            "run_id": "r1",
            "profile_id": "p1",
            "run_class": "Exploratory",
            "cohort_lock_status": "unlocked",
            "publication_ready_status": "Not applicable — exploratory run",
            "health_rows": [],
            "warnings": [],
            "open_first": [],
            "tuning_actions": [],
        },
    )
    monkeypatch.setattr(startup_menu_review.mu, "display_menu", lambda *_args, **_kwargs: next(choices))

    startup_menu_review.launch_review_latest_run_menu(
        read_latest_run_id=lambda: "r1",
        open_run_science_index_action=lambda: 0,
        launch_cohort_family_audit_action=lambda: None,
        launch_parser_vendor_coverage_action=lambda: None,
        launch_permission_intelligence_coverage_action=lambda: None,
        launch_feature_matrix_modality_action=lambda: None,
        launch_taxonomy_consistency_review_action=lambda: None,
        launch_run_overview_action=lambda: calls.__setitem__("history", calls["history"] + 1),
        launch_compare_runs_action=lambda: calls.__setitem__("compare", calls["compare"] + 1),
        launch_data_diagnostics_action=lambda: None,
        launch_reproducibility_action=lambda: None,
    )

    assert calls["history"] == 1
    assert calls["compare"] == 0


def test_vendor_parser_workbook_gap_is_warning_not_red(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(
        write_text_file,
        out_root,
        run_id,
        rdiag,
        manifest_payload={"publication_ready_status": "NOT_APPLICABLE"},
    )
    monkeypatch.setattr(
        startup_menu_review,
        "build_operator_state",
        lambda **_kwargs: {
            "latest_run_id": run_id,
            "display_mode": "compact",
            "manifest_payload": {"publication_ready_status": "NOT_APPLICABLE"},
            "profile_id": "malicious_temporal_stability",
            "evidence_mode": False,
            "best_run_index_path": rdiag / "run_science_index.md",
            "has_canonical_run_science": True,
            "parser_summary": {
                "csv_ready": True,
                "workbook_ready": False,
                "needs_attention": "Workbook drill-down unavailable",
                "unmapped_vendors": 70,
            },
        },
    )
    monkeypatch.setattr(
        startup_menu_review.diagnostics_banners,
        "build_diagnostics_overview",
        lambda **_kwargs: {
            "rows": [
                {"label": "Cohort / labels", "status": "GREEN"},
                {"label": "Taxonomy consistency", "status": "GREEN"},
                {"label": "Permission signal", "status": "GREEN"},
                {"label": "Vendor/parser coverage", "status": "YELLOW"},
                {"label": "Feature matrix", "status": "GREEN"},
                {"label": "Evidence/provenance", "status": "GREEN"},
            ]
        },
    )
    summary = startup_menu_review.build_review_latest_run_summary(output_root=out_root, latest_run_id=run_id)
    labels = {str(row["label"]): str(row["status"]) for row in summary["health_rows"]}
    assert labels["Vendor/parser"] == "YELLOW"


def test_tune_next_changes_with_status_flags(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(
        write_text_file,
        out_root,
        run_id,
        rdiag,
        manifest_payload={"publication_ready_status": "NOT_APPLICABLE"},
    )
    monkeypatch.setattr(
        startup_menu_review,
        "build_operator_state",
        lambda **_kwargs: {
            "latest_run_id": run_id,
            "display_mode": "compact",
            "manifest_payload": {"publication_ready_status": "NOT_APPLICABLE"},
            "profile_id": "malicious_temporal_stability",
            "evidence_mode": False,
            "best_run_index_path": rdiag / "run_science_index.md",
            "has_canonical_run_science": True,
            "parser_summary": {"csv_ready": True, "workbook_ready": True, "unmapped_vendors": 0},
        },
    )
    monkeypatch.setattr(
        startup_menu_review.diagnostics_banners,
        "build_diagnostics_overview",
        lambda **_kwargs: {
            "rows": [
                {"label": "Cohort / labels", "status": "GREEN"},
                {"label": "Taxonomy consistency", "status": "YELLOW"},
                {"label": "Permission signal", "status": "RED"},
                {"label": "Vendor/parser coverage", "status": "GREEN"},
                {"label": "Feature matrix", "status": "GREEN"},
                {"label": "Evidence/provenance", "status": "GREEN"},
            ]
        },
    )
    write_text_file(rdiag / f"taxonomy_consistency_summary_{run_id}.json", json.dumps({"taxonomy_mismatch_count": 5, "paper_facing_taxonomy_mismatch_count": 0, "type_mismatch_count": 5, "type_noncanonical_count": 0, "type_missing_label_count": 0, "family_label_mismatch_count": 0}))
    write_text_file(rdiag / "modality_contribution_summary.json", json.dumps({"permission_signal_pct": 45.0}))
    summary = startup_menu_review.build_review_latest_run_summary(output_root=out_root, latest_run_id=run_id)
    assert str(summary["tuning_actions"][0]).startswith("Prioritize screens in this order:")
    assert "Permission and feature health" in str(summary["tuning_actions"][0])
    assert "Taxonomy authority split" in str(summary["tuning_actions"][0])
    assert any("taxonomy authority split" in action.lower() for action in summary["tuning_actions"])
    assert any("permission signal" in action.lower() for action in summary["tuning_actions"])


def test_review_summary_warns_for_count_only_lock(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(write_text_file, out_root, run_id, rdiag, include_manifest=False)
    monkeypatch.setattr(
        startup_menu_review,
        "build_operator_state",
        lambda **_kwargs: {
            "latest_run_id": run_id,
            "display_mode": "compact",
            "manifest_payload": {
                "publication_ready_status": "NOT_READY",
                "evidence_mode": True,
                "paper_cohort_contract": {
                    "cohort_lock_status": "count_only_incomplete_sample_lock",
                    "paper_locked": True,
                },
            },
            "profile_id": "malicious_temporal_stability_locked",
            "evidence_mode": True,
            "best_run_index_path": rdiag / "run_science_index.md",
            "has_canonical_run_science": True,
            "parser_summary": {"csv_ready": True, "workbook_ready": True, "unmapped_vendors": 0},
        },
    )
    monkeypatch.setattr(
        startup_menu_review.diagnostics_banners,
        "build_diagnostics_overview",
        lambda **_kwargs: {
            "rows": [
                {"label": "Cohort / labels", "status": "GREEN"},
                {"label": "Taxonomy consistency", "status": "GREEN"},
                {"label": "Permission signal", "status": "GREEN"},
                {"label": "Vendor/parser coverage", "status": "GREEN"},
                {"label": "Feature matrix", "status": "GREEN"},
                {"label": "Evidence/provenance", "status": "GREEN"},
            ]
        },
    )

    summary = startup_menu_review.build_review_latest_run_summary(output_root=out_root, latest_run_id=run_id)

    assert summary["cohort_lock_status"] == "count-only"
    assert any("count-only lock" in str(w).lower() for w in summary["warnings"])
    assert any("count-only cohort lock" in str(action).lower() for action in summary["tuning_actions"])


def test_review_summary_warns_for_taxonomy_drift_lock(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(write_text_file, out_root, run_id, rdiag, include_manifest=False)
    monkeypatch.setattr(
        startup_menu_review,
        "build_operator_state",
        lambda **_kwargs: {
            "latest_run_id": run_id,
            "display_mode": "compact",
            "manifest_payload": {
                "publication_ready_status": "NOT_READY",
                "evidence_mode": True,
                "paper_cohort_contract": {
                    "cohort_lock_status": "membership_locked_taxonomy_drift",
                    "paper_locked": True,
                    "sample_id_lock": {
                        "taxonomy_label_drift": {
                            "drift_class": "taxonomy_expansion",
                            "family_delta": 5,
                            "type_delta": 1,
                            "recommended_action": "Review newly split families/types.",
                        }
                    },
                },
            },
            "profile_id": "malicious_temporal_stability_locked",
            "evidence_mode": True,
            "best_run_index_path": rdiag / "run_science_index.md",
            "has_canonical_run_science": True,
            "parser_summary": {"csv_ready": True, "workbook_ready": True, "unmapped_vendors": 0},
        },
    )
    monkeypatch.setattr(
        startup_menu_review.diagnostics_banners,
        "build_diagnostics_overview",
        lambda **_kwargs: {
            "rows": [
                {"label": "Cohort / labels", "status": "GREEN"},
                {"label": "Taxonomy consistency", "status": "GREEN"},
                {"label": "Permission signal", "status": "GREEN"},
                {"label": "Vendor/parser coverage", "status": "GREEN"},
                {"label": "Feature matrix", "status": "GREEN"},
                {"label": "Evidence/provenance", "status": "GREEN"},
            ]
        },
    )

    summary = startup_menu_review.build_review_latest_run_summary(output_root=out_root, latest_run_id=run_id)

    assert summary["cohort_lock_status"] == "taxonomy-drift"
    assert any("taxonomy-label drift" in str(w).lower() for w in summary["warnings"])
    assert any("family_delta=+5" in str(w) for w in summary["warnings"])
    assert any("taxonomy_expansion" in str(action) for action in summary["tuning_actions"])
    assert any("locked sample set" in str(action).lower() for action in summary["tuning_actions"])


def test_review_summary_warns_for_missing_lock(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(write_text_file, out_root, run_id, rdiag, include_manifest=False)
    monkeypatch.setattr(
        startup_menu_review,
        "build_operator_state",
        lambda **_kwargs: {
            "latest_run_id": run_id,
            "display_mode": "compact",
            "manifest_payload": {
                "publication_ready_status": "READY",
                "evidence_mode": True,
                "paper_cohort_contract": {
                    "cohort_lock_status": "missing_lock",
                    "paper_locked": True,
                },
            },
            "profile_id": "paper2_locked_banker",
            "evidence_mode": True,
            "best_run_index_path": rdiag / "run_science_index.md",
            "has_canonical_run_science": True,
            "parser_summary": {"csv_ready": True, "workbook_ready": True, "unmapped_vendors": 0},
        },
    )
    monkeypatch.setattr(
        startup_menu_review.diagnostics_banners,
        "build_diagnostics_overview",
        lambda **_kwargs: {
            "rows": [
                {"label": "Cohort / labels", "status": "GREEN"},
                {"label": "Taxonomy consistency", "status": "GREEN"},
                {"label": "Permission signal", "status": "GREEN"},
                {"label": "Vendor/parser coverage", "status": "GREEN"},
                {"label": "Feature matrix", "status": "GREEN"},
                {"label": "Evidence/provenance", "status": "GREEN"},
            ]
        },
    )

    summary = startup_menu_review.build_review_latest_run_summary(output_root=out_root, latest_run_id=run_id)

    assert summary["cohort_lock_status"] == "missing-lock"
    assert any("missing or mismatched lock" in str(w).lower() for w in summary["warnings"])
    assert any("publication-grade" in str(action).lower() for action in summary["tuning_actions"])


def test_review_summary_surfaces_locked_membership_and_malware_rescue(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    _seed_review_run_artifacts(write_text_file, out_root, run_id, rdiag, include_manifest=False)
    monkeypatch.setattr(
        startup_menu_review,
        "build_operator_state",
        lambda **_kwargs: {
            "latest_run_id": run_id,
            "display_mode": "compact",
            "manifest_payload": {"publication_ready_status": "NOT_APPLICABLE"},
            "profile_id": "paper2_demo",
            "evidence_mode": False,
            "best_run_index_path": rdiag / "run_science_index.md",
            "has_canonical_run_science": True,
            "parser_summary": {"csv_ready": True, "workbook_ready": True, "unmapped_vendors": 0},
            "cohort_membership_mode": "paper_locked_snapshot_membership",
            "cohort_membership_authority_note": "sample_id lock applied before dataset/contract gates",
            "min_malicious_detections_threshold": 5,
            "min_malicious_detections_rescued_unknown_consensus": 3,
        },
    )
    monkeypatch.setattr(
        startup_menu_review.diagnostics_banners,
        "build_diagnostics_overview",
        lambda **_kwargs: {
            "rows": [
                {"label": "Cohort / labels", "status": "GREEN"},
                {"label": "Taxonomy consistency", "status": "GREEN"},
                {"label": "Permission signal", "status": "GREEN"},
                {"label": "Vendor/parser coverage", "status": "GREEN"},
                {"label": "Feature matrix", "status": "GREEN"},
                {"label": "Evidence/provenance", "status": "GREEN"},
            ]
        },
    )

    summary = startup_menu_review.build_review_latest_run_summary(output_root=out_root, latest_run_id=run_id)

    assert summary["cohort_membership_mode"] == "paper_locked_snapshot_membership"
    assert summary["rescued_unknown_consensus"] == 3
    assert any("locked sample-id snapshot is authoritative" in str(w) for w in summary["warnings"])
    assert any("rows were retained with missing VT consensus" in str(w) for w in summary["warnings"])
    assert any("locked sample-id membership is the intended authority" in str(action) for action in summary["tuning_actions"])
    assert any("rescued missing-consensus malware rows" in str(action) for action in summary["tuning_actions"])
