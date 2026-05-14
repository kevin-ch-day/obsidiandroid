"""Tests for analysis snapshot export hygiene (run-scoped vs global mirror)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from config import app_config
from obsidiandroid.governance import cohort_reproducibility as cr


def test_export_analysis_snapshot_mirrors_global_latest_when_under_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
