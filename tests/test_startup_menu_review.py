"""Tests for the Review Latest Run operator flow."""

from __future__ import annotations

import json
from pathlib import Path

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
    assert "Permission Intel unavailable for readiness counts." in out
    assert "Taxonomy & Support Tuning" in out
    assert "Model prediction errors vs type/rendering" in out
    assert "Permission Coverage Tuning" in out


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
