from __future__ import annotations

from pathlib import Path

import pandas as pd

import scripts.diagnostics.report_vt_false_positive_review_triage as report_mod


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
