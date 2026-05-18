"""Tests for data-diagnostics banner helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidiandroid.cli.menu import diagnostics_banners


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
    from obsidiandroid.cli.startup_menu import _governed_cohort_n_for_q2

    rdiag = tmp_path / "run" / "diagnostics"
    gdiag = tmp_path / "diagnostics"
    rdiag.mkdir(parents=True, exist_ok=True)
    gdiag.mkdir(parents=True, exist_ok=True)
    assert _governed_cohort_n_for_q2(rdiag=rdiag, gdiag=gdiag, q2={"governed_cohort_n": 42}) == 42


def test_governed_cohort_n_falls_back_to_q1_json(tmp_path: Path) -> None:
    from obsidiandroid.cli.startup_menu import _governed_cohort_n_for_q2

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
    from obsidiandroid.cli.startup_menu import _governed_cohort_n_for_q2

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
    (rdiag / f"taxonomy_consistency_summary_{run_id}.json").write_text(
        '{"taxonomy_mismatch_count": 2}',
        encoding="utf-8",
    )
    (rdiag / "modality_contribution_summary.json").write_text(
        '{"permission_signal_pct": 97.31}',
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

    overview = diagnostics_banners.build_diagnostics_overview(output_root=out_root, latest_run_id=run_id)
    rows = {str(row["label"]): str(row["status"]) for row in overview["rows"]}
    assert rows["Cohort / labels"] == "GREEN"
    assert rows["Taxonomy consistency"] == "YELLOW"
    assert rows["Vendor/parser coverage"] == "YELLOW"
    assert rows["Publication readiness"] == "GREEN"
    assert str(overview["run_science_index_path"]).endswith("run_science_index.md")


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
