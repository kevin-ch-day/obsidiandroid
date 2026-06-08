from __future__ import annotations

from pathlib import Path

import pandas as pd

import scripts.diagnostics.report_android_missing_resolution_triage as missing_mod
import scripts.diagnostics.report_vt_false_positive_review_triage as report_mod


def test_export_lane_worklists_skips_vt_tail_and_writes_other_lanes(tmp_path: Path) -> None:
    detail_rows = pd.DataFrame(
        [
            {"sample_id": 1, "review_lane": "vt_tail_review", "sha256": "a"},
            {"sample_id": 2, "review_lane": "package_cluster_review", "sha256": "b"},
            {"sample_id": 3, "review_lane": "package_cluster_review", "sha256": "c"},
        ]
    )
    lane_counts = pd.DataFrame(
        [
            {"review_lane": "vt_tail_review", "row_count": 1},
            {"review_lane": "package_cluster_review", "row_count": 2},
        ]
    )
    out_dir = tmp_path / "diagnostics"
    out_dir.mkdir(parents=True)
    missing_mod.OUTPUT_DIR = out_dir

    exports = missing_mod._export_lane_worklists(detail_rows, lane_counts)

    assert set(exports) == {"package_cluster_review"}
    export_path = exports["package_cluster_review"]
    assert export_path.name == "android_missing_resolution_lane_package_cluster_review_latest.csv"
    exported = pd.read_csv(export_path)
    assert len(exported) == 2
    assert "vt_tail_review" not in set(exported["review_lane"])


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

    monkeypatch.setattr(missing_mod, "build_report", _fake_build_report)
    monkeypatch.setattr(missing_mod, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(missing_mod, "CSV_OUT", csv_out)
    monkeypatch.setattr(missing_mod, "VT_TAIL_CSV_OUT", out_dir / "android_missing_resolution_vt_tail_latest.csv")
    monkeypatch.setattr(missing_mod, "_export_lane_worklists", lambda *_args, **_kwargs: {})

    exit_code = missing_mod.main()
    out = capsys.readouterr().out

    assert exit_code == 0
    assert csv_out.exists()
    assert "[EXPORT] Android missing-resolution triage: " in out
    assert "Rows: 0" in out
    assert "Status: no queued Android missing-resolution review rows." in out
    assert "== lane_counts ==" not in out
    assert "[empty]" not in out


def test_build_report_groups_global_policy_and_lanes(monkeypatch) -> None:
    queries: list[str] = []

    def _fake_query(query: str, **_kwargs):
        queries.append(query)
        if "GROUP BY review_lane" in query:
            return pd.DataFrame(
                [
                    {"review_lane": "real_malware_family_or_class_review", "row_count": 17},
                    {"review_lane": "file_artifact_review", "row_count": 15},
                ]
            )
        if "GROUP BY recommended_triage_action" in query:
            return pd.DataFrame(
                [
                    {"recommended_triage_action": "retain_for_malware_review", "row_count": 17},
                    {"recommended_triage_action": "artifact_name_noise_review", "row_count": 22},
                ]
            )
        if "GROUP BY global_policy_bucket" in query:
            return pd.DataFrame(
                [
                    {"global_policy_bucket": "single_vendor_low_context_review", "row_count": 36},
                    {"global_policy_bucket": "no_global_policy_match", "row_count": 16},
                ]
            )
        if "GROUP BY sample_label" in query:
            return pd.DataFrame(
                [
                    {"sample_label": "Gigabud", "row_count": 16, "min_malicious": 1, "max_malicious": 2},
                    {"sample_label": "UNCLASSIFIED", "row_count": 7, "min_malicious": 1, "max_malicious": 2},
                ]
            )
        if "WHERE review_lane = 'real_malware_family_or_class_review'" in query:
            return pd.DataFrame(
                [
                    {
                        "sample_id": 1663,
                        "sha256": "abc",
                        "sample_label": "Gigabud",
                        "family_label": "Gigabud",
                        "platform": "android",
                        "android_package_name": "com.example",
                        "vt_malicious_count": 2,
                        "vt_suspicious_count": 0,
                        "vt_harmless_count": 0,
                        "vt_total_engines": 68,
                        "raw_detection_ratio": 0.0294,
                        "confidence_score": 20.0,
                        "confidence_bucket": "review",
                        "review_lane": "real_malware_family_or_class_review",
                        "recommended_triage_action": "retain_for_malware_review",
                    }
                ]
            )
        return pd.DataFrame(
            [
                {
                    "sample_id": 1663,
                    "sha256": "abc",
                    "sample_label": "Gigabud",
                    "family_label": "Gigabud",
                    "platform": "android",
                    "android_package_name": "com.example",
                    "vt_malicious_count": 2,
                    "vt_suspicious_count": 0,
                    "vt_harmless_count": 0,
                    "vt_total_engines": 68,
                    "raw_detection_ratio": 0.0294,
                    "confidence_score": 20.0,
                    "confidence_bucket": "review",
                    "recommended_action": "retain_for_malware_review",
                    "review_reason": "low_consensus",
                    "review_lane": "real_malware_family_or_class_review",
                    "recommended_triage_action": "retain_for_malware_review",
                }
            ]
        )

    monkeypatch.setattr(report_mod.db_engine, "execute_query", _fake_query)

    report = report_mod.build_report()

    assert not report["lane_counts"].empty
    assert not report["action_counts"].empty
    assert not report["global_policy_counts"].empty
    assert "GROUP BY global_policy_bucket" in "\n".join(queries)


def test_main_exports_latest_triage_csv(monkeypatch, tmp_path: Path) -> None:
    csv_out = tmp_path / "triage.csv"
    out_dir = tmp_path / "diagnostics"

    def _fake_build_report() -> dict[str, pd.DataFrame]:
        frame = pd.DataFrame(
            [
                {
                    "sample_id": 1,
                    "sha256": "abc",
                    "sample_label": "Gigabud",
                    "family_label": "Gigabud",
                    "platform": "android",
                    "android_package_name": "com.example",
                    "vt_malicious_count": 2,
                    "vt_suspicious_count": 0,
                    "vt_harmless_count": 0,
                    "vt_total_engines": 68,
                    "raw_detection_ratio": 0.0294,
                    "confidence_score": 20.0,
                    "confidence_bucket": "review",
                    "recommended_action": "retain_for_malware_review",
                    "review_reason": "low_consensus",
                    "review_lane": "real_malware_family_or_class_review",
                    "recommended_triage_action": "retain_for_malware_review",
                }
            ]
        )
        return {
            "lane_counts": pd.DataFrame([{"review_lane": "real_malware_family_or_class_review", "row_count": 1}]),
            "action_counts": pd.DataFrame([{"recommended_triage_action": "retain_for_malware_review", "row_count": 1}]),
            "global_policy_counts": pd.DataFrame([{"global_policy_bucket": "single_vendor_low_context_review", "row_count": 1}]),
            "top_labels": pd.DataFrame([{"sample_label": "Gigabud", "row_count": 1, "min_malicious": 2, "max_malicious": 2}]),
            "real_malware_rows": frame.copy(),
            "detail_rows": frame,
        }

    monkeypatch.setattr(report_mod, "build_report", _fake_build_report)
    monkeypatch.setattr(report_mod, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(report_mod, "CSV_OUT", csv_out)

    exit_code = report_mod.main()

    assert exit_code == 0
    assert csv_out.exists()
    assert "Gigabud" in csv_out.read_text(encoding="utf-8")
