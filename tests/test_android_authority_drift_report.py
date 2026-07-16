from __future__ import annotations

from pathlib import Path

import json
import pandas as pd

from config import app_config
from obsidiandroid.diagnostics import android_authority_drift_report


def test_build_android_authority_drift_payload_groups_families_types_and_batches() -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "family_canonical": ["FamA", "FamA", "FamB"],
            "type_slug": ["banker", "banker", "rat"],
            "source_batch_label": ["batch_a", "batch_a", "batch_b"],
            "analysis_lane": ["android_artifact", "windows_targeting_non_windows", "android_artifact"],
            "payload_target_platform": ["android", "windows", "android"],
            "sample_label_kind": ["family_or_common_name", "hash_like", "unclassified"],
            "vt_family_token": ["fama", "fama", "famb"],
            "family_label_raw": ["FamA", "WrongA", ""],
        }
    )

    payload = android_authority_drift_report.build_android_authority_drift_payload(df, top_n=10)

    assert payload["total_rows"] == 3
    assert payload["issue_rows"] == 2
    rows = payload["grouped_rows"]
    family_rows = [row for row in rows if row["scope"] == "family_canonical"]
    type_rows = [row for row in rows if row["scope"] == "type_slug"]
    batch_rows = [row for row in rows if row["scope"] == "source_batch_label"]
    assert family_rows[0]["group_value"] == "FamA"
    assert family_rows[0]["issue_events"] >= 3
    assert type_rows[0]["group_value"] == "banker"
    assert batch_rows[0]["group_value"] == "batch_a"


def test_export_android_authority_drift_reports_writes_json_csv_and_md(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1],
            "family_canonical": ["FamA"],
            "type_slug": ["banker"],
            "source_batch_label": ["batch_a"],
            "analysis_lane": ["windows_targeting_non_windows"],
            "payload_target_platform": ["windows"],
            "sample_label_kind": ["hash_like"],
            "vt_family_token": ["fama"],
            "family_label_raw": ["WrongA"],
        }
    )

    paths = android_authority_drift_report.export_android_authority_drift_reports(
        diagnostics_dir=tmp_path,
        run_id="run_unit",
        samples_df=df,
    )

    assert len(paths) == 3
    json_blob = json.loads((tmp_path / "android_authority_drift_run_unit.json").read_text(encoding="utf-8"))
    assert json_blob["issue_rows"] == 1
    md_blob = (tmp_path / "android_authority_drift_run_unit.md").read_text(encoding="utf-8")
    assert "# Android Authority Drift" in md_blob
    assert "## family_canonical" in md_blob


def test_build_android_authority_drift_payload_handles_clean_cohort() -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "family_canonical": ["FamA", "FamB"],
            "type_slug": ["banker", "rat"],
            "source_batch_label": ["batch_a", "batch_b"],
            "analysis_lane": ["android_artifact", "android_artifact"],
            "payload_target_platform": ["android", "android"],
            "sample_label_kind": ["family_or_common_name", "family_or_common_name"],
            "vt_family_token": ["fama", "famb"],
            "family_label_raw": ["FamA", "FamB"],
        }
    )

    payload = android_authority_drift_report.build_android_authority_drift_payload(df, top_n=10)

    assert payload["total_rows"] == 2
    assert payload["issue_rows"] == 0
    assert payload["grouped_rows"] == []


def test_authority_drift_does_not_count_alias_or_textual_null_as_family_conflict() -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "family_canonical": ["SpyLoan", "nan"],
            "type_slug": ["banker", "banker"],
            "source_batch_label": ["batch_a", "batch_b"],
            "analysis_lane": ["android_artifact", "android_artifact"],
            "payload_target_platform": ["android", "android"],
            "sample_label_kind": ["family_or_common_name", "family_or_common_name"],
            "vt_family_token": ["blackloan", "possiblefamily"],
            "family_label_raw": ["BlackLoan", "n/a"],
        }
    )

    payload = android_authority_drift_report.build_android_authority_drift_payload(df, top_n=10)

    assert payload["issue_rows"] == 1
    family_rows = [row for row in payload["grouped_rows"] if row["scope"] == "family_canonical"]
    assert family_rows[0]["group_value"] == "<blank>"
    assert family_rows[0]["raw_family_vs_canonical_conflict_rows"] == 0


def test_export_android_authority_drift_reports_skips_empty_csv_in_compact_mode(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", False, raising=False)
    df = pd.DataFrame(
        {
            "sample_id": [1],
            "family_canonical": ["FamA"],
            "type_slug": ["banker"],
            "source_batch_label": ["batch_a"],
            "analysis_lane": ["android_artifact"],
            "payload_target_platform": ["android"],
            "sample_label_kind": ["family_or_common_name"],
            "vt_family_token": [""],
            "family_label_raw": ["FamA"],
        }
    )

    paths = android_authority_drift_report.export_android_authority_drift_reports(
        diagnostics_dir=tmp_path,
        run_id="run_clean",
        samples_df=df,
    )

    assert len(paths) == 2
    assert str(tmp_path / "android_authority_drift_run_clean.json") in paths
    assert str(tmp_path / "android_authority_drift_run_clean.md") in paths
    assert not (tmp_path / "android_authority_drift_groups_run_clean.csv").exists()
