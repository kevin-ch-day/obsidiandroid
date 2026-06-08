from __future__ import annotations

from pathlib import Path

import pandas as pd

import scripts.diagnostics.report_blank_resolved_family_triage as report_mod


def test_export_singleton_worklists_filters_lane_and_clusters_packages() -> None:
    detail_rows = pd.DataFrame(
        [
            {
                "sample_id": 10,
                "android_package_name": "com.example.a",
                "review_lane": "singleton_provenance_review",
            },
            {
                "sample_id": 11,
                "android_package_name": "com.example.a",
                "review_lane": "singleton_provenance_review",
            },
            {
                "sample_id": 12,
                "android_package_name": "com.example.b",
                "review_lane": "pua_provenance_review",
            },
        ]
    )

    singleton_rows, singleton_clusters = report_mod._export_singleton_worklists(detail_rows)

    assert len(singleton_rows) == 2
    assert set(singleton_rows["android_package_name"]) == {"com.example.a"}
    assert len(singleton_clusters) == 1
    assert int(singleton_clusters.iloc[0]["sample_count"]) == 2


def test_main_exports_singleton_worklists(monkeypatch, tmp_path: Path, capsys) -> None:
    out_dir = tmp_path / "diagnostics"

    def _fake_build_report() -> dict[str, pd.DataFrame]:
        detail_rows = pd.DataFrame(
            [
                {
                    "sample_id": 1,
                    "android_package_name": "com.singleton",
                    "review_lane": "singleton_provenance_review",
                    "authority_bucket": "low_signal_singleton_provenance_review",
                }
            ]
        )
        return {
            "detail_rows": detail_rows,
            "lane_counts": pd.DataFrame([{"review_lane": "singleton_provenance_review", "row_count": 1}]),
            "authority_bucket_counts": pd.DataFrame([{"authority_bucket": "low_signal_singleton_provenance_review", "sample_count": 1}]),
            "package_clusters": pd.DataFrame([{"android_package_name": "com.singleton", "sample_count": 1}]),
        }

    monkeypatch.setattr(report_mod, "build_report", _fake_build_report)
    monkeypatch.setattr(report_mod, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(report_mod, "CSV_OUT", out_dir / "blank_resolved_family_triage_latest.csv")
    monkeypatch.setattr(report_mod, "SINGLETON_CSV_OUT", out_dir / "blank_resolved_singleton_provenance_latest.csv")
    monkeypatch.setattr(
        report_mod,
        "SINGLETON_CLUSTER_CSV_OUT",
        out_dir / "blank_resolved_singleton_package_clusters_latest.csv",
    )

    exit_code = report_mod.main()
    out = capsys.readouterr().out

    assert exit_code == 0
    assert (out_dir / "blank_resolved_singleton_provenance_latest.csv").exists()
    assert (out_dir / "blank_resolved_singleton_package_clusters_latest.csv").exists()
    assert "Singleton provenance rows: 1" in out
