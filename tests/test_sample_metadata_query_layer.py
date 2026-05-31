"""Tests for type-aware sample metadata query facade and sample stage wiring."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from obsidiandroid.cli import profile_manager
from obsidiandroid.common.repo_paths import repo_root
from obsidiandroid.pipeline import stage_samples
from obsidiandroid.database import db_sample_metadata_queries


def _locked_materialization_stub(samples_df: pd.DataFrame, **overrides) -> SimpleNamespace:
    """Return a minimal lock-first materialization result for stage-sample tests."""

    work = samples_df.copy()
    work.attrs["paper_locked_materialization"] = {
        "mode": "immutable_lock_first_broad_catalog_fetch",
        "lock_file_count": int(len(work)),
        "materialized_count": int(len(work)),
    }
    work.attrs["paper_locked_label_snapshot"] = {
        "status": str(overrides.get("archived_label_snapshot_status", "available")),
        "available": bool(overrides.get("archived_label_snapshot_available", True)),
        "path": str(overrides.get("archived_label_snapshot_path", "labels.csv")),
        "label_snapshot_hash": str(overrides.get("archived_label_snapshot_hash", "labelhash")),
        "taxonomy_hash": str(overrides.get("archived_label_snapshot_hash", "labelhash")),
    }
    return SimpleNamespace(
        samples_df=work,
        missing_locked_members_path=str(overrides.get("missing_locked_members_path", "missing_locked_members.csv")),
        label_drift_csv_path=str(overrides.get("label_drift_csv_path", "locked_paper_label_drift.csv")),
        label_drift_summary_path=str(
            overrides.get("label_drift_summary_path", "locked_paper_label_drift_summary.json")
        ),
        label_drift_report_path=str(
            overrides.get("label_drift_report_path", "locked_paper_label_drift_report.md")
        ),
        archived_label_snapshot_available=bool(overrides.get("archived_label_snapshot_available", True)),
        archived_label_snapshot_status=str(overrides.get("archived_label_snapshot_status", "available")),
        archived_label_snapshot_path=str(overrides.get("archived_label_snapshot_path", "labels.csv")),
        archived_label_snapshot_hash=str(overrides.get("archived_label_snapshot_hash", "labelhash")),
    )


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
            "family_cap": 60,
            "family_cap_seed": 1337,
            "type_cap": 300,
            "type_cap_seed": 1337,
            "type_cap_by_slug": {"banker": 90, "rat": 55},
            "exclude_weak_label_kinds": True,
            "exclude_family_label_conflicts": True,
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
    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "get_type_cohort_catalog_semantics_profile",
        lambda **_kwargs: {"scope": "sql_governed_android_cohort", "non_android_lane_rows": 0},
    )
    monkeypatch.setattr(
        stage_samples.android_authority_drift_report,
        "export_android_authority_drift_reports",
        lambda **_kwargs: ["android_authority_drift.json", "android_authority_drift.csv", "android_authority_drift.md"],
    )
    monkeypatch.setattr(
        stage_samples.cohort_family_feed_risk,
        "export_family_feed_risk_reports",
        lambda **_kwargs: ["cohort_family_feed_risk.json", "cohort_family_feed_risk.csv", "cohort_family_feed_risk.md"],
    )
    monkeypatch.setattr(
        stage_samples.family_label_taxonomy_audit,
        "write_family_label_taxonomy_audit",
        lambda **kwargs: {
            "family_label_taxonomy_audit_csv": f"{kwargs.get('artifact_prefix', '')}family_label_taxonomy_audit.csv",
            "family_label_taxonomy_audit_md": f"{kwargs.get('artifact_prefix', '')}family_label_taxonomy_audit.md",
            "support_threshold_preview_csv": f"{kwargs.get('artifact_prefix', '')}support_threshold_preview.csv",
            "support_threshold_preview_md": f"{kwargs.get('artifact_prefix', '')}support_threshold_preview.md",
        },
    )
    monkeypatch.setattr(
        stage_samples.taxonomy_target_surface_report,
        "export_taxonomy_target_surface_reports",
        lambda **_kwargs: [
            "taxonomy_target_surfaces.json",
            "taxonomy_target_surfaces.csv",
            "taxonomy_target_surfaces.md",
        ],
    )
    monkeypatch.setattr(
        stage_samples.family_label_confidence_audit,
        "export_family_label_confidence_reports",
        lambda **_kwargs: [
            "family_label_confidence_audit.json",
            "family_label_confidence_families.csv",
            "family_label_confidence_samples.csv",
            "family_label_confidence_audit.md",
        ],
    )

    artifacts: list[str] = []
    out = stage_samples.load_and_prepare_samples(
        profile=profile,
        profile_id="test_profile",
        type_slug="banker",
        run_id="run1",
        artifact_list=artifacts,
    )
    assert int(out.shape[0]) == 1
    expected = ("devixor", "gigabud")
    assert stats_calls[0]["exclude_family_canonical"] == expected
    assert load_calls[0]["exclude_family_canonical"] == expected
    assert load_calls[0]["family_cap"] == 60
    assert load_calls[0]["family_cap_seed"] == 1337
    assert load_calls[0]["type_cap"] == 300
    assert load_calls[0]["type_cap_seed"] == 1337
    assert load_calls[0]["type_cap_by_slug"] == {"banker": 90, "rat": 55}
    assert load_calls[0]["exclude_weak_label_kinds"] is True
    assert load_calls[0]["exclude_family_label_conflicts"] is True
    assert out.attrs["catalog_semantics_sql_scope"]["scope"] == "sql_governed_android_cohort"
    assert "android_authority_drift.json" in artifacts
    assert "cohort_family_feed_risk.json" in artifacts
    assert "sql_governed_support_threshold_preview.csv" in artifacts
    assert "support_threshold_preview.csv" in artifacts
    assert "taxonomy_target_surfaces.json" in artifacts
    assert "family_label_confidence_audit.json" in artifacts


def test_stage_samples_builds_sql_scope_semantics_from_loaded_dataframe(monkeypatch, tmp_path) -> None:
    """Samples stage should not launch a second DB semantics scan after loading the cohort."""
    profile = {"cohort_gates": {}}

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
        stage_samples.android_authority_drift_report,
        "export_android_authority_drift_reports",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        stage_samples.taxonomy_target_surface_report,
        "export_taxonomy_target_surface_reports",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        stage_samples.family_label_confidence_audit,
        "export_family_label_confidence_reports",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "get_type_cohort_gate_stats",
        lambda **_kwargs: {"total_candidates": 1, "governed_cohort_count": 1},
    )
    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "load_samples_by_type",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "sample_id": 1,
                    "sha256": "a" * 64,
                    "family_canonical": "trickmo",
                    "family_label_raw": "trickmo",
                    "type_slug": "banker",
                    "analysis_lane": "android_artifact",
                    "sample_label_kind": "family_or_common_name",
                    "payload_target_platform": "android",
                    "payload_target_source": "artifact_platform",
                    "vt_family_token": "trickmo",
                    "source_batch_label": "",
                    "android_package_name": "pkg.a",
                    "vt_malicious_count": 1,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "get_type_cohort_catalog_semantics_profile",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("should not query DB semantics profile")),
    )

    out = stage_samples.load_and_prepare_samples(
        profile=profile,
        profile_id="df_semantics_profile",
        type_slug=None,
        run_id="run_df_semantics",
        artifact_list=[],
    )

    semantics = out.attrs["catalog_semantics_sql_scope"]
    assert semantics["scope"] == "sql_governed_android_cohort"
    assert semantics["analysis_lane_distribution"]["android_artifact"] == 1
    assert semantics["vt_family_token_rows"] == 1


def test_stage_samples_marks_limited_loader_semantics_scope(monkeypatch, tmp_path) -> None:
    """Limited profiles should not label loader-slice semantics as full governed SQL scope."""
    profile = {"cohort_gates": {"limit": 5}}

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
        stage_samples.android_authority_drift_report,
        "export_android_authority_drift_reports",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        stage_samples.taxonomy_target_surface_report,
        "export_taxonomy_target_surface_reports",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        stage_samples.family_label_confidence_audit,
        "export_family_label_confidence_reports",
        lambda **_kwargs: [],
    )
    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "get_type_cohort_gate_stats",
        lambda **_kwargs: {"total_candidates": 10, "governed_cohort_count": 8},
    )
    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "load_samples_by_type",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "sample_id": 1,
                    "sha256": "a" * 64,
                    "family_canonical": "gigabud",
                    "family_label_raw": "gigabud",
                    "type_slug": "banker",
                    "analysis_lane": "android_artifact",
                    "sample_label_kind": "family_or_common_name",
                    "payload_target_platform": "android",
                    "payload_target_source": "artifact_platform",
                    "vt_family_token": "gigabud",
                    "source_batch_label": "",
                    "android_package_name": "pkg.a",
                    "vt_malicious_count": 1,
                }
            ]
        ),
    )

    out = stage_samples.load_and_prepare_samples(
        profile=profile,
        profile_id="limited_profile",
        type_slug=None,
        run_id="run_limited_semantics",
        artifact_list=[],
    )

    assert out.attrs["catalog_semantics_sql_scope"]["scope"] == "sql_limited_loader_slice"


def test_stage_samples_sets_gate_stats_before_readiness_and_tracks_deferred_exclusions(monkeypatch, tmp_path) -> None:
    """Readiness should receive SQL-scope attrs, and locked runs should record deferred exclusions."""
    profile = {
        "paper_locked": True,
        "cohort_gates": {
            "exclude_families": ["Devixor", "Gigabud"],
        },
    }
    captured: dict[str, object] = {}

    monkeypatch.setattr(stage_samples.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(stage_samples.app_config, "EXPORT_ANALYSIS_SNAPSHOT", False, raising=False)
    monkeypatch.setattr(stage_samples.app_config, "ENABLE_SNAPSHOT_LOCK", True, raising=False)
    monkeypatch.setattr(stage_samples.app_config, "SNAPSHOT_LOCK_FILE", "baseline.csv", raising=False)

    monkeypatch.setattr(stage_samples, "_resolve_dataset_time_contract", lambda **_kwargs: {})
    monkeypatch.setattr(stage_samples, "_augment_dataset_time_contract", lambda **kwargs: kwargs["time_contract"])
    monkeypatch.setattr(stage_samples, "_export_dataset_time_contract", lambda **_kwargs: "time.json")
    monkeypatch.setattr(stage_samples, "_export_time_window_family_distributions", lambda **_kwargs: [])
    monkeypatch.setattr(stage_samples, "_export_paper_cohort_sample_ids", lambda **_kwargs: "ids.csv")
    monkeypatch.setattr(stage_samples, "_export_cohort_filter_contract", lambda **_kwargs: ("a.json", "b.csv"))
    monkeypatch.setattr(stage_samples, "export_cohort_filter_summary", lambda **_kwargs: "summary.csv")
    monkeypatch.setattr(stage_samples, "prepare_sample_dataframe", lambda **kwargs: kwargs["df"])
    monkeypatch.setattr(stage_samples, "_assert_package_name_integrity", lambda **_kwargs: None)
    monkeypatch.setattr(
        stage_samples.cohort_readiness_report,
        "print_cohort_sql_scope_gate_summary",
        lambda _stats: None,
    )

    def _capture_readiness(df, gates=None):
        captured["cohort_gate_stats"] = dict(df.attrs.get("cohort_gate_stats", {}))
        captured["requested_exclude_families"] = tuple(df.attrs.get("requested_exclude_families", ()))
        captured["deferred"] = bool(df.attrs.get("exclude_families_deferred_by_snapshot_lock", False))

    monkeypatch.setattr(
        stage_samples.cohort_readiness_report,
        "print_cohort_readiness_report",
        _capture_readiness,
    )

    monkeypatch.setattr(
        stage_samples,
        "materialize_locked_paper_cohort",
        lambda **kwargs: _locked_materialization_stub(kwargs["current_fetch_df"]),
    )
    monkeypatch.setattr(
        stage_samples.android_authority_drift_report,
        "export_android_authority_drift_reports",
        lambda **_kwargs: ["android_authority_drift.json", "android_authority_drift.csv", "android_authority_drift.md"],
    )
    monkeypatch.setattr(
        stage_samples.cohort_family_feed_risk,
        "export_family_feed_risk_reports",
        lambda **_kwargs: ["cohort_family_feed_risk.json", "cohort_family_feed_risk.csv", "cohort_family_feed_risk.md"],
    )
    monkeypatch.setattr(
        stage_samples.family_label_taxonomy_audit,
        "write_family_label_taxonomy_audit",
        lambda **kwargs: {
            "family_label_taxonomy_audit_csv": f"{kwargs.get('artifact_prefix', '')}family_label_taxonomy_audit.csv",
            "family_label_taxonomy_audit_md": f"{kwargs.get('artifact_prefix', '')}family_label_taxonomy_audit.md",
            "support_threshold_preview_csv": f"{kwargs.get('artifact_prefix', '')}support_threshold_preview.csv",
            "support_threshold_preview_md": f"{kwargs.get('artifact_prefix', '')}support_threshold_preview.md",
        },
    )
    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "get_type_cohort_catalog_semantics_profile",
        lambda **_kwargs: {"scope": "sql_governed_android_cohort", "non_android_lane_rows": 0},
    )

    def _fake_stats(**kwargs):
        return {"total_candidates": 9, "governed_cohort_count": 7}

    def _fake_load(**kwargs):
        return pd.DataFrame(
            [
                {
                    "sample_id": 1,
                    "sha256": "a" * 64,
                    "family_canonical": "fam_a",
                    "type_slug": "banker",
                    "android_package_name": "pkg.a",
                    "vt_malicious_count": 1,
                }
            ]
        )

    monkeypatch.setattr(stage_samples.db_sample_metadata_queries, "get_type_cohort_gate_stats", _fake_stats)
    monkeypatch.setattr(stage_samples.db_sample_metadata_queries, "load_samples_by_type", _fake_load)

    out = stage_samples.load_and_prepare_samples(
        profile=profile,
        profile_id="locked_profile",
        type_slug=None,
        run_id="run_locked",
        artifact_list=[],
    )
    assert int(out.shape[0]) == 1
    assert captured["cohort_gate_stats"] == {"total_candidates": 9, "governed_cohort_count": 7}
    assert captured["requested_exclude_families"] == ("devixor", "gigabud")
    assert captured["deferred"] is True


def test_stage_samples_persists_cohort_counts_before_late_integrity_failure(monkeypatch, tmp_path) -> None:
    """Samples-stage manifest counts should survive even if a late integrity check fails."""
    profile = {
        "cohort_gates": {
            "max_missing_package_pct": 0.0,
        }
    }
    manifest_context: dict[str, object] = {}

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
        stage_samples.cohort_readiness_report,
        "print_cohort_sql_scope_gate_summary",
        lambda _stats: None,
    )
    monkeypatch.setattr(
        stage_samples.cohort_readiness_report,
        "print_cohort_readiness_report",
        lambda _df, gates=None: None,
    )
    monkeypatch.setattr(stage_samples, "prepare_sample_dataframe", lambda **kwargs: kwargs["df"])
    monkeypatch.setattr(stage_samples, "apply_dataset_filters", lambda df, _profile: df)
    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "get_type_cohort_catalog_semantics_profile",
        lambda **_kwargs: {"scope": "sql_governed_android_cohort"},
    )
    monkeypatch.setattr(
        stage_samples.android_authority_drift_report,
        "export_android_authority_drift_reports",
        lambda **_kwargs: ["android_authority_drift.json"],
    )
    monkeypatch.setattr(
        stage_samples.cohort_family_feed_risk,
        "export_family_feed_risk_reports",
        lambda **_kwargs: ["cohort_family_feed_risk.json"],
    )
    monkeypatch.setattr(
        stage_samples.family_label_taxonomy_audit,
        "write_family_label_taxonomy_audit",
        lambda **kwargs: {
            "family_label_taxonomy_audit_csv": f"{kwargs.get('artifact_prefix', '')}family_label_taxonomy_audit.csv",
            "family_label_taxonomy_audit_md": f"{kwargs.get('artifact_prefix', '')}family_label_taxonomy_audit.md",
            "support_threshold_preview_csv": f"{kwargs.get('artifact_prefix', '')}support_threshold_preview.csv",
            "support_threshold_preview_md": f"{kwargs.get('artifact_prefix', '')}support_threshold_preview.md",
        },
    )

    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "get_type_cohort_gate_stats",
        lambda **_kwargs: {"total_candidates": 9, "governed_cohort_count": 7},
    )
    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "load_samples_by_type",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "sample_id": 1,
                    "sha256": "a" * 64,
                    "family_canonical": "fam_a",
                    "type_slug": "banker",
                    "android_package_name": "",
                    "vt_malicious_count": 1,
                }
            ]
        ),
    )

    with pytest.raises(ValueError, match="Missing package rate"):
        stage_samples.load_and_prepare_samples(
            profile=profile,
            profile_id="counts_failure_profile",
            type_slug=None,
            run_id="run_counts_fail",
            artifact_list=[],
            manifest_context=manifest_context,
        )

    assert manifest_context["cohort_sql_scope_row_count"] == 9
    assert manifest_context["cohort_prepared_row_count"] == 1
    assert manifest_context["gate_total_candidates"] == 9
    assert manifest_context["governed_cohort_rows"] == 1


def test_stage_samples_locked_run_exports_sql_min_support_as_deferred(monkeypatch, tmp_path) -> None:
    """Locked runs should not claim SQL min-support enforcement in the foundation bundle."""
    profile = {
        "paper_locked": True,
        "cohort_gates": {
            "min_samples_per_family": 20,
            "exclude_families": ["Devixor"],
        },
    }
    captured: dict[str, object] = {}

    monkeypatch.setattr(stage_samples.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(stage_samples.app_config, "EXPORT_ANALYSIS_SNAPSHOT", False, raising=False)
    monkeypatch.setattr(stage_samples.app_config, "ENABLE_SNAPSHOT_LOCK", True, raising=False)
    monkeypatch.setattr(stage_samples.app_config, "SNAPSHOT_LOCK_FILE", "baseline.csv", raising=False)

    monkeypatch.setattr(stage_samples, "_resolve_dataset_time_contract", lambda **_kwargs: {})
    monkeypatch.setattr(stage_samples, "_augment_dataset_time_contract", lambda **kwargs: kwargs["time_contract"])
    monkeypatch.setattr(stage_samples, "_export_dataset_time_contract", lambda **_kwargs: "time.json")
    monkeypatch.setattr(stage_samples, "_export_time_window_family_distributions", lambda **_kwargs: [])
    monkeypatch.setattr(stage_samples, "_export_paper_cohort_sample_ids", lambda **_kwargs: "ids.csv")
    monkeypatch.setattr(stage_samples, "_export_cohort_filter_contract", lambda **_kwargs: ("a.json", "b.csv"))
    monkeypatch.setattr(stage_samples, "export_cohort_filter_summary", lambda **_kwargs: "summary.csv")
    monkeypatch.setattr(stage_samples, "prepare_sample_dataframe", lambda **kwargs: kwargs["df"])
    monkeypatch.setattr(stage_samples, "_assert_package_name_integrity", lambda **_kwargs: None)
    monkeypatch.setattr(
        stage_samples.cohort_readiness_report,
        "print_cohort_sql_scope_gate_summary",
        lambda _stats: None,
    )
    monkeypatch.setattr(
        stage_samples.cohort_readiness_report,
        "print_cohort_readiness_report",
        lambda _df, gates=None: None,
    )
    monkeypatch.setattr(
        stage_samples,
        "materialize_locked_paper_cohort",
        lambda **kwargs: _locked_materialization_stub(kwargs["current_fetch_df"]),
    )
    monkeypatch.setattr(
        stage_samples.android_authority_drift_report,
        "export_android_authority_drift_reports",
        lambda **_kwargs: ["android_authority_drift.json", "android_authority_drift.csv", "android_authority_drift.md"],
    )
    monkeypatch.setattr(
        stage_samples.cohort_family_feed_risk,
        "export_family_feed_risk_reports",
        lambda **_kwargs: ["cohort_family_feed_risk.json", "cohort_family_feed_risk.csv", "cohort_family_feed_risk.md"],
    )
    monkeypatch.setattr(
        stage_samples.family_label_taxonomy_audit,
        "write_family_label_taxonomy_audit",
        lambda **kwargs: {
            "family_label_taxonomy_audit_csv": f"{kwargs.get('artifact_prefix', '')}family_label_taxonomy_audit.csv",
            "family_label_taxonomy_audit_md": f"{kwargs.get('artifact_prefix', '')}family_label_taxonomy_audit.md",
            "support_threshold_preview_csv": f"{kwargs.get('artifact_prefix', '')}support_threshold_preview.csv",
            "support_threshold_preview_md": f"{kwargs.get('artifact_prefix', '')}support_threshold_preview.md",
        },
    )
    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "get_type_cohort_catalog_semantics_profile",
        lambda **_kwargs: {"scope": "sql_governed_android_cohort", "non_android_lane_rows": 0},
    )

    def _fake_foundation(**kwargs):
        captured["min_samples_per_family_sql"] = kwargs["min_samples_per_family_sql"]
        captured["requested_excluded_families"] = tuple(
            kwargs["samples_df"].attrs.get("requested_exclude_families", ())
        )
        captured["deferred"] = bool(
            kwargs["samples_df"].attrs.get("exclude_families_deferred_by_snapshot_lock", False)
        )

    monkeypatch.setattr(
        stage_samples.cohort_foundation_export,
        "export_cohort_foundation_bundle",
        _fake_foundation,
    )

    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "get_type_cohort_gate_stats",
        lambda **_kwargs: {"total_candidates": 9, "governed_cohort_count": 7},
    )
    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "load_samples_by_type",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "sample_id": 1,
                    "sha256": "a" * 64,
                    "family_canonical": "fam_a",
                    "type_slug": "banker",
                    "android_package_name": "pkg.a",
                    "vt_malicious_count": 1,
                }
            ]
        ),
    )

    out = stage_samples.load_and_prepare_samples(
        profile=profile,
        profile_id="locked_profile",
        type_slug=None,
        run_id="run_locked",
        artifact_list=[],
    )
    assert int(out.shape[0]) == 1
    assert captured["min_samples_per_family_sql"] is None
    assert captured["requested_excluded_families"] == ("devixor",)
    assert captured["deferred"] is True


def test_stage_samples_tolerates_noncritical_diagnostics_export_failures(monkeypatch, tmp_path) -> None:
    """Cohort diagnostics export bugs should not crash an otherwise valid samples stage."""
    profile = {
        "cohort_gates": {},
    }
    warnings: list[str] = []

    monkeypatch.setattr(stage_samples.app_config, "DEFAULT_OUTPUT_DIR", str(tmp_path / "output"), raising=False)
    monkeypatch.setattr(stage_samples.app_config, "EXPORT_ANALYSIS_SNAPSHOT", False, raising=False)

    monkeypatch.setattr(stage_samples, "_resolve_dataset_time_contract", lambda **_kwargs: {})
    monkeypatch.setattr(stage_samples, "_augment_dataset_time_contract", lambda **kwargs: kwargs["time_contract"])
    monkeypatch.setattr(stage_samples, "_export_dataset_time_contract", lambda **_kwargs: "time.json")
    monkeypatch.setattr(stage_samples, "_export_time_window_family_distributions", lambda **_kwargs: [])
    monkeypatch.setattr(stage_samples, "_export_paper_cohort_sample_ids", lambda **_kwargs: "ids.csv")
    monkeypatch.setattr(stage_samples, "_export_cohort_filter_contract", lambda **_kwargs: ("a.json", "b.csv"))
    monkeypatch.setattr(stage_samples, "export_cohort_filter_summary", lambda **_kwargs: "summary.csv")
    monkeypatch.setattr(stage_samples, "prepare_sample_dataframe", lambda **kwargs: kwargs["df"])
    monkeypatch.setattr(stage_samples, "_assert_package_name_integrity", lambda **_kwargs: None)
    monkeypatch.setattr(stage_samples.du, "print_warning", lambda msg: warnings.append(str(msg)))
    monkeypatch.setattr(
        stage_samples.cohort_readiness_report,
        "print_cohort_sql_scope_gate_summary",
        lambda _stats: None,
    )
    monkeypatch.setattr(
        stage_samples.cohort_readiness_report,
        "print_cohort_readiness_report",
        lambda _df, gates=None: None,
    )
    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "get_type_cohort_catalog_semantics_profile",
        lambda **_kwargs: {"scope": "sql_governed_android_cohort", "non_android_lane_rows": 0},
    )
    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "get_type_cohort_gate_stats",
        lambda **_kwargs: {"total_candidates": 9, "governed_cohort_count": 7},
    )
    monkeypatch.setattr(
        stage_samples.db_sample_metadata_queries,
        "load_samples_by_type",
        lambda **_kwargs: pd.DataFrame(
            [
                {
                    "sample_id": 1,
                    "sha256": "a" * 64,
                    "family_canonical": "fam_a",
                    "type_slug": "banker",
                    "android_package_name": "pkg.a",
                    "vt_malicious_count": 1,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        stage_samples.cohort_foundation_export,
        "export_cohort_foundation_bundle",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("broken foundation export")),
    )
    monkeypatch.setattr(
        stage_samples.android_authority_drift_report,
        "export_android_authority_drift_reports",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("broken drift export")),
    )
    monkeypatch.setattr(
        stage_samples.cohort_family_feed_risk,
        "export_family_feed_risk_reports",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("broken feed risk export")),
    )
    monkeypatch.setattr(
        stage_samples.family_label_taxonomy_audit,
        "write_family_label_taxonomy_audit",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("broken family taxonomy export")),
    )

    out = stage_samples.load_and_prepare_samples(
        profile=profile,
        profile_id="test_profile",
        type_slug="banker",
        run_id="run1",
        artifact_list=[],
    )
    assert int(out.shape[0]) == 1
    assert any("Foundation diagnostics export skipped" in msg for msg in warnings)
    assert any("Authority-drift diagnostics export skipped" in msg for msg in warnings)
    assert any("Family feed-risk diagnostics export skipped" in msg for msg in warnings)
    assert any("Family taxonomy/support diagnostics export skipped" in msg for msg in warnings)


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


def test_stage_samples_direct_canonical_locked_profile_path_preserves_min_support_floor(
    monkeypatch,
    tmp_path,
) -> None:
    """Directly loaded canonical locked YAMLs should keep the same guard via explicit metadata."""
    profile = profile_manager.load_profile(
        str(repo_root() / "profiles" / "malicious_temporal_stability_locked.yaml")
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
    monkeypatch.setattr(
        stage_samples,
        "materialize_locked_paper_cohort",
        lambda **kwargs: _locked_materialization_stub(kwargs["current_fetch_df"]),
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

    monkeypatch.setattr(
        stage_samples,
        "materialize_locked_paper_cohort",
        lambda **kwargs: _locked_materialization_stub(kwargs["current_fetch_df"]),
    )
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
    assert str(profile["paper_lock"]["sample_id_lock_file"]) == str(tmp_path / "lock.csv")
