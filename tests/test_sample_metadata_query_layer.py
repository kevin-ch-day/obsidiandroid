"""Tests for type-aware sample metadata query facade and sample stage wiring."""

from __future__ import annotations

import pandas as pd

from analysis.pipeline import stage_samples
from database import db_sample_metadata_queries


def test_load_samples_by_type_supports_all_types_when_slug_none(monkeypatch) -> None:
    """`type_slug=None` should flow through to fetcher without applying a type filter."""
    captured: dict[str, object] = {}

    def _fake_fetch(**kwargs):
        captured.update(kwargs)
        return (["sample_id"], [(1,)])

    monkeypatch.setattr(db_sample_metadata_queries, "_fetch_samples_by_type", _fake_fetch)
    df = db_sample_metadata_queries.load_samples_by_type(type_slug=None)
    assert not df.empty
    assert captured["type_slug"] is None


def test_load_banker_dataframe_routes_to_generic_type_loader(monkeypatch) -> None:
    """Convenience banker loader should route to generic type-aware API."""
    captured: dict[str, object] = {}

    def _fake_fetch(**kwargs):
        captured.update(kwargs)
        return (["sample_id"], [(1,)])

    monkeypatch.setattr(db_sample_metadata_queries, "_fetch_samples_by_type", _fake_fetch)
    df = db_sample_metadata_queries.load_banker_dataframe(limit=10)
    assert int(df.shape[0]) == 1
    assert captured["type_slug"] == "banker"
    assert captured["limit"] == 10


def test_stage_samples_forwards_excluded_families_to_sql_layer(monkeypatch, tmp_path) -> None:
    """Stage sample loading should pass `exclude_families` to stats and SQL fetchers."""
    profile = {
        "cohort_gates": {
            "exclude_families": ["Devixor", " Gigabud "],
        }
    }

    stats_calls: list[dict[str, object]] = []
    load_calls: list[dict[str, object]] = []

    monkeypatch.setattr(stage_samples.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(stage_samples.app_config, "EXPORT_ANALYSIS_SNAPSHOT", False, raising=False)

    monkeypatch.setattr(stage_samples, "_resolve_dataset_time_contract", lambda **_kwargs: {})
    monkeypatch.setattr(stage_samples, "_augment_dataset_time_contract", lambda **kwargs: kwargs["time_contract"])
    monkeypatch.setattr(stage_samples, "_export_dataset_time_contract", lambda **_kwargs: "time.json")
    monkeypatch.setattr(stage_samples, "_export_time_window_family_distributions", lambda **_kwargs: [])
    monkeypatch.setattr(stage_samples, "_export_paper_cohort_sample_ids", lambda **_kwargs: "ids.csv")
    monkeypatch.setattr(stage_samples, "_export_cohort_filter_contract", lambda **_kwargs: ("a.json", "b.csv"))
    monkeypatch.setattr(stage_samples, "export_cohort_filter_summary", lambda **_kwargs: "summary.csv")
    monkeypatch.setattr(
        stage_samples.cohort_readiness_report, "print_cohort_sql_scope_gate_summary", lambda _stats: None
    )
    monkeypatch.setattr(stage_samples.cohort_readiness_report, "print_cohort_readiness_report", lambda _df, gates=None: None)
    monkeypatch.setattr(stage_samples, "prepare_sample_dataframe", lambda **kwargs: kwargs["df"])
    monkeypatch.setattr(stage_samples, "apply_dataset_filters", lambda df, _profile: df)
    monkeypatch.setattr(stage_samples, "_assert_package_name_integrity", lambda **_kwargs: None)

    def _fake_stats(**kwargs):
        stats_calls.append(kwargs)
        return {"total_candidates": 1, "final_count_estimate": 1}

    def _fake_load(**kwargs):
        load_calls.append(kwargs)
        return pd.DataFrame(
            [
                {
                    "sample_id": 1,
                    "sha256": "a" * 64,
                    "family_canonical": "x",
                    "type_slug": "banker",
                    "permissions": 1,
                    "android_package_name": "pkg",
                    "vt_malicious_count": 1,
                }
            ]
        )

    monkeypatch.setattr(stage_samples.db_sample_metadata_queries, "get_type_cohort_gate_stats", _fake_stats)
    monkeypatch.setattr(stage_samples.db_sample_metadata_queries, "load_samples_by_type", _fake_load)

    out = stage_samples.load_and_prepare_samples(
        profile=profile,
        profile_id="test_profile",
        type_slug="banker",
        run_id="run1",
        artifact_list=[],
    )
    assert int(out.shape[0]) == 1
    expected = ("devixor", "gigabud")
    assert stats_calls[0]["exclude_family_canonical"] == expected
    assert load_calls[0]["exclude_family_canonical"] == expected


def test_stage_samples_forwards_exclude_unknown_type_slug_to_sql_layer(monkeypatch, tmp_path) -> None:
    """Stage sample loading should pass `exclude_unknown_type_slug` to stats and SQL fetchers."""
    profile = {
        "cohort_gates": {
            "exclude_unknown_type_slug": True,
        }
    }

    stats_calls: list[dict[str, object]] = []
    load_calls: list[dict[str, object]] = []

    monkeypatch.setattr(stage_samples.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(stage_samples.app_config, "EXPORT_ANALYSIS_SNAPSHOT", False, raising=False)

    monkeypatch.setattr(stage_samples, "_resolve_dataset_time_contract", lambda **_kwargs: {})
    monkeypatch.setattr(stage_samples, "_augment_dataset_time_contract", lambda **kwargs: kwargs["time_contract"])
    monkeypatch.setattr(stage_samples, "_export_dataset_time_contract", lambda **_kwargs: "time.json")
    monkeypatch.setattr(stage_samples, "_export_time_window_family_distributions", lambda **_kwargs: [])
    monkeypatch.setattr(stage_samples, "_export_paper_cohort_sample_ids", lambda **_kwargs: "ids.csv")
    monkeypatch.setattr(stage_samples, "_export_cohort_filter_contract", lambda **_kwargs: ("a.json", "b.csv"))
    monkeypatch.setattr(stage_samples, "export_cohort_filter_summary", lambda **_kwargs: "summary.csv")
    monkeypatch.setattr(
        stage_samples.cohort_readiness_report, "print_cohort_sql_scope_gate_summary", lambda _stats: None
    )
    monkeypatch.setattr(stage_samples.cohort_readiness_report, "print_cohort_readiness_report", lambda _df, gates=None: None)
    monkeypatch.setattr(stage_samples, "prepare_sample_dataframe", lambda **kwargs: kwargs["df"])
    monkeypatch.setattr(stage_samples, "apply_dataset_filters", lambda df, _profile: df)
    monkeypatch.setattr(stage_samples, "_assert_package_name_integrity", lambda **_kwargs: None)

    def _fake_stats(**kwargs):
        stats_calls.append(kwargs)
        return {"total_candidates": 1, "final_count_estimate": 1}

    def _fake_load(**kwargs):
        load_calls.append(kwargs)
        return pd.DataFrame(
            [
                {
                    "sample_id": 1,
                    "sha256": "a" * 64,
                    "family_canonical": "x",
                    "type_slug": "banker",
                    "permissions": 1,
                    "android_package_name": "pkg",
                    "vt_malicious_count": 1,
                }
            ]
        )

    monkeypatch.setattr(stage_samples.db_sample_metadata_queries, "get_type_cohort_gate_stats", _fake_stats)
    monkeypatch.setattr(stage_samples.db_sample_metadata_queries, "load_samples_by_type", _fake_load)

    out = stage_samples.load_and_prepare_samples(
        profile=profile,
        profile_id="test_profile",
        type_slug=None,
        run_id="run1",
        artifact_list=[],
    )
    assert int(out.shape[0]) == 1
    assert stats_calls[0]["exclude_unknown_type_slug"] is True
    assert load_calls[0]["exclude_unknown_type_slug"] is True


def test_stage_samples_enforces_unknown_exclusion_for_evidence_mode(monkeypatch, tmp_path) -> None:
    """Evidence mode should force SQL unknown-type exclusion even without explicit gate."""
    profile = {
        "cohort_gates": {},
    }

    stats_calls: list[dict[str, object]] = []
    load_calls: list[dict[str, object]] = []

    monkeypatch.setattr(stage_samples.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(stage_samples.app_config, "EXPORT_ANALYSIS_SNAPSHOT", False, raising=False)
    monkeypatch.setattr(stage_samples.app_config, "RUNTIME_EVIDENCE_MODE", True, raising=False)
    monkeypatch.setattr(stage_samples.app_config, "PAPER_MODE_ENABLED", False, raising=False)

    monkeypatch.setattr(stage_samples, "_resolve_dataset_time_contract", lambda **_kwargs: {})
    monkeypatch.setattr(stage_samples, "_augment_dataset_time_contract", lambda **kwargs: kwargs["time_contract"])
    monkeypatch.setattr(stage_samples, "_export_dataset_time_contract", lambda **_kwargs: "time.json")
    monkeypatch.setattr(stage_samples, "_export_time_window_family_distributions", lambda **_kwargs: [])
    monkeypatch.setattr(stage_samples, "_export_paper_cohort_sample_ids", lambda **_kwargs: "ids.csv")
    monkeypatch.setattr(stage_samples, "_export_cohort_filter_contract", lambda **_kwargs: ("a.json", "b.csv"))
    monkeypatch.setattr(stage_samples, "export_cohort_filter_summary", lambda **_kwargs: "summary.csv")
    monkeypatch.setattr(
        stage_samples.cohort_readiness_report, "print_cohort_sql_scope_gate_summary", lambda _stats: None
    )
    monkeypatch.setattr(stage_samples.cohort_readiness_report, "print_cohort_readiness_report", lambda _df, gates=None: None)
    monkeypatch.setattr(stage_samples, "prepare_sample_dataframe", lambda **kwargs: kwargs["df"])
    monkeypatch.setattr(stage_samples, "apply_dataset_filters", lambda df, _profile: df)
    monkeypatch.setattr(stage_samples, "_assert_package_name_integrity", lambda **_kwargs: None)

    def _fake_stats(**kwargs):
        stats_calls.append(kwargs)
        return {"total_candidates": 1, "final_count_estimate": 1}

    def _fake_load(**kwargs):
        load_calls.append(kwargs)
        return pd.DataFrame(
            [
                {
                    "sample_id": 1,
                    "sha256": "a" * 64,
                    "family_canonical": "x",
                    "type_slug": "banker",
                    "permissions": 1,
                    "android_package_name": "pkg",
                    "vt_malicious_count": 1,
                }
            ]
        )

    monkeypatch.setattr(stage_samples.db_sample_metadata_queries, "get_type_cohort_gate_stats", _fake_stats)
    monkeypatch.setattr(stage_samples.db_sample_metadata_queries, "load_samples_by_type", _fake_load)

    out = stage_samples.load_and_prepare_samples(
        profile=profile,
        profile_id="test_profile",
        type_slug=None,
        run_id="run1",
        artifact_list=[],
    )
    assert int(out.shape[0]) == 1
    assert stats_calls[0]["exclude_unknown_type_slug"] is True
    assert load_calls[0]["exclude_unknown_type_slug"] is True


def test_validate_type_slug_uses_db_taxonomy_in_hybrid_mode(monkeypatch) -> None:
    """Hybrid slug validation should use DB slugs when available."""
    monkeypatch.setattr(
        db_sample_metadata_queries.app_config,
        "TYPE_SLUG_VALIDATION_MODE",
        "hybrid",
        raising=False,
    )
    monkeypatch.setattr(
        db_sample_metadata_queries,
        "fetch_available_android_type_slugs",
        lambda: ("banker", "dropper", "new-type"),
    )
    db_sample_metadata_queries._DB_TYPE_SLUG_CACHE = None  # pylint: disable=protected-access

    db_sample_metadata_queries._validate_type_slug("new-type")  # pylint: disable=protected-access


def test_validate_type_slug_hybrid_falls_back_to_static_on_db_failure(monkeypatch) -> None:
    """Hybrid mode should fallback to static slugs when DB taxonomy fetch fails."""
    monkeypatch.setattr(
        db_sample_metadata_queries.app_config,
        "TYPE_SLUG_VALIDATION_MODE",
        "hybrid",
        raising=False,
    )

    def _boom():
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(db_sample_metadata_queries, "fetch_available_android_type_slugs", _boom)
    db_sample_metadata_queries._DB_TYPE_SLUG_CACHE = None  # pylint: disable=protected-access

    db_sample_metadata_queries._validate_type_slug("banker")  # pylint: disable=protected-access


def test_stage_samples_sets_runtime_min_family_support_from_profile_gates(monkeypatch, tmp_path) -> None:
    """Sample stage should expose profile min-family-support for downstream training."""
    profile = {
        "cohort_gates": {
            "min_samples_per_family": 20,
        }
    }

    monkeypatch.setattr(stage_samples.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(stage_samples.app_config, "EXPORT_ANALYSIS_SNAPSHOT", False, raising=False)

    monkeypatch.setattr(stage_samples, "_resolve_dataset_time_contract", lambda **_kwargs: {})
    monkeypatch.setattr(stage_samples, "_augment_dataset_time_contract", lambda **kwargs: kwargs["time_contract"])
    monkeypatch.setattr(stage_samples, "_export_dataset_time_contract", lambda **_kwargs: "time.json")
    monkeypatch.setattr(stage_samples, "_export_time_window_family_distributions", lambda **_kwargs: [])
    monkeypatch.setattr(stage_samples, "_export_paper_cohort_sample_ids", lambda **_kwargs: "ids.csv")
    monkeypatch.setattr(stage_samples, "_export_cohort_filter_contract", lambda **_kwargs: ("a.json", "b.csv"))
    monkeypatch.setattr(stage_samples, "export_cohort_filter_summary", lambda **_kwargs: "summary.csv")
    monkeypatch.setattr(
        stage_samples.cohort_readiness_report, "print_cohort_sql_scope_gate_summary", lambda _stats: None
    )
    monkeypatch.setattr(stage_samples.cohort_readiness_report, "print_cohort_readiness_report", lambda _df, gates=None: None)
    monkeypatch.setattr(stage_samples, "prepare_sample_dataframe", lambda **kwargs: kwargs["df"])
    monkeypatch.setattr(stage_samples, "apply_dataset_filters", lambda df, _profile: df)
    monkeypatch.setattr(stage_samples, "_assert_package_name_integrity", lambda **_kwargs: None)
    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "get_type_cohort_gate_stats",
        lambda **_kwargs: {"total_candidates": 1, "final_count_estimate": 1},
    )
    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "load_samples_by_type",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "sample_id": 1,
                    "sha256": "a" * 64,
                    "family_canonical": "x",
                    "type_slug": "banker",
                    "permissions": 1,
                    "android_package_name": "pkg",
                    "vt_malicious_count": 1,
                }
            ]
        ),
    )

    stage_samples.load_and_prepare_samples(
        profile=profile,
        profile_id="test_profile",
        type_slug=None,
        run_id="run1",
        artifact_list=[],
    )

    assert int(getattr(stage_samples.app_config, "RUNTIME_MIN_FAMILY_SUPPORT", 0)) == 20

