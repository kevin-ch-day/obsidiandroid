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
    assert "Hostile audit" in out
