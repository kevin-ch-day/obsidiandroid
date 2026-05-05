"""Unit tests for alignment gap diagnostics (no live DB)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.diagnostics import alignment_gap_diagnostics as agd


def test_infer_likely_missing_reason_vendor_verdicts_first() -> None:
    row = pd.Series(
        {
            "in_catalog": 1,
            "has_vendor_verdicts": 0,
            "has_scan_summary": 0,
            "has_signal_current": 0,
            "has_androguard_current": 0,
            "has_pi_permissions": 0,
        }
    )
    assert agd.infer_likely_missing_reason(row, androguard_table_tracked=True) == "no_vendor_verdicts"


def test_infer_likely_missing_reason_androguard_only_when_tracked() -> None:
    row = pd.Series(
        {
            "in_catalog": 1,
            "has_vendor_verdicts": 1,
            "has_scan_summary": 1,
            "has_signal_current": 1,
            "has_androguard_current": 0,
            "has_pi_permissions": 1,
        }
    )
    assert agd.infer_likely_missing_reason(row, androguard_table_tracked=True) == "no_androguard_current"
    assert agd.infer_likely_missing_reason(row, androguard_table_tracked=False) == "unknown_feature_builder_drop"


def test_infer_unknown_when_all_signals_present() -> None:
    row = pd.Series(
        {
            "in_catalog": 1,
            "has_vendor_verdicts": 1,
            "has_scan_summary": 1,
            "has_signal_current": 1,
            "has_androguard_current": 1,
            "has_pi_permissions": 1,
        }
    )
    assert agd.infer_likely_missing_reason(row, androguard_table_tracked=True) == "unknown_feature_builder_drop"


def test_build_alignment_gap_summary_counts() -> None:
    df = pd.DataFrame(
        {
            "likely_missing_reason": ["no_vendor_verdicts", "no_vendor_verdicts", "no_pi_permissions"],
            "has_vendor_verdicts": [0, 0, 1],
            "has_scan_summary": [0, 1, 1],
            "has_signal_current": [0, 1, 1],
            "has_androguard_current": [0, 1, 1],
            "has_pi_permissions": [0, 0, 0],
            "family_label": ["A", "B", "C"],
            "classification_primary": ["Trojan", "Trojan", "Adware"],
            "optional_table_vt_state": [0, 0, 0],
            "optional_table_androguard_current": [0, 0, 0],
        }
    )
    summary = agd.build_alignment_gap_summary(df)
    assert summary["total_unmatched_labels"] == 3
    assert summary["missing_vendor_verdicts"] == 2
    assert summary["reason_counts"]["no_vendor_verdicts"] == 2
    assert summary["reason_counts"]["no_pi_permissions"] == 1
    assert "recommended_next_fix" in summary
    assert "verdict" in summary["recommended_next_fix"].lower()


def test_build_alignment_gap_summary_empty() -> None:
    summary = agd.build_alignment_gap_summary(pd.DataFrame())
    assert summary["total_unmatched_labels"] == 0
    assert summary["reason_counts"] == {}
    assert "recommended_next_fix" in summary


def test_load_unmatched_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "unmatched_label_ids.csv"
    p.write_text("sample_id\n", encoding="utf-8")
    assert agd.load_unmatched_label_sample_ids(p) == []


def test_write_artifacts_roundtrip(tmp_path: Path) -> None:
    diag = tmp_path / "diagnostics"
    diag.mkdir(parents=True)
    df = pd.DataFrame({"sample_id": [1], "likely_missing_reason": ["no_vendor_verdicts"]})
    summary = {"total_unmatched_labels": 1, "reason_counts": {"no_vendor_verdicts": 1}}
    csv_p, json_p, md_p = agd.write_alignment_gap_artifacts(diag, df, summary)
    assert csv_p.is_file()
    payload = json.loads(json_p.read_text(encoding="utf-8"))
    assert payload["total_unmatched_labels"] == 1
    assert "Alignment gap" in md_p.read_text(encoding="utf-8")


def test_collect_with_stub_executors() -> None:
    """Deterministic stub SQL routing for integration-style unit test."""

    def fake_eq(sql: str, params=None, fetch=False, return_columns=False):
        assert fetch and return_columns
        params = params or ()
        if "malware_sample_catalog" in sql:
            cols = [
                "sample_id",
                "sha256",
                "family_label",
                "classification_primary",
                "classification_subtype",
                "android_package_name",
                "android_permission_count",
            ]
            rows = [
                (
                    params[0],
                    "a" * 64,
                    "Fam",
                    "Trojan",
                    "banker",
                    "pkg",
                    5,
                )
            ]
            return cols, rows
        if "information_schema" in sql:
            return ["TABLE_NAME"], []
        if "virustotal_sample_vendor_engine_verdicts" in sql and "COUNT" in sql:
            return ["sample_id", "verdict_row_count"], [(params[0], 0)]
        if "virustotal_sample_scan_summary" in sql:
            return ["sample_id", "has_scan_summary"], []
        if "virustotal_sample_signal_current" in sql:
            return ["sample_id", "has_signal_current"], []
        return [], []

    def fake_ep(sql: str, params=None, fetch=False, return_columns=False):
        assert fetch and return_columns
        if "android_permission_obs_sample" in sql:
            return ["sample_id", "pi_permission_count", "pi_classification_count"], []
        return [], []

    out = agd.collect_alignment_gap_detail_frame(
        [101],
        execute_query=fake_eq,
        execute_permission_query=fake_ep,
        chunk_size=50,
    )
    assert len(out) == 1
    assert int(out.iloc[0]["has_vendor_verdicts"]) == 0
    assert out.iloc[0]["likely_missing_reason"] == "no_vendor_verdicts"
