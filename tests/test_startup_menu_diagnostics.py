"""Tests for data diagnostics compact taxonomy/support tuning screen."""

from __future__ import annotations

import json
from pathlib import Path

from config import app_config
from obsidiandroid.cli import startup_menu_diagnostics


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_taxonomy_support_tuning_compact_shows_status_and_tune_next(monkeypatch, tmp_path: Path, capsys) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    rdiag = out_root / "runs" / run_id / "diagnostics"

    _write(
        rdiag / f"taxonomy_consistency_summary_{run_id}.json",
        json.dumps(
            {
                "taxonomy_mismatch_count": 5,
                "type_mismatch_count": 2,
                "type_noncanonical_count": 1,
                "type_missing_label_count": 1,
                "family_label_mismatch_count": 1,
            }
        ),
    )
    _write(
        rdiag / "family_label_taxonomy_audit.csv",
        "family_canonical,aligned_rows,support_status,configured_min_samples_per_family\n"
        "famA,25,retained,20\n"
        "famB,19,dropped_low_support,20\n"
        "famC,18,dropped_low_support,20\n",
    )
    _write(rdiag / "support_threshold_preview.csv", "threshold,retained_families\n20,1\n")

    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.setattr(startup_menu_diagnostics, "resolve_display_mode", lambda: "compact")

    startup_menu_diagnostics.launch_taxonomy_support_tuning_compact_menu(read_latest_run_id=lambda: run_id)
    out = capsys.readouterr().out

    assert "Taxonomy & support tuning" in out
    assert "Taxonomy health" in out
    assert "Families just below threshold" in out
    assert "tune next" in out.lower()
    assert "taxonomy_type_authority_review" in out


def test_taxonomy_support_snapshot_includes_threshold_sensitivity(monkeypatch, tmp_path: Path) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    rdiag = out_root / "runs" / run_id / "diagnostics"
    _write(
        rdiag / "family_label_taxonomy_audit.csv",
        "family_canonical,aligned_rows,support_status,configured_min_samples_per_family\n"
        "famA,25,retained,20\n"
        "famB,12,dropped_low_support,20\n"
        "famC,4,dropped_low_support,20\n",
    )
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    snap = startup_menu_diagnostics.build_taxonomy_support_tuning_snapshot(run_id=run_id, output_root=out_root)
    sensitivity = snap.get("threshold_sensitivity")
    assert isinstance(sensitivity, list)
    assert len(sensitivity) == 5
    assert sensitivity[0]["threshold"] == 5
