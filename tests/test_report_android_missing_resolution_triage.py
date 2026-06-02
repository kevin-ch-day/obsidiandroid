from __future__ import annotations

from pathlib import Path

import pandas as pd

import scripts.diagnostics.report_android_missing_resolution_triage as report_mod


def test_main_exports_empty_triage_csv_with_compact_empty_summary(monkeypatch, tmp_path: Path, capsys) -> None:
    csv_out = tmp_path / "triage.csv"
    out_dir = tmp_path / "diagnostics"

    def _fake_build_report() -> dict[str, pd.DataFrame]:
        empty = pd.DataFrame()
        return {
            "lane_counts": pd.DataFrame(columns=["review_lane", "row_count"]),
            "action_counts": pd.DataFrame(columns=["recommended_action", "row_count"]),
            "top_clusters": pd.DataFrame(
                columns=[
                    "package_cluster_key",
                    "package_cluster_size",
                    "row_count",
                    "first_sample_id",
                    "last_sample_id",
                ]
            ),
            "vt_tail_rows": empty.copy(),
            "detail_rows": empty,
        }

    monkeypatch.setattr(report_mod, "build_report", _fake_build_report)
    monkeypatch.setattr(report_mod, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(report_mod, "CSV_OUT", csv_out)

    exit_code = report_mod.main()
    out = capsys.readouterr().out

    assert exit_code == 0
    assert csv_out.exists()
    assert "[EXPORT] Android missing-resolution triage: " in out
    assert "Rows: 0" in out
    assert "Status: no queued Android missing-resolution review rows." in out
    assert "== lane_counts ==" not in out
    assert "[empty]" not in out

