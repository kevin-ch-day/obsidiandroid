"""Tests for vendor feature vector builder helper behaviors."""

from __future__ import annotations

import pandas as pd
from pathlib import Path

from obsidiandroid.features import feature_vector_builder
from config import app_config


def test_filter_vendors_with_parsed_data_keeps_available_only() -> None:
    """Helper should keep only vendors present in parsed vendor payload."""
    parsed = {"lionic": {}, "tencent": {}, "drweb": {}}
    selected = ["lionic", "missing_vendor", "drweb"]
    filtered = feature_vector_builder._filter_vendors_with_parsed_data(  # pylint: disable=protected-access
        parsed_vendor_data=parsed,
        vendor_list=selected,
        verbose=False,
    )
    assert filtered == ["lionic", "drweb"]


def test_filter_vendors_with_parsed_data_handles_empty() -> None:
    """Helper should return empty list for empty/invalid parsed data."""
    filtered = feature_vector_builder._filter_vendors_with_parsed_data(  # pylint: disable=protected-access
        parsed_vendor_data={},
        vendor_list=["a", "b"],
        verbose=False,
    )
    assert filtered == []


def test_ensure_min_vendor_selection_no_fallback_in_paper_mode(monkeypatch) -> None:
    """Paper mode must not widen vendor set via fallback selection."""
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", True, raising=False)
    result = feature_vector_builder._ensure_min_vendor_selection(  # pylint: disable=protected-access
        weights_df=None,
        selected_vendors=["a", "b"],
        min_required=4,
        top_k=8,
        score_preference="Leakage Safe Score",
        exclude_categories=[],
        verbose=False,
    )
    assert result == ["a", "b"]


def test_ensure_min_vendor_selection_requires_explicit_fallback(monkeypatch) -> None:
    """Non-paper runs should not widen vendor selection unless fallback is explicitly enabled."""
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False, raising=False)
    monkeypatch.setattr(app_config, "ALLOW_VENDOR_FALLBACK_FOR_WIDTH", False, raising=False)
    result = feature_vector_builder._ensure_min_vendor_selection(  # pylint: disable=protected-access
        weights_df=pd.DataFrame({"Vendor": ["a", "b"], "Leakage Safe Score": [0.9, 0.8]}),
        selected_vendors=["a"],
        min_required=3,
        top_k=5,
        score_preference="Leakage Safe Score",
        exclude_categories=[],
        verbose=False,
    )
    assert result == ["a"]


def test_build_feature_vector_recovers_when_parser_gating_selects_zero(monkeypatch) -> None:
    """Builder should attempt fallback recovery when initial gated selection is empty."""
    monkeypatch.setattr(app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", False, raising=False)
    monkeypatch.setattr(app_config, "ALLOW_VENDOR_FALLBACK_FOR_WIDTH", True, raising=False)
    monkeypatch.setattr(app_config, "FEATURE_MIN_SELECTED_VENDORS", 1, raising=False)
    monkeypatch.setattr(app_config, "ALLOW_ADAPTIVE_TOP_K", True, raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_EVIDENCE_OVERRIDE_USED", False, raising=False)

    monkeypatch.setattr(
        feature_vector_builder,
        "_select_top_vendors",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        feature_vector_builder,
        "_ensure_min_vendor_selection",
        lambda **kwargs: ["lionic"],
    )
    monkeypatch.setattr(
        feature_vector_builder,
        "_prepare_vendor_features",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "sample_id": [1, 2],
                "lionic__Parsed Family": ["a", "b"],
            }
        ),
    )
    monkeypatch.setattr(
        feature_vector_builder,
        "encode_features",
        lambda *args, **kwargs: pd.DataFrame({"feat": [1, 0]}, index=[1, 2]),
    )

    out = feature_vector_builder.build_feature_vector(
        weights_df=pd.DataFrame(
            {
                "Vendor": ["lionic"],
                "Leakage Safe Score": [0.1],
                "included_in_model": [0],
            }
        ),
        parsed_vendor_data={"lionic": {"dummy": "x"}},
        top_k=8,
        score_preference="Leakage Safe Score",
        verbose=False,
    )

    assert not out.empty
    assert bool(out.attrs.get("vendor_fallback_used", False)) is True
    assert str(out.attrs.get("vendor_selection_policy", "")) == "explicit_widening"


def test_merge_extra_features_joins_on_sample_id_column_with_range_index() -> None:
    """Extras must align on ``sample_id`` when the matrix uses RangeIndex (fused-path bug)."""
    encoded = pd.DataFrame(
        {
            "sample_id": [495, 579, 657],
            "feat_a": [1, 2, 3],
        },
        index=pd.RangeIndex(3),
    )
    extra = pd.DataFrame(
        {
            "sample_id": [657, 495, 579],
            "perm__android_permission_internet": [1, 1, 0],
            "perm__total_count": [2, 2, 1],
        }
    )
    out, _maps = feature_vector_builder._merge_extra_features(encoded, extra, verbose=False)
    assert out["sample_id"].tolist() == [495, 579, 657]
    assert out["feat_a"].tolist() == [1, 2, 3]
    assert out["perm__android_permission_internet"].tolist() == [1, 0, 1]
    assert out["perm__total_count"].tolist() == [2, 1, 2]


def test_merge_extra_features_coerces_object_perm_columns_numeric() -> None:
    """Permission bag columns must not use categorical codes (object dtype from CSV joins)."""
    encoded = pd.DataFrame(
        {"feat_a": [1, 2]},
        index=pd.Index([10, 20], name="sample_id"),
    )
    extra = pd.DataFrame(
        {
            "sample_id": [10, 20],
            "perm__android_permission_internet": ["1", "0"],
            "perm__total_count": ["3", "0"],
        }
    )
    out, maps = feature_vector_builder._merge_extra_features(encoded, extra, verbose=False)
    assert "perm__android_permission_internet" not in maps
    assert out["perm__android_permission_internet"].tolist() == [1, 0]
    assert out["perm__total_count"].tolist() == [3, 0]


def test_expand_to_cohort_authoritative_adds_permission_row_for_vendor_gap() -> None:
    """Cohort ids without vendor merge rows still receive enrichment columns from extras."""
    merged = pd.DataFrame(
        {"v__threat": [1, 2], "perm__bag": [1, 0]},
        index=pd.Index([10, 20], name="sample_id"),
    )
    merged.attrs["encoder_mappings"] = {
        "v__threat": {"unknown": 0, "a": 1, "b": 2},
        "perm__bag": {},
    }
    merged.attrs["vendor_merge_sample_ids"] = [10, 20]
    extra = pd.DataFrame({"sample_id": [10, 20, 99], "perm__bag": [1, 0, 7]})
    out = feature_vector_builder._expand_to_cohort_authoritative(
        merged,
        cohort_sample_ids=[10, 20, 99],
        vendor_feature_columns=["v__threat"],
        encoder_mappings=dict(merged.attrs["encoder_mappings"]),
        vendor_merge_sample_ids=[10, 20],
        extra_features_df=extra,
        verbose=False,
    )
    assert len(out) == 3
    assert int(out.loc[99, "v__threat"]) == 0
    assert float(out.loc[99, "perm__bag"]) == 7.0


def test_merge_extra_features_joins_on_sample_id_index_when_no_column() -> None:
    """When ``sample_id`` is only the index, extras still align by id (not by position)."""
    encoded = pd.DataFrame(
        {"feat_a": [10, 20, 30]},
        index=pd.Index([495, 579, 657], name="sample_id"),
    )
    extra = pd.DataFrame(
        {
            "sample_id": [579, 657, 495],
            "perm__x": [0, 1, 1],
        }
    )
    out, _ = feature_vector_builder._merge_extra_features(encoded, extra, verbose=False)
    assert out["feat_a"].tolist() == [10, 20, 30]
    assert out["perm__x"].tolist() == [1, 0, 1]


def test_export_vendor_gate_debug_run_scoped_uses_global_latest_mirror_only(
    monkeypatch,
    make_run_diagnostics_layout,
) -> None:
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("rid")
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "rid", raising=False)

    out = feature_vector_builder._export_vendor_gate_debug(  # pylint: disable=protected-access
        weights_df=pd.DataFrame(
            {
                "Vendor": ["tencent", "lionic"],
                "Leakage Safe Score Raw": [0.9, 0.8],
                "Leakage Safe Score": [0.9, 0.8],
                "Vendor Category": ["High Diversity", "High Diversity"],
            }
        ),
        selected_vendors=["tencent"],
        parsed_vendor_data={"tencent": {"x": 1}, "lionic": {"x": 1}},
        top_vendors_initial=["tencent"],
    )

    assert out == str(diagnostics_dir / "vendor_gate_debug_rid.csv")
    assert Path(out).is_file()
    assert not (diagnostics_dir / "vendor_gate_debug.latest.csv").exists()
    assert (output_root / "diagnostics" / "vendor_gate_debug.latest.csv").is_file()
