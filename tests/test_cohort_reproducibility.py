import pandas as pd
import pytest

from config import app_config
from utils import cohort_reproducibility as cr


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
