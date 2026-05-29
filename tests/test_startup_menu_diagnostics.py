"""Tests for data diagnostics compact taxonomy/support tuning screen."""

from __future__ import annotations

import json

from obsidiandroid.cli import startup_menu_diagnostics
from obsidiandroid.cli.menu.diagnostics import artifact_views


def test_taxonomy_support_tuning_compact_shows_status_and_tune_next(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
    capsys,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)

    write_text_file(
        rdiag / f"taxonomy_authority_split_{run_id}.json",
        json.dumps(
            {
                "source_mode": "live_view",
                "authority_scopes": {
                    "global_authority_catalog": {"bucket_counts": {"resolved_but_no_authority_family": 12}},
                    "run_cohort_authority": {"available": True, "bucket_counts": {"resolved_but_no_authority_family": 4}},
                },
                "taxonomy_split": {
                    "type_authority_vs_rendering_mismatch": {
                        "counts": {
                            "type_mapping_mismatch": 2,
                            "type_label_missing": 1,
                            "type_label_noncanonical": 1,
                            "label_family_mismatch": 1,
                        }
                    },
                    "model_prediction_error": {"count": 2},
                },
            }
        ),
    )
    write_text_file(rdiag / f"taxonomy_authority_split_{run_id}.md", "# Taxonomy Authority Split\n")
    write_text_file(
        rdiag / f"taxonomy_consistency_summary_{run_id}.json",
        json.dumps(
            {
                "taxonomy_mismatch_count": 5,
                "paper_facing_taxonomy_mismatch_count": 0,
                "type_mismatch_count": 2,
                "type_noncanonical_count": 1,
                "type_missing_label_count": 1,
                "family_label_mismatch_count": 1,
            }
        ),
    )
    write_text_file(
        rdiag / f"taxonomy_target_surfaces_{run_id}.json",
        json.dumps(
            {
                "label_strategy": {
                    "preferred_family_target": "family_id",
                    "preferred_type_target": "type_slug",
                    "avoid_for_primary_claims": ["category_primary"],
                    "alignment_interpretation": "Raw subtype aligns materially better than raw primary.",
                }
            }
        ),
    )
    write_text_file(
        rdiag / "family_label_taxonomy_audit.csv",
        "family_canonical,aligned_rows,support_status,configured_min_samples_per_family\n"
        "famA,25,retained,20\n"
        "famB,19,dropped_low_support,20\n"
        "famC,18,dropped_low_support,20\n",
    )
    write_text_file(rdiag / "support_threshold_preview.csv", "threshold,retained_families\n20,1\n")

    monkeypatch.setattr(startup_menu_diagnostics, "resolve_display_mode", lambda: "compact")

    startup_menu_diagnostics.launch_taxonomy_support_tuning_compact_menu(read_latest_run_id=lambda: run_id)
    out = capsys.readouterr().out

    assert "Taxonomy & support tuning" in out
    assert "Taxonomy health" in out
    assert "Model prediction error count" in out
    assert "Authority gap rows (run/global)" in out
    assert "Claim-facing mismatch total" in out
    assert "Families just below threshold" in out
    assert "Preferred family target" in out
    assert "Avoid for primary claims" in out
    assert "tune next" in out.lower()
    assert "taxonomy_authority_split" in out
    assert "taxonomy_model_prediction_errors" in out


def test_taxonomy_support_snapshot_includes_threshold_sensitivity(
    make_run_diagnostics_layout,
    write_text_file,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    write_text_file(
        rdiag / "family_label_taxonomy_audit.csv",
        "family_canonical,aligned_rows,support_status,configured_min_samples_per_family\n"
        "famA,25,retained,20\n"
        "famB,12,dropped_low_support,20\n"
        "famC,4,dropped_low_support,20\n",
    )
    write_text_file(
        rdiag / f"taxonomy_authority_split_{run_id}.json",
        json.dumps(
            {
                "authority_scopes": {
                    "global_authority_catalog": {"bucket_counts": {"resolved_but_no_authority_family": 10}},
                    "run_cohort_authority": {"available": True, "bucket_counts": {"resolved_but_no_authority_family": 3}},
                },
                "taxonomy_split": {
                    "type_authority_vs_rendering_mismatch": {
                        "counts": {
                            "type_mapping_mismatch": 2,
                            "type_label_missing": 1,
                            "type_label_noncanonical": 0,
                            "label_family_mismatch": 1,
                        }
                    },
                    "model_prediction_error": {"count": 2},
                },
            }
        ),
    )
    write_text_file(rdiag / f"taxonomy_authority_split_{run_id}.md", "# Taxonomy Authority Split\n")
    write_text_file(
        rdiag / f"taxonomy_target_surfaces_{run_id}.json",
        json.dumps(
            {
                "label_strategy": {
                    "preferred_family_target": "family_id",
                    "preferred_family_reporting_surface": "family_canonical",
                    "preferred_type_target": "type_slug",
                    "preferred_hierarchical_target": "family_within_type",
                    "avoid_for_primary_claims": ["category_primary"],
                    "alignment_interpretation": "Raw subtype aligns materially better than raw primary.",
                }
            }
        ),
    )
    snap = startup_menu_diagnostics.build_taxonomy_support_tuning_snapshot(run_id=run_id, output_root=out_root)
    assert snap["paper_facing_taxonomy_mismatch_total"] == "—"
    assert snap["model_prediction_error_count"] == 2
    assert snap["family_mismatch_count"] == 2
    assert snap["authority_gap_run_count"] == 3
    assert snap["taxonomy_authority_split_path"].endswith(".md")
    assert snap["preferred_family_target"] == "family_id"
    assert snap["preferred_type_target"] == "type_slug"
    assert snap["avoid_for_primary_claims"] == ["category_primary"]
    sensitivity = snap.get("threshold_sensitivity")
    assert isinstance(sensitivity, list)
    assert len(sensitivity) == 5
    assert sensitivity[0]["threshold"] == 5


def test_taxonomy_support_snapshot_prefers_sql_governed_threshold_preview(
    make_run_diagnostics_layout,
    write_text_file,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    write_text_file(
        rdiag / "family_label_taxonomy_audit.csv",
        "family_canonical,aligned_rows,support_status,configured_min_samples_per_family\n"
        "famA,25,retained,20\n"
        "famB,12,dropped_low_support,20\n",
    )
    write_text_file(
        rdiag / "sql_governed_family_label_taxonomy_audit.csv",
        "family_canonical,aligned_rows,support_status,configured_min_samples_per_family\n"
        "famA,25,retained,20\n"
        "famB,12,dropped_low_support,20\n"
        "famC,7,dropped_low_support,20\n",
    )
    write_text_file(
        rdiag / f"taxonomy_authority_split_{run_id}.json",
        json.dumps(
            {
                "authority_scopes": {
                    "global_authority_catalog": {"bucket_counts": {"resolved_but_no_authority_family": 10}},
                    "run_cohort_authority": {"available": True, "bucket_counts": {"resolved_but_no_authority_family": 3}},
                },
                "taxonomy_split": {
                    "type_authority_vs_rendering_mismatch": {
                        "counts": {
                            "type_mapping_mismatch": 2,
                            "type_label_missing": 1,
                            "type_label_noncanonical": 0,
                            "label_family_mismatch": 1,
                        }
                    },
                    "model_prediction_error": {"count": 2},
                },
            }
        ),
    )
    write_text_file(rdiag / f"taxonomy_authority_split_{run_id}.md", "# Taxonomy Authority Split\n")

    snap = startup_menu_diagnostics.build_taxonomy_support_tuning_snapshot(run_id=run_id, output_root=out_root)
    assert snap["families_before_threshold"] == 3
    assert snap["family_label_taxonomy_audit_path"].endswith("sql_governed_family_label_taxonomy_audit.csv")


def test_taxonomy_consistency_review_prefers_taxonomy_authority_split(
    make_run_diagnostics_layout,
    write_text_file,
    capsys,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    write_text_file(
        rdiag / f"taxonomy_authority_split_{run_id}.json",
        json.dumps(
            {
                "source_mode": "live_view",
                "authority_scopes": {
                    "global_authority_catalog": {"available": True},
                    "run_cohort_authority": {
                        "available": True,
                        "bucket_counts": {
                            "resolved_but_no_authority_family": 4,
                            "generic_label_candidate": 1,
                            "authority_family_unknown_type": 2,
                        },
                    },
                },
                "taxonomy_split": {
                    "type_authority_vs_rendering_mismatch": {
                        "counts": {
                            "type_mapping_mismatch": 3,
                            "type_label_missing": 1,
                            "type_label_noncanonical": 1,
                            "label_family_mismatch": 0,
                        }
                    },
                    "model_prediction_error": {"count": 2},
                    "generic_or_coarse_label_issue": {"global_row_count": 9},
                    "unknown_type_family_issue": {"global_row_count": 6},
                },
            }
        ),
    )
    write_text_file(rdiag / f"taxonomy_authority_split_{run_id}.md", "# Taxonomy Authority Split\n")

    artifact_views.launch_taxonomy_consistency_review_menu(
        read_latest_run_id=lambda: run_id,
        output_root=out_root,
        first_existing_path_fn=startup_menu_diagnostics.first_existing_path,
    )
    out = capsys.readouterr().out

    assert "Taxonomy consistency review" in out
    assert "Authority split source mode" in out


def test_taxonomy_support_tuning_warns_when_using_global_latest_mirror(
    monkeypatch,
    make_run_diagnostics_layout,
    write_text_file,
    capsys,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    gdiag = out_root / "diagnostics"
    write_text_file(
        gdiag / "taxonomy_authority_split.latest.json",
        json.dumps(
            {
                "source_mode": "live_view",
                "authority_scopes": {
                    "global_authority_catalog": {"bucket_counts": {"resolved_but_no_authority_family": 8}},
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
    write_text_file(gdiag / "taxonomy_authority_split.latest.md", "# Taxonomy Authority Split\n")
    write_text_file(gdiag / "taxonomy_target_surfaces.latest.json", json.dumps({"label_strategy": {"preferred_family_target": "family_id"}}))
    write_text_file(gdiag / "taxonomy_consistency_summary.latest.json", json.dumps({"taxonomy_mismatch_count": 1}))
    write_text_file(rdiag / "family_label_taxonomy_audit.csv", "family_canonical,aligned_rows,support_status,configured_min_samples_per_family\nfamA,5,retained,3\n")

    monkeypatch.setattr(startup_menu_diagnostics, "resolve_display_mode", lambda: "compact")
    startup_menu_diagnostics.launch_taxonomy_support_tuning_compact_menu(read_latest_run_id=lambda: run_id)
    out = capsys.readouterr().out

    assert "Artifact provenance" in out
    assert "global_latest_mirror" in out
    assert "global latest mirror" in out.lower()


def test_taxonomy_consistency_review_warns_when_using_global_latest_mirror(
    make_run_diagnostics_layout,
    write_text_file,
    capsys,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, _rdiag, _ = make_run_diagnostics_layout(run_id)
    gdiag = out_root / "diagnostics"
    write_text_file(
        gdiag / "taxonomy_authority_split.latest.json",
        json.dumps(
            {
                "source_mode": "global_fallback",
                "authority_scopes": {"global_authority_catalog": {"available": True}},
                "taxonomy_split": {
                    "type_authority_vs_rendering_mismatch": {
                        "counts": {
                            "type_mapping_mismatch": 2,
                            "type_label_missing": 1,
                            "type_label_noncanonical": 0,
                            "label_family_mismatch": 0,
                        }
                    },
                    "model_prediction_error": {"count": 0},
                },
            }
        ),
    )
    write_text_file(gdiag / "taxonomy_authority_split.latest.md", "# Taxonomy Authority Split\n")
    write_text_file(
        gdiag / "taxonomy_consistency_summary.latest.json",
        json.dumps({"taxonomy_mismatch_count": 3, "type_guard_family_suppressed_count": 2}),
    )

    artifact_views.launch_taxonomy_consistency_review_menu(
        read_latest_run_id=lambda: run_id,
        output_root=out_root,
        first_existing_path_fn=startup_menu_diagnostics.first_existing_path,
    )
    out = capsys.readouterr().out

    assert "Artifact provenance" in out
    assert "global_latest_mirror" in out
    assert "global latest mirror" in out.lower()
    assert "Model prediction errors" in out
    assert "Type-guard suppressions" in out
    assert "Taxonomy authority split (Markdown)" in out
    assert "Taxonomy authority gap summary (CSV)" in out


def test_permission_intelligence_coverage_shows_artifact_origin_and_warns_on_global_mirror(
    make_run_diagnostics_layout,
    write_text_file,
    capsys,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, _rdiag, _ = make_run_diagnostics_layout(run_id)
    gdiag = out_root / "diagnostics"
    write_text_file(
        gdiag / "modality_contribution_summary.json",
        json.dumps({"permission_signal_pct": 95.0, "permission_signal_n": 10, "vendor_merge_pct": 90.0, "vendor_merge_n": 9}),
    )
    write_text_file(gdiag / "permission_coverage_summary.csv", "a,b\n1,2\n")

    artifact_views.launch_permission_intelligence_coverage_menu(
        read_latest_run_id=lambda: run_id,
        output_root=out_root,
        first_existing_path_fn=startup_menu_diagnostics.first_existing_path,
        governed_cohort_n_for_q2_fn=lambda **_kwargs: 10,
    )
    out = capsys.readouterr().out

    assert "Permission coverage summary" in out
    assert "global_latest_mirror" in out
    assert "Permission intelligence coverage is using at least one global latest mirror artifact" in out


def test_feature_matrix_modality_view_shows_artifact_origin_and_warns_on_global_mirror(
    make_run_diagnostics_layout,
    write_text_file,
    capsys,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, _rdiag, _ = make_run_diagnostics_layout(run_id)
    gdiag = out_root / "diagnostics"
    write_text_file(gdiag / "feature_contract.json", json.dumps({"feature_columns": 10}))

    artifact_views.launch_feature_matrix_modality_menu(
        read_latest_run_id=lambda: run_id,
        output_root=out_root,
        first_existing_path_fn=startup_menu_diagnostics.first_existing_path,
    )
    out = capsys.readouterr().out

    assert "Feature contract" in out
    assert "global_latest_mirror" in out
    assert "Feature matrix / modality coverage is using at least one global latest mirror artifact" in out


def test_cohort_family_artifact_paths_show_origin_for_global_latest_mirror(
    make_run_diagnostics_layout,
    write_text_file,
    capsys,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    gdiag = out_root / "diagnostics"
    write_text_file(gdiag / "analysis_snapshot.latest.csv", "sample_id\n1\n")

    startup_menu_diagnostics._cohort_audit.print_cohort_family_artifact_paths(
        read_latest_run_id=lambda: run_id,
        output_root=out_root,
        latest_post_run_enrichment_dir_fn=lambda _rdiag: None,
        latest_post_run_entry_fn=lambda _rdiag: {},
    )
    out = capsys.readouterr().out

    assert "analysis_snapshot.latest.csv" in out
    assert "present [global_latest_mirror]" in out


def test_cohort_family_artifact_paths_show_taxonomy_drift_from_latest_enrichment(
    make_run_diagnostics_layout,
    write_text_file,
    capsys,
) -> None:
    run_id = "20260515T141956Z__58d84f"
    out_root, rdiag, _ = make_run_diagnostics_layout(run_id)
    enrichment_dir = rdiag / "post_run_enrichments" / "audit1"
    enrichment_dir.mkdir(parents=True, exist_ok=True)

    startup_menu_diagnostics._cohort_audit.print_cohort_family_artifact_paths(
        read_latest_run_id=lambda: run_id,
        output_root=out_root,
        latest_post_run_enrichment_dir_fn=lambda _rdiag: enrichment_dir,
        latest_post_run_entry_fn=lambda _rdiag: {
            "audit_profile": "malicious_temporal_stability_locked",
            "target_run_profile": "malicious_temporal_stability_locked",
            "same_profile_as_target": True,
            "cohort_lock_status": "membership_locked_taxonomy_drift",
            "taxonomy_label_drift": {
                "drift_class": "taxonomy_expansion",
                "family_delta": 5,
                "type_delta": 1,
                "recommended_action": "Review newly split families/types.",
            },
        },
    )
    out = capsys.readouterr().out

    assert "Taxonomy drift" in out
    assert "taxonomy_expansion" in out
    assert "family_delta=+5" in out
