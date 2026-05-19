"""Tests for feature enrichment stage helpers."""

import json

import pandas as pd
from config import app_config

from obsidiandroid.pipeline import stage_feature_enrichment


def test_merge_sample_metadata_features_disabled_returns_original() -> None:
    """Disabled metadata flag should return the enrichment frame unchanged when no permissions."""
    existing_df = pd.DataFrame({"sample_id": [1], "existing": [1.0]})
    samples_df = pd.DataFrame({"sample_id": [1], "permissions": [2]})

    result = stage_feature_enrichment.merge_sample_metadata_features(
        extra_features_df=existing_df,
        samples_df=samples_df,
        feature_flags={"enable_sample_metadata_features": False},
    )

    assert result is existing_df


def test_merge_sample_metadata_features_disabled_still_fuses_permissions() -> None:
    """When catalog metadata features are disabled, PI permission columns must still merge."""
    existing_df = pd.DataFrame({"sample_id": [10, 20], "existing": [1.0, 2.0]})
    samples_df = pd.DataFrame({"sample_id": [10, 20], "permissions": [1, 2]})
    perm = pd.DataFrame({"sample_id": [10, 20], "perm__android_permission_internet": [1, 0]})

    result = stage_feature_enrichment.merge_sample_metadata_features(
        extra_features_df=existing_df,
        samples_df=samples_df,
        feature_flags={"enable_sample_metadata_features": False},
        permission_features_df=perm,
    )

    assert isinstance(result, pd.DataFrame)
    assert "perm__android_permission_internet" in result.columns
    assert result["perm__android_permission_internet"].tolist() == [1, 0]


def test_merge_sample_metadata_features_merges_expected_columns() -> None:
    """Enabled flag should merge metadata-derived columns by sample id."""
    existing_df = pd.DataFrame({"sample_id": [1, 2], "existing": [1.0, 2.0]})
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "permissions": [10, 20],
            "vt_tags": ["banker,overlay", ""],
        }
    )

    result = stage_feature_enrichment.merge_sample_metadata_features(
        extra_features_df=existing_df,
        samples_df=samples_df,
        feature_flags={"enable_sample_metadata_features": True},
    )

    assert isinstance(result, pd.DataFrame)
    assert "meta__permissions" in result.columns
    assert "meta__vt_tag_count" in result.columns
    assert result.shape[0] == 2


def test_merge_sample_metadata_features_dedupes_before_permission_fuse() -> None:
    """Duplicate sample_id rows in the AV enrichment base must not multiply permission joins."""
    base = pd.DataFrame(
        {
            "sample_id": [1, 1, 2],
            "existing": [1.0, 9.0, 2.0],
        }
    )
    samples_df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "permissions": [3, 4],
            "vt_tags": ["a", ""],
        }
    )
    perm = pd.DataFrame({"sample_id": [1, 2], "perm__x": [1, 1]})

    result = stage_feature_enrichment.merge_sample_metadata_features(
        extra_features_df=base,
        samples_df=samples_df,
        feature_flags={"enable_sample_metadata_features": True},
        permission_features_df=perm,
    )
    assert result is not None
    assert len(result) == 2
    assert result["perm__x"].tolist() == [1, 1]


def test_permission_fuse_audit_run_scoped_uses_global_latest(monkeypatch, tmp_path) -> None:
    output_root = tmp_path / "output"
    diagnostics_dir = output_root / "runs" / "rid" / "diagnostics"
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "rid", raising=False)

    stage_feature_enrichment._write_permission_fuse_audit({"run_id": "rid", "rows": 2})  # pylint: disable=protected-access

    assert (diagnostics_dir / "permission_fuse_audit_rid.json").exists()
    assert not (diagnostics_dir / "permission_fuse_audit.latest.json").exists()
    payload = json.loads((output_root / "diagnostics" / "permission_fuse_audit.latest.json").read_text(encoding="utf-8"))
    assert payload["rows"] == 2


def test_duplicate_pre_fuse_report_run_scoped_uses_global_latest(monkeypatch, tmp_path) -> None:
    output_root = tmp_path / "output"
    diagnostics_dir = output_root / "runs" / "rid" / "diagnostics"
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "rid", raising=False)
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_MODE", False, raising=False)

    merged = pd.DataFrame({"sample_id": [1, 1], "meta__permissions": [1, 2]})
    stage_feature_enrichment._maybe_export_duplicate_sample_id_pre_fuse(merged, 1)  # pylint: disable=protected-access

    assert (diagnostics_dir / "duplicate_sample_id_pre_fuse_rid.csv").exists()
    assert not (diagnostics_dir / "duplicate_sample_id_pre_fuse.latest.csv").exists()
    assert (output_root / "diagnostics" / "duplicate_sample_id_pre_fuse.latest.csv").exists()
