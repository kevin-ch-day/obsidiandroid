"""Tests for type-aware sample metadata query facade and sample stage wiring."""

from __future__ import annotations

import pandas as pd
import pytest

from obsidiandroid.cli import profile_manager
from obsidiandroid.common.repo_paths import repo_root
from obsidiandroid.pipeline import stage_samples
from obsidiandroid.database import db_sample_metadata_queries


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


def test_validate_type_slug_hybrid_static_fallback_accepts_live_taxonomy_slug(monkeypatch) -> None:
    """Fallback validation should still allow slugs present in the current live taxonomy."""
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

    db_sample_metadata_queries._validate_type_slug("ransomware")  # pylint: disable=protected-access


def test_validate_type_slug_static_accepts_current_taxonomy_slug(monkeypatch) -> None:
    """Static validation should include the expanded supported Android malware taxonomy."""
    monkeypatch.setattr(
        db_sample_metadata_queries.app_config,
        "TYPE_SLUG_VALIDATION_MODE",
        "static",
        raising=False,
    )

    db_sample_metadata_queries._validate_type_slug("ransomware")  # pylint: disable=protected-access


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


def test_stage_samples_temporal_evidence_profiles_require_min_support_floor(
    monkeypatch,
    tmp_path,
) -> None:
    """Canonical temporal evidence profiles must keep the floor-20 min-support guard."""
    profile = {
        "cohort_gates": {
            "min_samples_per_family": 3,
            "min_support_guard_mode": "temporal_evidence_floor_20",
        }
    }
    monkeypatch.setattr(stage_samples.app_config, "PAPER_MODE_ENABLED", True, raising=False)
    monkeypatch.setattr(stage_samples.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)

    with pytest.raises(
        ValueError,
        match=r"Evidence/publication-ready temporal malicious profiles require .* >= 20",
    ):
        stage_samples.load_and_prepare_samples(
            profile=profile,
            profile_id="malicious_temporal_stability",
            type_slug=None,
            run_id="run1",
            artifact_list=[],
        )


def test_stage_samples_direct_legacy_paper2_profile_path_preserves_min_support_floor(
    monkeypatch,
    tmp_path,
) -> None:
    """Directly loaded legacy paper2 YAMLs should keep the same guard via explicit metadata."""
    profile = profile_manager.load_profile(
        str(repo_root() / "profiles" / "paper2_primary.yaml")
    )
    profile["cohort_gates"]["min_samples_per_family"] = 3
    monkeypatch.setattr(stage_samples.app_config, "PAPER_MODE_ENABLED", True, raising=False)
    monkeypatch.setattr(stage_samples.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)

    with pytest.raises(
        ValueError,
        match=r"Evidence/publication-ready temporal malicious profiles require .* >= 20",
    ):
        stage_samples.load_and_prepare_samples(
            profile=profile,
            profile_id=str(profile["profile_id"]),
            type_slug=None,
            run_id="run1",
            artifact_list=[],
        )


def test_stage_samples_banker_locked_does_not_receive_temporal_min_support_floor(
    monkeypatch,
    tmp_path,
) -> None:
    """Non-temporal locked profiles should not inherit the temporal evidence floor."""
    profile = {
        "paper_locked": True,
        "cohort_gates": {
            "min_samples_per_family": 3,
        },
    }
    monkeypatch.setattr(stage_samples.app_config, "PAPER_MODE_ENABLED", True, raising=False)
    monkeypatch.setattr(stage_samples.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(stage_samples.app_config, "EXPORT_ANALYSIS_SNAPSHOT", False, raising=False)
    monkeypatch.setattr(stage_samples, "_resolve_dataset_time_contract", lambda **_kwargs: {})
    monkeypatch.setattr(stage_samples, "_augment_dataset_time_contract", lambda **kwargs: kwargs["time_contract"])
    monkeypatch.setattr(stage_samples, "_export_dataset_time_contract", lambda **_kwargs: "time.json")
    monkeypatch.setattr(stage_samples, "_export_time_window_family_distributions", lambda **_kwargs: [])
    monkeypatch.setattr(stage_samples, "_export_paper_cohort_sample_ids", lambda **_kwargs: "ids.csv")
    monkeypatch.setattr(stage_samples, "_export_cohort_filter_contract", lambda **_kwargs: ("a.json", "b.csv"))
    monkeypatch.setattr(stage_samples, "export_cohort_filter_summary", lambda **_kwargs: "summary.csv")
    monkeypatch.setattr(stage_samples.cohort_readiness_report, "print_cohort_sql_scope_gate_summary", lambda _stats: None)
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
        profile_id="banker_locked",
        type_slug="banker",
        run_id="run1",
        artifact_list=[],
    )


def test_stage_samples_guard_uses_metadata_not_profile_name(
    monkeypatch,
    tmp_path,
) -> None:
    """The temporal support-floor guard should rely on metadata, not paper2 naming."""
    monkeypatch.setattr(stage_samples.app_config, "PAPER_MODE_ENABLED", True, raising=False)
    monkeypatch.setattr(stage_samples.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)

    with pytest.raises(
        ValueError,
        match=r"Evidence/publication-ready temporal malicious profiles require .* >= 20",
    ):
        stage_samples.load_and_prepare_samples(
            profile={
                "cohort_gates": {
                    "min_samples_per_family": 3,
                    "min_support_guard_mode": "temporal_evidence_floor_20",
                }
            },
            profile_id="synthetic_current_profile",
            type_slug=None,
            run_id="run1",
            artifact_list=[],
        )

    monkeypatch.setattr(stage_samples.app_config, "EXPORT_ANALYSIS_SNAPSHOT", False, raising=False)
    monkeypatch.setattr(stage_samples, "_resolve_dataset_time_contract", lambda **_kwargs: {})
    monkeypatch.setattr(stage_samples, "_augment_dataset_time_contract", lambda **kwargs: kwargs["time_contract"])
    monkeypatch.setattr(stage_samples, "_export_dataset_time_contract", lambda **_kwargs: "time.json")
    monkeypatch.setattr(stage_samples, "_export_time_window_family_distributions", lambda **_kwargs: [])
    monkeypatch.setattr(stage_samples, "_export_paper_cohort_sample_ids", lambda **_kwargs: "ids.csv")
    monkeypatch.setattr(stage_samples, "_export_cohort_filter_contract", lambda **_kwargs: ("a.json", "b.csv"))
    monkeypatch.setattr(stage_samples, "export_cohort_filter_summary", lambda **_kwargs: "summary.csv")
    monkeypatch.setattr(stage_samples.cohort_readiness_report, "print_cohort_sql_scope_gate_summary", lambda _stats: None)
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
        profile={
            "cohort_gates": {
                "min_samples_per_family": 3,
            }
        },
        profile_id="paper2_synthetic_without_metadata",
        type_slug=None,
        run_id="run1",
        artifact_list=[],
    )


def test_stage_samples_locked_snapshot_defers_membership_shrinking_sql_gates(monkeypatch, tmp_path) -> None:
    """Paper-locked sample-id snapshots should own membership before support/exclusion gates."""
    profile = {
        "paper_locked": True,
        "paper_lock": {
            "sample_id_lock_file": str(tmp_path / "lock.csv"),
        },
        "cohort_gates": {
            "min_samples_per_family": 20,
            "exclude_families": ["Devixor", "Gigabud"],
        },
    }
    captured: dict[str, object] = {}

    monkeypatch.setattr(stage_samples.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(stage_samples.app_config, "EXPORT_ANALYSIS_SNAPSHOT", False, raising=False)
    monkeypatch.setattr(stage_samples.app_config, "ENABLE_SNAPSHOT_LOCK", True, raising=False)
    monkeypatch.setattr(stage_samples.app_config, "SNAPSHOT_LOCK_FILE", str(tmp_path / "lock.csv"), raising=False)
    monkeypatch.setattr(stage_samples.app_config, "RUNTIME_EVIDENCE_STRICT_MODE", True, raising=False)

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
    monkeypatch.setattr(stage_samples, "_assert_package_name_integrity", lambda **_kwargs: None)
    def _fake_gate_stats(**kwargs):
        captured["gate_stats_kwargs"] = kwargs
        return {"total_candidates": 10, "governed_cohort_count": 10}

    def _fake_load(**kwargs):
        captured["load_kwargs"] = kwargs
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

    monkeypatch.setattr(stage_samples.db_sample_metadata_queries, "get_type_cohort_gate_stats", _fake_gate_stats)
    monkeypatch.setattr(stage_samples.db_sample_metadata_queries, "load_samples_by_type", _fake_load)

    def _snapshot_lock(**kwargs):
        captured["snapshot_lock_kwargs"] = kwargs
        df = kwargs["samples_df"].copy()
        df.attrs["snapshot_lock"] = {
            "status": "matched",
            "applied": True,
            "matched_sample_count": len(df),
            "lock_sample_count": len(df),
            "missing_from_db_count": 0,
            "fail_closed": kwargs["fail_closed"],
        }
        return df

    monkeypatch.setattr(stage_samples.cohort_reproducibility, "apply_analysis_snapshot_lock", _snapshot_lock)
    monkeypatch.setattr(
        stage_samples,
        "apply_dataset_filters",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("dataset filters should be skipped")),
    )
    monkeypatch.setattr(
        stage_samples,
        "apply_contract_filters",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("contract filters should be skipped")),
    )

    stage_samples.load_and_prepare_samples(
        profile=profile,
        profile_id="malicious_temporal_stability_locked",
        type_slug=None,
        run_id="run_locked",
        artifact_list=[],
    )

    assert captured["gate_stats_kwargs"]["min_samples_per_family"] is None
    assert captured["load_kwargs"]["min_samples_per_family"] is None
    assert captured["gate_stats_kwargs"]["exclude_family_canonical"] == tuple()
    assert captured["load_kwargs"]["exclude_family_canonical"] == tuple()
    assert captured["snapshot_lock_kwargs"]["lock_file"] == str(tmp_path / "lock.csv")
