"""Tests for data-diagnostics banner helpers."""

from __future__ import annotations

import json
from pathlib import Path
import os
import time

import pytest

from obsidiandroid.cli.menu import diagnostics_banners

pytestmark = pytest.mark.contract


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "—"),
        ("—", "—"),
        (97.3109, "97.31%"),
        (100, "100.00%"),
        ("88", "88.00%"),
    ],
)
def test_format_percent_for_menu(value: object, expected: str) -> None:
    assert diagnostics_banners.format_percent_for_menu(value) == expected


def test_governed_cohort_n_prefers_q2_payload(tmp_path: Path) -> None:
    from obsidiandroid.cli.startup_menu_diagnostics import governed_cohort_n_for_q2 as _governed_cohort_n_for_q2

    rdiag = tmp_path / "run" / "diagnostics"
    gdiag = tmp_path / "diagnostics"
    rdiag.mkdir(parents=True, exist_ok=True)
    gdiag.mkdir(parents=True, exist_ok=True)
    assert _governed_cohort_n_for_q2(rdiag=rdiag, gdiag=gdiag, q2={"governed_cohort_n": 42}) == 42


def test_governed_cohort_n_falls_back_to_q1_json(tmp_path: Path) -> None:
    from obsidiandroid.cli.startup_menu_diagnostics import governed_cohort_n_for_q2 as _governed_cohort_n_for_q2

    rdiag = tmp_path / "run" / "diagnostics"
    gdiag = tmp_path / "diagnostics"
    rdiag.mkdir(parents=True, exist_ok=True)
    gdiag.mkdir(parents=True, exist_ok=True)
    (rdiag / "dataset_foundation_summary.json").write_text(
        '{"governed_samples": 100}',
        encoding="utf-8",
    )
    assert (
        _governed_cohort_n_for_q2(rdiag=rdiag, gdiag=gdiag, q2={"permission_signal_n": 1, "permission_signal_pct": 1.0})
        == 100
    )


def test_governed_cohort_n_infers_from_signal_when_no_json(tmp_path: Path) -> None:
    from obsidiandroid.cli.startup_menu_diagnostics import governed_cohort_n_for_q2 as _governed_cohort_n_for_q2

    rdiag = tmp_path / "run" / "diagnostics"
    gdiag = tmp_path / "diagnostics"
    rdiag.mkdir(parents=True, exist_ok=True)
    gdiag.mkdir(parents=True, exist_ok=True)
    assert (
        _governed_cohort_n_for_q2(
            rdiag=rdiag,
            gdiag=gdiag,
            q2={"permission_signal_n": 97, "permission_signal_pct": 97.0},
        )
        == 100
    )


def test_print_data_diagnostics_banner_reads_q2_from_global_when_run_json_missing(
    tmp_path: Path,
    capsys,
) -> None:
    """Q2 permission/vendor percentages should resolve from global diagnostics when run dir lacks JSON."""
    out_root = tmp_path / "output"
    rdiag = out_root / "runs" / "r1" / "diagnostics"
    rdiag.mkdir(parents=True, exist_ok=True)
    (out_root / "diagnostics").mkdir(parents=True, exist_ok=True)
    (rdiag / f"split_freeze_headline_r1.csv").write_text("sample_id\n1\n", encoding="utf-8")
    (out_root / "diagnostics" / "modality_contribution_summary.json").write_text(
        '{"permission_signal_pct": 99.5, "vendor_merge_pct": 88.0, "permission_signal_n": 10, "vendor_merge_n": 9}',
        encoding="utf-8",
    )
    (out_root / "diagnostics" / "run_manifest.latest.json").write_text(
        json.dumps({"run_id": "r1", "profile_params": {"profile_id": "demo_prof"}}),
        encoding="utf-8",
    )

    diagnostics_banners.print_data_diagnostics_banner(output_root=out_root, latest_run_id="r1")
    out = capsys.readouterr().out
    assert "99.50%" in out
    assert "88.00%" in out
    assert "Frozen profile_params (manifest)" in out
    assert "Available" in out


def test_print_data_diagnostics_banner_reports_post_run_enrichment_artifacts(
    tmp_path: Path,
    capsys,
) -> None:
    out_root = tmp_path / "output"
    rdiag = out_root / "runs" / "r1" / "diagnostics"
    enrich = rdiag / "post_run_enrichments" / "audit1"
    enrich.mkdir(parents=True, exist_ok=True)
    (rdiag / f"split_freeze_headline_r1.csv").write_text("sample_id\n1\n", encoding="utf-8")
    (enrich / "family_label_taxonomy_audit.csv").write_text("x\n1\n", encoding="utf-8")
    (enrich / "support_threshold_preview.md").write_text("# preview\n", encoding="utf-8")
    (out_root / "diagnostics").mkdir(parents=True, exist_ok=True)

    diagnostics_banners.print_data_diagnostics_banner(output_root=out_root, latest_run_id="r1")
    out = capsys.readouterr().out
    assert "Family taxonomy audit (post-run)" in out
    assert "Support threshold preview (post-run)" in out
    assert out.count("Available") >= 2


def test_build_diagnostics_overview_includes_traffic_lights_and_run_science_path(
    tmp_path: Path,
    monkeypatch,
) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    rdiag = out_root / "runs" / run_id / "diagnostics"
    rdiag.mkdir(parents=True, exist_ok=True)
    (out_root / "diagnostics").mkdir(parents=True, exist_ok=True)
    (rdiag / "cohort_foundation.json").write_text("{}", encoding="utf-8")
    (rdiag / "run_science_index.md").write_text("# run science\n", encoding="utf-8")
    (rdiag / "diagnostic_provenance.json").write_text('{"entries":[]}', encoding="utf-8")
    (rdiag / "feature_contract.json").write_text("{}", encoding="utf-8")
    (rdiag / f"taxonomy_authority_split_{run_id}.json").write_text(
        json.dumps(
            {
                "taxonomy_split": {
                    "type_authority_vs_rendering_mismatch": {
                        "counts": {
                            "type_mapping_mismatch": 1,
                            "type_label_missing": 1,
                            "type_label_noncanonical": 0,
                            "label_family_mismatch": 0,
                        }
                    },
                    "model_prediction_error": {"count": 1},
                }
            }
        ),
        encoding="utf-8",
    )
    (rdiag / "modality_contribution_summary.json").write_text(
        '{"permission_signal_pct": 97.31}',
        encoding="utf-8",
    )
    (out_root / "diagnostics" / "android_missing_resolution_triage_latest.csv").write_text(
        "sample_id,review_lane\n1,blank_package_review\n2,vt_tail_review\n",
        encoding="utf-8",
    )
    (out_root / "diagnostics" / "vt_false_positive_review_triage_latest.csv").write_text(
        "sample_id,review_lane\n1,real_malware_family_or_class_review\n2,file_artifact_review\n3,other_review\n",
        encoding="utf-8",
    )
    (out_root / "diagnostics" / "run_manifest.latest.json").write_text(
        json.dumps({"run_id": run_id, "publication_ready_status": "ready"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        diagnostics_banners,
        "build_operator_state",
        lambda **_kwargs: {
            "latest_run_id": run_id,
            "best_run_index_path": rdiag / "run_science_index.md",
            "has_canonical_run_science": True,
            "publication_ready_status": "ready",
            "parser_summary": {"csv_ready": True, "workbook_ready": False},
        },
    )
    monkeypatch.setattr(
        diagnostics_banners,
        "get_cohort_readiness_snapshot",
        lambda: {"status": "ok", "warnings": [], "buckets": {}, "taxonomy_signals": {"policy_held_family_samples": 129, "policy_held_family_token_kind_counts": {"generic_family_token": 5}}},
    )

    overview = diagnostics_banners.build_diagnostics_overview(output_root=out_root, latest_run_id=run_id)
    rows = {str(row["label"]): str(row["status"]) for row in overview["rows"]}
    assert rows["Cohort / labels"] == "GREEN"
    assert rows["Taxonomy consistency"] == "YELLOW"
    assert rows["Android missing-resolution triage"] == "YELLOW"
    assert rows["VT false-positive triage"] == "YELLOW"
    assert rows["Vendor/parser coverage"] == "YELLOW"
    assert rows["Claim readiness"] == "GREEN"
    assert str(overview["run_science_index_path"]).endswith("run_science_index.md")
    taxonomy_row = next(row for row in overview["rows"] if str(row["label"]) == "Taxonomy consistency")
    android_triage_row = next(row for row in overview["rows"] if str(row["label"]) == "Android missing-resolution triage")
    fp_triage_row = next(row for row in overview["rows"] if str(row["label"]) == "VT false-positive triage")
    focus_item = overview["focus_item"]
    assert "authority split" in str(taxonomy_row["action"]).lower()
    assert str(android_triage_row["detail"]) == "2 queued row(s); top=blank_package_review (1); freshness=current"
    assert str(fp_triage_row["detail"]) == "3 review row(s); top=real_malware_family_or_class_review (1); freshness=current"
    assert str(focus_item["label"]) == "Taxonomy consistency"
    assert "YELLOW" in str(focus_item["reason"])


def test_print_compact_diagnostics_overview_shows_triage_backlog_counts(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    rdiag = out_root / "runs" / run_id / "diagnostics"
    rdiag.mkdir(parents=True, exist_ok=True)
    (out_root / "diagnostics").mkdir(parents=True, exist_ok=True)
    (rdiag / "cohort_foundation.json").write_text("{}", encoding="utf-8")
    (rdiag / "run_science_index.md").write_text("# run science\n", encoding="utf-8")
    (rdiag / "feature_contract.json").write_text("{}", encoding="utf-8")
    (rdiag / "diagnostic_provenance.json").write_text('{"entries":[]}', encoding="utf-8")
    (rdiag / "modality_contribution_summary.json").write_text(
        json.dumps({"permission_signal_pct": 81.4}),
        encoding="utf-8",
    )
    (rdiag / f"taxonomy_authority_split_{run_id}.json").write_text(
        json.dumps(
            {
                "taxonomy_split": {
                    "type_authority_vs_rendering_mismatch": {
                        "counts": {
                            "type_mapping_mismatch": 1,
                            "type_label_missing": 0,
                            "type_label_noncanonical": 0,
                            "label_family_mismatch": 0,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (out_root / "diagnostics" / "android_missing_resolution_triage_latest.csv").write_text(
        "sample_id,review_lane\n1,blank_package_review\n2,vt_tail_review\n",
        encoding="utf-8",
    )
    (out_root / "diagnostics" / "vt_false_positive_review_triage_latest.csv").write_text(
        "sample_id,review_lane\n1,real_malware_family_or_class_review\n2,file_artifact_review\n3,other_review\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        diagnostics_banners,
        "build_operator_state",
        lambda **_kwargs: {
            "latest_run_id": run_id,
            "best_run_index_path": rdiag / "run_science_index.md",
            "has_canonical_run_science": True,
            "publication_ready_status": "ready",
            "parser_summary": {"csv_ready": True, "workbook_ready": True},
        },
    )
    monkeypatch.setattr(
        diagnostics_banners,
        "get_cohort_readiness_snapshot",
        lambda: {"status": "ok", "warnings": [], "buckets": {}, "taxonomy_signals": {"policy_held_family_samples": 129, "policy_held_family_token_kind_counts": {"generic_family_token": 5}}},
    )

    diagnostics_banners.print_compact_diagnostics_overview(output_root=out_root, latest_run_id=run_id)
    out = capsys.readouterr().out

    assert "Focus first" in out
    assert "Taxonomy consistency" in out
    assert "Reason: YELLOW; Review taxonomy authority split or post-run audit" in out
    assert "Android missing-resolution triage" in out
    assert "Backlog: 2 queued row(s); top=blank_package_review (1);" in out
    assert "freshness=current" in out
    assert "Backlog: 3 review row(s); top=real malware family/class…" in out


def test_build_diagnostics_overview_marks_stale_triage_export_red(
    tmp_path: Path,
    monkeypatch,
) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    rdiag = out_root / "runs" / run_id / "diagnostics"
    rdiag.mkdir(parents=True, exist_ok=True)
    gdiag = out_root / "diagnostics"
    gdiag.mkdir(parents=True, exist_ok=True)
    (rdiag / "cohort_foundation.json").write_text("{}", encoding="utf-8")
    (rdiag / "feature_contract.json").write_text("{}", encoding="utf-8")
    (rdiag / "diagnostic_provenance.json").write_text('{"entries":[]}', encoding="utf-8")
    (rdiag / "modality_contribution_summary.json").write_text(
        json.dumps({"permission_signal_pct": 76.2}),
        encoding="utf-8",
    )
    (rdiag / f"taxonomy_authority_split_{run_id}.json").write_text(
        json.dumps(
            {
                "taxonomy_split": {
                    "type_authority_vs_rendering_mismatch": {
                        "counts": {
                            "type_mapping_mismatch": 0,
                            "type_label_missing": 0,
                            "type_label_noncanonical": 0,
                            "label_family_mismatch": 0,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    triage_path = gdiag / "android_missing_resolution_triage_latest.csv"
    triage_path.write_text(
        "sample_id,review_lane\n1,blank_package_review\n",
        encoding="utf-8",
    )
    stale_epoch = time.time() - (96 * 3600)
    os.utime(triage_path, (stale_epoch, stale_epoch))
    monkeypatch.setattr(
        diagnostics_banners,
        "build_operator_state",
        lambda **_kwargs: {
            "latest_run_id": run_id,
            "best_run_index_path": rdiag / "run_science_index.md",
            "has_canonical_run_science": True,
            "publication_ready_status": "ready",
            "parser_summary": {"csv_ready": True, "workbook_ready": True},
        },
    )
    monkeypatch.setattr(
        diagnostics_banners,
        "get_cohort_readiness_snapshot",
        lambda: {"status": "ok", "warnings": [], "buckets": {}, "taxonomy_signals": {}},
    )

    overview = diagnostics_banners.build_diagnostics_overview(output_root=out_root, latest_run_id=run_id)
    row = next(row for row in overview["rows"] if str(row["label"]) == "Android missing-resolution triage")
    focus_item = overview["focus_item"]
    assert str(row["status"]) == "RED"
    assert "freshness=stale" in str(row["detail"])
    assert str(focus_item["label"]) == "Android missing-resolution triage"
    assert "Refresh Android missing-resolution triage export first" in str(focus_item["reason"])


def test_build_diagnostics_overview_surfaces_cohort_contract_context(
    tmp_path: Path,
    monkeypatch,
) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    rdiag = out_root / "runs" / run_id / "diagnostics"
    rdiag.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        diagnostics_banners,
        "build_operator_state",
        lambda **_kwargs: {
            "latest_run_id": run_id,
            "best_run_index_path": rdiag / "run_science_index.md",
            "has_canonical_run_science": True,
            "publication_ready_status": "ready",
            "parser_summary": {"csv_ready": True, "workbook_ready": True},
            "cohort_membership_mode": "paper_locked_snapshot_membership",
            "min_malicious_detections_rescued_unknown_consensus": 4,
        },
    )

    overview = diagnostics_banners.build_diagnostics_overview(output_root=out_root, latest_run_id=run_id)

    assert overview["cohort_membership_mode"] == "paper_locked_snapshot_membership"
    assert overview["rescued_unknown_consensus"] == 4


def test_build_diagnostics_overview_does_not_focus_green_zero_row_queue(
    tmp_path: Path,
    monkeypatch,
) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    rdiag = out_root / "runs" / run_id / "diagnostics"
    rdiag.mkdir(parents=True, exist_ok=True)
    gdiag = out_root / "diagnostics"
    gdiag.mkdir(parents=True, exist_ok=True)
    (rdiag / "run_science_index.md").write_text("# run science\n", encoding="utf-8")
    (rdiag / "cohort_foundation.json").write_text("{}", encoding="utf-8")
    (rdiag / "feature_contract.json").write_text("{}", encoding="utf-8")
    (rdiag / "diagnostic_provenance.json").write_text('{"entries":[]}', encoding="utf-8")
    (rdiag / "modality_contribution_summary.json").write_text(
        json.dumps({"permission_signal_pct": 79.8}),
        encoding="utf-8",
    )
    (rdiag / f"taxonomy_authority_split_{run_id}.json").write_text(
        json.dumps(
            {
                "taxonomy_split": {
                    "type_authority_vs_rendering_mismatch": {
                        "counts": {
                            "type_mapping_mismatch": 1,
                            "type_label_missing": 0,
                            "type_label_noncanonical": 0,
                            "label_family_mismatch": 0,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (gdiag / "android_missing_resolution_triage_latest.csv").write_text(
        "sample_id,review_lane\n",
        encoding="utf-8",
    )
    (gdiag / "vt_false_positive_review_triage_latest.csv").write_text(
        "sample_id,review_lane\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        diagnostics_banners,
        "build_operator_state",
        lambda **_kwargs: {
            "latest_run_id": run_id,
            "best_run_index_path": rdiag / "run_science_index.md",
            "has_canonical_run_science": True,
            "publication_ready_status": "unknown",
            "publication_ready_mode": False,
            "evidence_mode": False,
            "parser_summary": {"csv_ready": True, "workbook_ready": False},
        },
    )
    monkeypatch.setattr(
        diagnostics_banners,
        "get_cohort_readiness_snapshot",
        lambda: {"status": "ok", "warnings": [], "buckets": {}, "taxonomy_signals": {}},
    )

    overview = diagnostics_banners.build_diagnostics_overview(output_root=out_root, latest_run_id=run_id)

    assert str(overview["focus_item"]["label"]) == "Taxonomy consistency"
    assert "Android missing-resolution triage" != str(overview["focus_item"]["label"])
