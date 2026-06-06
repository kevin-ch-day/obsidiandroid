from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.diagnostics import cohort_persistence

pytestmark = pytest.mark.contract


def test_export_cohort_membership_snapshot_writes_legacy_and_run_scoped(tmp_path: Path) -> None:
    samples_df = pd.DataFrame(
        {
            "sample_id": [2, 1],
            "family_id": [10, 9],
            "family_canonical": ["Beta", "Alpha"],
            "type_slug": ["rat", "banker"],
        }
    )

    paths = cohort_persistence.export_cohort_membership_snapshot(
        diagnostics_dir=tmp_path,
        run_id="run_persist",
        samples_df=samples_df,
    )

    assert (tmp_path / "cohort_membership.csv").is_file()
    assert (tmp_path / "cohort_membership_run_persist.csv").is_file()
    assert len(paths) >= 2
    legacy = pd.read_csv(tmp_path / "cohort_membership.csv")
    scoped = pd.read_csv(tmp_path / "cohort_membership_run_persist.csv")
    assert list(legacy["sample_id"]) == [1, 2]
    assert list(scoped["sample_id"]) == [1, 2]


def test_resolve_effective_samples_df_prefers_runtime_frame(tmp_path: Path) -> None:
    runtime = pd.DataFrame({"sample_id": [1], "family_canonical": ["A"]})
    (tmp_path / "cohort_membership.csv").write_text("sample_id,family_canonical\n9,Z\n", encoding="utf-8")

    resolved = cohort_persistence.resolve_effective_samples_df(tmp_path, "run_x", runtime)

    assert resolved is not None
    assert int(resolved["sample_id"].iloc[0]) == 1


def test_resolve_effective_samples_df_reloads_run_scoped_membership(tmp_path: Path) -> None:
    (tmp_path / "cohort_membership_run_reload.csv").write_text(
        "sample_id,family_canonical,type_slug\n7,Gamma,spy\n",
        encoding="utf-8",
    )

    resolved = cohort_persistence.resolve_effective_samples_df(tmp_path, "run_reload", None)

    assert resolved is not None
    assert len(resolved) == 1
    assert resolved["family_canonical"].iloc[0] == "Gamma"
