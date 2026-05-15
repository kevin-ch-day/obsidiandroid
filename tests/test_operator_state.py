"""Tests for shared operator-state resolution."""

from __future__ import annotations

import json
from pathlib import Path

from obsidiandroid.cli.menu import operator_state


def test_build_operator_state_respects_run_override_and_best_index_fallback(tmp_path: Path) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    run_root = out_root / "runs" / run_id
    (run_root / "diagnostics").mkdir(parents=True, exist_ok=True)
    (out_root / "diagnostics").mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "profile_params": {"profile_id": "research_all_malicious"},
                "publication_ready_status": "unknown",
            }
        ),
        encoding="utf-8",
    )
    (run_root / "run_evidence_index.md").write_text("# evidence\n", encoding="utf-8")

    shared = operator_state.build_operator_state(output_base=out_root, run_id=run_id)

    assert shared["latest_run_id"] == run_id
    assert shared["profile_id"] == "research_all_malicious"
    assert shared["best_run_index_path"] == run_root / "run_evidence_index.md"
    assert shared["has_canonical_run_science"] is False


def test_build_operator_state_reports_canonical_run_science_when_present(tmp_path: Path) -> None:
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    run_root = out_root / "runs" / run_id
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (run_root / "run_manifest.json").write_text(
        json.dumps({"run_id": run_id, "profile_params": {"profile_id": "research_all_malicious"}}),
        encoding="utf-8",
    )
    (diagnostics_dir / "run_science_index.md").write_text("# science\n", encoding="utf-8")

    shared = operator_state.build_operator_state(output_base=out_root, run_id=run_id)

    assert shared["best_run_index_path"] == diagnostics_dir / "run_science_index.md"
    assert shared["has_canonical_run_science"] is True
