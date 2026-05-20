import pandas as pd
import pytest

from config import app_config
import obsidiandroid.governance.cohort_reproducibility as cr


def test_apply_cohort_lock_filters_to_matching_ids(tmp_path):
    samples_df = pd.DataFrame(
        {
            "sample_id": [100, 200, 300],
            "family_name": ["A", "B", "C"],
        }
    )
    lock_file = tmp_path / "cohort.lock.csv"
    pd.DataFrame({"sample_id": [300, 100]}).to_csv(lock_file, index=False)

    filtered = cr.apply_cohort_lock(samples_df, str(lock_file))

    assert filtered["sample_id"].tolist() == [100, 300]
    assert filtered.attrs["snapshot_lock"]["status"] == "matched"
    assert filtered.attrs["snapshot_lock"]["applied"] is True


def test_apply_cohort_lock_uses_live_cohort_when_missing(tmp_path):
    samples_df = pd.DataFrame({"sample_id": [2, 1]})
    filtered = cr.apply_cohort_lock(samples_df, str(tmp_path / "missing.csv"))
    assert filtered["sample_id"].tolist() == [1, 2]


def test_apply_analysis_snapshot_lock_fails_closed_when_requested(tmp_path) -> None:
    samples_df = pd.DataFrame({"sample_id": [2, 1]})

    with pytest.raises(ValueError, match="Lock file not found"):
        cr.apply_analysis_snapshot_lock(
            samples_df,
            str(tmp_path / "missing.csv"),
            fail_closed=True,
        )


def test_apply_cohort_lock_fails_closed_in_strict_evidence_mode(
    monkeypatch,
    tmp_path,
) -> None:
    samples_df = pd.DataFrame({"sample_id": [2, 1]})
    monkeypatch.setattr(app_config, "REQUIRE_SNAPSHOT_LOCK_IN_EVIDENCE_MODE", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", True, raising=False)

    with pytest.raises(ValueError, match="Lock file not found"):
        cr.apply_cohort_lock(samples_df, str(tmp_path / "missing.csv"))


def test_export_cohort_snapshot_writes_hash_and_ids(tmp_path):
    samples_df = pd.DataFrame({"sample_id": [3, 1, 2]})
    snapshot_file = tmp_path / "cohort.latest.csv"
    meta_file = tmp_path / "cohort.latest.meta.txt"

    cr.export_cohort_snapshot(samples_df, str(snapshot_file), str(meta_file))

    exported = pd.read_csv(snapshot_file)
    meta_text = meta_file.read_text(encoding="utf-8")

    assert exported["sample_id"].tolist() == [1, 2, 3]
    assert "sample_count=3" in meta_text
    assert "sha256=" in meta_text


def test_export_analysis_snapshot_mirrors_global_latest_when_under_runs(
    tmp_path,
    monkeypatch,
) -> None:
    """Under ``runs/<id>/diagnostics``, snapshot CSV/meta should mirror to global diagnostics."""
    monkeypatch.setattr(app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(app_config, "SUPPRESS_LATEST_DUPLICATES_IN_RUN_DIRS", True, raising=False)

    diag = tmp_path / "output" / "runs" / "rid1" / "diagnostics"
    snap = diag / "analysis_snapshot_rid1.csv"
    meta = diag / "analysis_snapshot_rid1.meta.txt"

    sha_a = "a" * 64
    sha_f = "f" * 64
    df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "sha256": [sha_a, sha_f],
            "family_id": [1, 2],
            "family_canonical": ["A", "B"],
            "type_slug": ["banker", "banker"],
            "vt_first_seen_itw_date": [pd.NaT, pd.NaT],
            "vt_first_submission_at_utc": ["2020-01-01T00:00:00Z", "2020-01-02T00:00:00Z"],
        }
    )

    cr.export_analysis_snapshot(df, str(snap), str(meta), conflict_file=None, run_id="rid1")

    assert snap.is_file()
    assert not (diag / "analysis_snapshot.latest.csv").exists()
    glob_latest = tmp_path / "output" / "diagnostics" / "analysis_snapshot.latest.csv"
    assert glob_latest.is_file()
    glob_meta = tmp_path / "output" / "diagnostics" / "analysis_snapshot.latest.meta.txt"
    assert glob_meta.is_file()
