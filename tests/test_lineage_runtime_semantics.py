"""Fast tests for lineage CSV semantics (unset vs empty runtime id sets)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.diagnostics import feature_build_coverage_export as fbc
from config import app_config


@pytest.fixture
def _reset_lineage_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    for attr in (
        "RUNTIME_VENDOR_MERGE_SAMPLE_IDS",
        "RUNTIME_PERMISSION_FRAME_SAMPLE_IDS",
        "RUNTIME_FUSED_MATRIX_SAMPLE_IDS",
        "RUNTIME_ALIGNED_SUPERVISED_SAMPLE_IDS",
        "RUNTIME_POST_FAMILY_SUPPORT_TRAINABLE_SAMPLE_IDS",
    ):
        monkeypatch.delattr(app_config, attr, raising=False)


def test_sample_stage_lineage_unknown_vendor_when_attr_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _reset_lineage_runtime
) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_FUSED_MATRIX_SAMPLE_IDS", [10], raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ALIGNED_SUPERVISED_SAMPLE_IDS", [10], raising=False)
    monkeypatch.setattr(
        app_config, "RUNTIME_POST_FAMILY_SUPPORT_TRAINABLE_SAMPLE_IDS", [10], raising=False
    )
    # RUNTIME_VENDOR_MERGE_SAMPLE_IDS intentionally unset -> None
    out = fbc.export_sample_stage_lineage_audit(
        cohort_sample_ids=[10],
        output_dir=tmp_path,
        run_id="sem_u1",
        enabled=True,
    )
    assert out is not None
    df = pd.read_csv(out)
    assert pd.isna(df.loc[0, "in_vendor_merge"])
    assert bool(df.loc[0, "in_fused_feature_matrix"]) is True


def test_sample_stage_lineage_vendor_false_when_empty_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _reset_lineage_runtime
) -> None:
    monkeypatch.setattr(app_config, "RUNTIME_VENDOR_MERGE_SAMPLE_IDS", [], raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_FUSED_MATRIX_SAMPLE_IDS", [10], raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_ALIGNED_SUPERVISED_SAMPLE_IDS", [10], raising=False)
    monkeypatch.setattr(
        app_config, "RUNTIME_POST_FAMILY_SUPPORT_TRAINABLE_SAMPLE_IDS", [10], raising=False
    )
    out = fbc.export_sample_stage_lineage_audit(
        cohort_sample_ids=[10],
        output_dir=tmp_path,
        run_id="sem_u2",
        enabled=True,
    )
    assert out is not None
    df = pd.read_csv(out)
    assert bool(df.loc[0, "in_vendor_merge"]) is False
