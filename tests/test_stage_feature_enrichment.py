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


def test_merge_sample_metadata_fuses_permissions_by_sample_id_not_position() -> None:
    """Permission columns must attach to matching ``sample_id`` after metadata merge + dedupe."""
    samples_df = pd.DataFrame(
        {
            "sample_id": [495, 579, 657],
            "permissions": [12, 0, 8],
        }
    )
    enriched = pd.DataFrame(
        {
            "sample_id": [495, 579, 657],
            "malicious_ratio": [0.4, 0.5, 0.6],
        }
    )
    permission_features_df = pd.DataFrame(
        {
            "sample_id": [495, 657],
            "perm__android_permission_internet": [1, 1],
            "perm__android_permission_wake_lock": [1, 0],
            "perm__total_count": [4, 2],
        }
    )
    flags = {"enable_sample_metadata_features": True}
    merged = stage_feature_enrichment.merge_sample_metadata_features(
        enriched,
        samples_df,
        flags,
        permission_features_df,
    )
    assert merged is not None
    assert not merged.empty
    assert sorted(merged["sample_id"].tolist()) == [495, 579, 657]
    assert int(merged.loc[merged["sample_id"] == 495, "perm__android_permission_internet"].iloc[0]) == 1
    assert int(merged.loc[merged["sample_id"] == 657, "perm__android_permission_internet"].iloc[0]) == 1
    wake_579 = int(merged.loc[merged["sample_id"] == 579, "perm__android_permission_wake_lock"].iloc[0])
    assert wake_579 == 0
    assert int(merged.loc[merged["sample_id"] == 579, "perm__total_count"].iloc[0]) == 0


def test_merge_sample_metadata_coerces_string_sample_id_for_permission_join() -> None:
    """String ``sample_id`` values on the AV enrichment base must still join PI permission rows."""
    samples_df = pd.DataFrame({"sample_id": [495, 657], "permissions": [1, 2]})
    enriched = pd.DataFrame({"sample_id": ["495", "657"], "malicious_ratio": [0.1, 0.2]})
    permission_features_df = pd.DataFrame(
        {
            "sample_id": [495, 657],
            "perm__android_permission_internet": [1, 1],
        }
    )
    merged = stage_feature_enrichment.merge_sample_metadata_features(
        enriched,
        samples_df,
        {"enable_sample_metadata_features": True},
        permission_features_df,
    )
    assert merged is not None
    assert merged["sample_id"].dtype == "int64"
    assert int(merged.loc[merged["sample_id"] == 495, "perm__android_permission_internet"].iloc[0]) == 1


def test_merge_sample_metadata_drops_overlay_rows_before_permission_fuse() -> None:
    """Rows without a numeric catalog ``sample_id`` must not dilute joins."""
    samples_df = pd.DataFrame({"sample_id": [495, 657], "permissions": [3, 4]})
    enriched = pd.DataFrame(
        {
            "sample_id": [495, float("nan"), 657, float("nan")],
            "malicious_ratio": [0.1, 9.9, 0.2, 8.8],
        }
    )
    permission_features_df = pd.DataFrame(
        {
            "sample_id": [495, 657],
            "perm__android_permission_internet": [1, 1],
        }
    )
    merged = stage_feature_enrichment.merge_sample_metadata_features(
        enriched,
        samples_df,
        {"enable_sample_metadata_features": True},
        permission_features_df,
    )
    assert merged is not None
    assert set(merged["sample_id"].tolist()) == {495, 657}
    assert int(merged.loc[merged["sample_id"] == 495, "perm__android_permission_internet"].iloc[0]) == 1


def test_merge_extra_features_aligns_perm_columns_by_encoded_index() -> None:
    """End-to-end: encoded vendor matrix index ids receive ``perm__`` values from enrichment by ``sample_id``."""
    from obsidiandroid.features import feature_vector_builder
    from obsidiandroid.features.feature_encoder import encode_features

    vendor_merged = pd.DataFrame(
        {
            "sample_id": [495, 579, 657],
            "parsed_family_vendorx": ["a", "b", "c"],
        }
    )
    encoded = encode_features(vendor_merged, encoding="category", verbose=False, skip_numeric=True)
    samples_df = pd.DataFrame({"sample_id": [495, 579, 657], "permissions": [2, 2, 2]})
    enriched = pd.DataFrame({"sample_id": [495, 579, 657], "malicious_ratio": [0.3, 0.4, 0.5]})
    permission_features_df = pd.DataFrame(
        {
            "sample_id": [495, 657],
            "perm__android_permission_internet": [1, 1],
            "perm__total_count": [3, 5],
        }
    )
    extra = stage_feature_enrichment.merge_sample_metadata_features(
        enriched,
        samples_df,
        {"enable_sample_metadata_features": True},
        permission_features_df,
    )
    out, _maps = feature_vector_builder._merge_extra_features(encoded, extra, verbose=False)
    internet_cols = [c for c in out.columns if "internet" in str(c).lower() and str(c).startswith("perm__")]
    assert internet_cols, f"expected perm internet column, got {out.columns.tolist()}"
    col = internet_cols[0]
    assert int(out.loc[495, col]) > 0
    assert int(out.loc[657, col]) > 0
    assert int(out.loc[579, col]) == 0
