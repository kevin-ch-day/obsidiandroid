"""Tests for immutable lock-first paper cohort materialization."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.governance import locked_paper_materialization
from obsidiandroid.governance.cohort_lock_manifest import compute_cohort_hash_from_member_list


def _make_manifest(baseline_dir: Path, *, taxonomy_hash: str = "taxhash") -> Path:
    member_path = baseline_dir / "members.csv"
    manifest_path = baseline_dir / "cohort_lock_manifest.json"
    members = pd.DataFrame({"sample_id": [1, 2, 3]})
    members.to_csv(member_path, index=False)
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "lock_version": "v1",
                "profile_id": "malicious_temporal_stability_locked",
                "contract_id": "locked_contract",
                "canonical_historical_run_id": "",
                "created_at_utc": "2026-05-31T00:00:00Z",
                "member_list_path": "members.csv",
                "sample_count": 3,
                "family_count": 2,
                "type_count": 2,
                "cohort_hash": compute_cohort_hash_from_member_list(members),
                "taxonomy_hash": taxonomy_hash,
                "sql_profile_version": "test",
                "profile_version": "test",
                "time_window": {
                    "start_utc": "2020-01-01T00:00:00Z",
                    "end_utc": "2026-01-01T00:00:00Z",
                    "window_semantics": "start_inclusive_end_exclusive",
                    "timestamp_field": "effective_first_seen_at_utc",
                    "require_effective_first_seen": True,
                    "fallback_order": ["vt_first_seen_itw_date", "vt_first_submission_at_utc"],
                },
                "source_artifacts": {},
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_materialize_locked_paper_cohort_recovers_members_excluded_by_current_sql(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Locked paper materialization should recover members from a broad fetch before live SQL gates."""
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    manifest_path = _make_manifest(baseline_dir)
    broad_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "sha256": ["a" * 64, "b" * 64, "c" * 64],
            "family_canonical": ["FamA", "FamA", "FamB"],
            "family_id": [10, 10, 20],
            "type_slug": ["banker", "banker", "spyware"],
            "permissions": ["p1", "p2", ""],
            "vt_scan_status": ["complete", "complete", "complete"],
            "vt_malicious_count": [5, 6, 7],
            "vt_suspicious_count": [0, 0, 0],
            "vt_undetected_count": [1, 1, 1],
            "vt_harmless_count": [0, 0, 0],
            "effective_first_seen_at_utc": [
                "2020-02-01T00:00:00Z",
                "2021-02-01T00:00:00Z",
                "2026-02-01T00:00:00Z",
            ],
            "vt_first_seen_itw_date": ["2020-02-01", "2021-02-01", "2026-02-01"],
            "vt_first_submission_date": ["2020-02-02", "2021-02-02", "2026-02-02"],
        }
    )
    current_fetch_df = broad_df[broad_df["sample_id"].isin([1, 2])].copy()

    monkeypatch.setattr(
        locked_paper_materialization.db_sample_metadata_queries,
        "load_samples_by_type",
        lambda **_: broad_df.copy(),
    )

    result = locked_paper_materialization.materialize_locked_paper_cohort(
        profile={
            "profile_id": "malicious_temporal_stability_locked",
            "paper_lock": {
                "cohort_lock_manifest_file": str(manifest_path),
                "sample_id_lock_source": str(baseline_dir / "members.csv"),
            },
        },
        run_id="run123",
        current_fetch_df=current_fetch_df,
        snapshot_lock_file=str(baseline_dir / "members.csv"),
        diagnostics_dir=tmp_path / "diag",
    )

    assert result.samples_df["sample_id"].tolist() == [1, 2, 3]
    missing_df = pd.read_csv(result.missing_locked_members_path)
    assert missing_df["sample_id"].tolist() == [3]
    row = missing_df.iloc[0].to_dict()
    assert bool(row["excluded_by_current_fetch_sql"]) is True
    assert bool(row["outside_time_window"]) is True
    assert row["missing_reason"] == "outside_time_window"
    drift_summary = json.loads(Path(result.label_drift_summary_path).read_text(encoding="utf-8"))
    assert drift_summary["archived_label_snapshot_available"] is False
    assert drift_summary["currently_missing_from_current_fetch_sql_count"] == 1


def test_materialize_locked_paper_cohort_fails_when_lock_cannot_be_fully_rejoined(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Immutable paper lock reproduction must fail if locked members are absent from the broad catalog."""
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    manifest_path = _make_manifest(baseline_dir)
    broad_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "sha256": ["a" * 64, "b" * 64],
            "family_canonical": ["FamA", "FamA"],
            "family_id": [10, 10],
            "type_slug": ["banker", "banker"],
            "permissions": ["p1", "p2"],
            "vt_scan_status": ["complete", "complete"],
            "vt_malicious_count": [5, 6],
            "vt_suspicious_count": [0, 0],
            "vt_undetected_count": [1, 1],
            "vt_harmless_count": [0, 0],
            "effective_first_seen_at_utc": [
                "2020-02-01T00:00:00Z",
                "2021-02-01T00:00:00Z",
            ],
            "vt_first_seen_itw_date": ["2020-02-01", "2021-02-01"],
            "vt_first_submission_date": ["2020-02-02", "2021-02-02"],
        }
    )

    monkeypatch.setattr(
        locked_paper_materialization.db_sample_metadata_queries,
        "load_samples_by_type",
        lambda **_: broad_df.copy(),
    )

    diagnostics_dir = tmp_path / "diag"
    with pytest.raises(ValueError, match="Failed to fully materialize immutable paper lock"):
        locked_paper_materialization.materialize_locked_paper_cohort(
            profile={
                "profile_id": "malicious_temporal_stability_locked",
                "paper_lock": {
                    "cohort_lock_manifest_file": str(manifest_path),
                    "sample_id_lock_source": str(baseline_dir / "members.csv"),
                },
            },
            run_id="run123",
            current_fetch_df=broad_df.copy(),
            snapshot_lock_file=str(baseline_dir / "members.csv"),
            diagnostics_dir=diagnostics_dir,
        )

    missing_df = pd.read_csv(diagnostics_dir / "missing_locked_members.csv")
    assert missing_df["sample_id"].tolist() == [3]
    row = missing_df.iloc[0].to_dict()
    assert bool(row["missing_from_catalog"]) is True
    assert row["missing_reason"] == "missing_from_catalog"


def test_materialize_locked_paper_cohort_applies_archived_labels_when_available(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Archived paper labels should replace current live labels in strict locked materialization."""
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    label_snapshot = baseline_dir / "label_snapshot.csv"
    label_snapshot.write_text(
        "sample_id,sha256,family_id,family_canonical,type_slug\n"
        "1," + "a" * 64 + ",11,ArchivedFamA,banker\n"
        "2," + "b" * 64 + ",12,ArchivedFamB,spyware\n"
        "3," + "c" * 64 + ",13,ArchivedFamC,stealer\n",
        encoding="utf-8",
    )
    manifest_path = _make_manifest(baseline_dir, taxonomy_hash="unused-for-helper")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_artifacts"]["label_snapshot_csv"] = "label_snapshot.csv"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    broad_df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "sha256": ["a" * 64, "b" * 64, "c" * 64],
            "family_canonical": ["LiveA", "LiveB", "LiveC"],
            "family_id": [100, 200, 300],
            "type_slug": ["rat", "rat", "rat"],
            "permissions": ["p1", "p2", "p3"],
            "vt_scan_status": ["complete", "complete", "complete"],
            "vt_malicious_count": [5, 6, 7],
            "vt_suspicious_count": [0, 0, 0],
            "vt_undetected_count": [1, 1, 1],
            "vt_harmless_count": [0, 0, 0],
            "effective_first_seen_at_utc": ["2020-02-01T00:00:00Z"] * 3,
            "vt_first_seen_itw_date": ["2020-02-01"] * 3,
            "vt_first_submission_date": ["2020-02-02"] * 3,
        }
    )

    monkeypatch.setattr(
        locked_paper_materialization.db_sample_metadata_queries,
        "load_samples_by_type",
        lambda **_: broad_df.copy(),
    )

    result = locked_paper_materialization.materialize_locked_paper_cohort(
        profile={
            "profile_id": "malicious_temporal_stability_locked",
            "paper_lock": {
                "cohort_lock_manifest_file": str(manifest_path),
                "sample_id_lock_source": str(baseline_dir / "members.csv"),
            },
        },
        run_id="run123",
        current_fetch_df=broad_df.copy(),
        snapshot_lock_file=str(baseline_dir / "members.csv"),
        diagnostics_dir=tmp_path / "diag",
    )

    assert result.archived_label_snapshot_available is True
    out = result.samples_df.sort_values("sample_id", kind="mergesort").reset_index(drop=True)
    assert out["family_canonical"].tolist() == ["ArchivedFamA", "ArchivedFamB", "ArchivedFamC"]
    assert out["type_slug"].tolist() == ["banker", "spyware", "stealer"]


def test_load_archived_label_snapshot_from_warehouse_uses_archive_fallback(monkeypatch) -> None:
    """Warehouse archive table should be used when the live snapshot table is empty."""
    empty_df = pd.DataFrame(columns=["sample_id", "sha256", "family_id", "family_canonical", "type_slug"])
    archive_df = pd.DataFrame(
        {
            "sample_id": [1],
            "sha256": ["a" * 64],
            "family_id": [10],
            "family_canonical": ["FamA"],
            "type_slug": ["banker"],
        }
    )

    class _Conn:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        locked_paper_materialization.db_engine,
        "database_connection",
        lambda: _Conn(),
    )

    def _fake_read_sql_query(query, conn, params=None):  # pylint: disable=unused-argument
        if "analysis_snapshot_sample_archive" in query:
            return archive_df.copy()
        return empty_df.copy()

    monkeypatch.setattr(
        locked_paper_materialization.pd,
        "read_sql_query",
        _fake_read_sql_query,
    )

    loaded, source = locked_paper_materialization._load_archived_label_snapshot_from_warehouse("rid")  # pylint: disable=protected-access

    assert source == "results_warehouse_analysis_snapshot_sample_archive"
    assert loaded is not None
    assert loaded["sample_id"].tolist() == [1]
