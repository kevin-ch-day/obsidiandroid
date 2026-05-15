"""Tests for parser diagnostics state helpers."""

from __future__ import annotations

from pathlib import Path
import json

import pandas as pd

from obsidiandroid.cli.menu import vendor_parser_state


def test_resolve_vendor_parser_coverage_csv_prefers_run_scoped_file(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Run-scoped parser coverage should win over the global latest mirror."""
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    run_diag = out_root / "runs" / run_id / "diagnostics"
    global_diag = out_root / "diagnostics"
    run_diag.mkdir(parents=True, exist_ok=True)
    global_diag.mkdir(parents=True, exist_ok=True)
    (run_diag / "vendor_parser_coverage.latest.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (global_diag / "vendor_parser_coverage.latest.csv").write_text("a,b\n3,4\n", encoding="utf-8")

    monkeypatch.setattr(vendor_parser_state.app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.setattr(vendor_parser_state.run_locator, "read_latest_run_id", lambda: run_id)

    resolved = vendor_parser_state.resolve_vendor_parser_coverage_csv()

    assert resolved == run_diag / "vendor_parser_coverage.latest.csv"


def test_build_parser_diagnostics_state_returns_compact_counts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Parser diagnostics state should return stable summary counts and paths."""
    out_root = tmp_path / "output"
    run_id = "20260515T141956Z__58d84f"
    run_diag = out_root / "runs" / run_id / "diagnostics"
    global_diag = out_root / "diagnostics"
    run_diag.mkdir(parents=True, exist_ok=True)
    global_diag.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"vendor_column": "a", "coverage_pct": 95.0, "parser_mapped": 1},
            {"vendor_column": "b", "coverage_pct": 80.0, "parser_mapped": 0},
        ]
    ).to_csv(run_diag / "vendor_parser_coverage.latest.csv", index=False)
    pd.DataFrame([{"engine_name": "a"}, {"engine_name": "b"}]).to_csv(
        run_diag / "engine_scoring_summary.csv",
        index=False,
    )
    (global_diag / "run_manifest.latest.json").write_text(
        json.dumps({"run_id": run_id, "selected_vendor_count": 8}),
        encoding="utf-8",
    )

    monkeypatch.setattr(vendor_parser_state.app_config, "DEFAULT_OUTPUT_DIR", str(out_root), raising=False)
    monkeypatch.setattr(vendor_parser_state.run_locator, "read_latest_run_id", lambda: run_id)

    state = vendor_parser_state.build_parser_diagnostics_state(
        workbook_loader=lambda **_kwargs: None
    )

    assert state["csv_ready"] is True
    assert state["workbook_ready"] is False
    assert state["observed_engines"] == 2
    assert state["parser_mapped_vendors"] == 1
    assert state["unmapped_vendors"] == 1
    assert state["selected_vendors"] == 8
    assert state["engine_scoring_universe"] == 2
    assert state["source_run_id"] == run_id
    assert state["coverage_from_latest_run"] is True
    assert state["selected_vendor_data_present"] is False
