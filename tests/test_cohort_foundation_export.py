"""Tests for cohort foundation diagnostics export."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analysis.diagnostics.cohort_foundation_export import (
    build_cohort_foundation_payload,
    export_cohort_foundation_bundle,
)
from analysis.diagnostics.cohort_vocabulary import (
    KEY_COHORT_PREPARED_ROW_COUNT,
    KEY_COHORT_SQL_SCOPE_ROW_COUNT,
)


def test_export_cohort_foundation_bundle_writes_four_artifacts(tmp_path: Path) -> None:
    diagnostics_dir = tmp_path / "diagnostics"
    df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "sha256": ["a" * 64, "b" * 64],
            "family_canonical": ["f1", "f2"],
            "type_slug": ["trojan", "trojan"],
            "android_package_name": ["com.example", ""],
            "vt_first_submission_date": [
                pd.Timestamp("2020-01-01", tz="UTC"),
                pd.Timestamp("2020-01-02", tz="UTC"),
            ],
        }
    )
    gate_stats = {
        "total_candidates": 50,
        "governed_cohort_count": 2,
        "excluded_unmapped_family": 3,
        "excluded_unknown_type_slug": 0,
        "excluded_missing_sha256": 1,
        "excluded_missing_hash_registry": 0,
        "excluded_missing_package_name": 0,
        "excluded_low_support": 0,
    }
    profile = {
        "profile_id": "unit_cohort",
        "cohort_gates": {"min_samples_per_family": 3},
    }
    time_contract = {"start_utc": "2019-01-01", "end_utc": None, "require_effective_first_seen": True}
    paths = export_cohort_foundation_bundle(
        diagnostics_dir=diagnostics_dir,
        run_id="run_unit",
        profile_id="unit_cohort",
        profile=profile,
        gate_stats=gate_stats,
        samples_df=df,
        time_contract=time_contract,
        type_slug=None,
        min_samples_per_family_sql=None,
        configured_min_samples_per_family=3,
    )
    assert len(paths) == 4
    assert (diagnostics_dir / "cohort_foundation.json").exists()
    assert (diagnostics_dir / "cohort_foundation.md").exists()
    assert (diagnostics_dir / "cohort_foundation_counts.csv").exists()
    assert (diagnostics_dir / "cohort_foundation_schema.csv").exists()
    blob = json.loads((diagnostics_dir / "cohort_foundation.json").read_text(encoding="utf-8"))
    assert blob["run_id"] == "run_unit"
    assert blob[KEY_COHORT_SQL_SCOPE_ROW_COUNT] == 50
    assert blob[KEY_COHORT_PREPARED_ROW_COUNT] == 2
    assert blob["gate_stats"]["total_candidates"] == 50
    assert blob["loaded_dataframe"]["rows"] == 2


def test_interim_warning_when_upstream_expected_min_exceeded() -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1],
            "sha256": ["c" * 64],
            "family_canonical": ["fam"],
            "type_slug": ["trojan"],
        }
    )
    profile = {
        "profile_id": "research_all_malicious",
        "cohort_gates": {"upstream_expected_min_gate_total": 99999},
    }
    gate_stats = {"total_candidates": 10, "governed_cohort_count": 1}
    payload = build_cohort_foundation_payload(
        run_id="r1",
        profile_id="research_all_malicious",
        profile=profile,
        gate_stats=gate_stats,
        samples_df=df,
        time_contract={},
        type_slug=None,
        min_samples_per_family_sql=None,
        configured_min_samples_per_family=3,
    )
    warns = payload.get("interim_rebuild_warnings") or []
    assert any("Erebus" in w for w in warns)
