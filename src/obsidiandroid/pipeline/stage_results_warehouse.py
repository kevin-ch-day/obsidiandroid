"""Persist permission-trends analysis artifacts into MariaDB run-scoped tables.

Canonical implementation (**Pass 70**): ``obsidiandroid.pipeline.stage_results_warehouse``;
The supported import path is ``obsidiandroid.pipeline.stage_results_warehouse``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
from typing import Any

import numpy as np
import pandas as pd

from obsidiandroid.database import db_engine
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.runtime_paths import resolve_diagnostics_dir


def _diagnostics_dir() -> Path:
    """Resolve diagnostics directory for current runtime context."""
    return resolve_diagnostics_dir()


def persist_permission_trends_results(
    run_id: str,
    profile_id: str,
    bundle_metadata: dict[str, Any],
    sample_core_df: pd.DataFrame,
    coverage_df: pd.DataFrame,
    dangerous_df: pd.DataFrame,
    type_prevalence_df: pd.DataFrame,
    family_profiles_df: pd.DataFrame,
    type_entropy_df: pd.DataFrame,
    family_entropy_df: pd.DataFrame,
    jsd_df: pd.DataFrame,
    banker_enrichment_df: pd.DataFrame,
    discriminability_df: pd.DataFrame,
    consensus_df: pd.DataFrame,
    per_family_perf_df: pd.DataFrame,
    artifact_paths: list[str],
    type_prevalence_by_view_df: pd.DataFrame | None = None,
    family_profiles_by_view_df: pd.DataFrame | None = None,
    group_entropy_by_view_df: pd.DataFrame | None = None,
    family_jsd_by_view_df: pd.DataFrame | None = None,
    banker_enrichment_by_view_df: pd.DataFrame | None = None,
    discriminability_by_view_df: pd.DataFrame | None = None,
    banker_cluster_assignments_df: pd.DataFrame | None = None,
    banker_cluster_profiles_df: pd.DataFrame | None = None,
    temporal_trends_df: pd.DataFrame | None = None,
) -> None:
    """Write run-scoped analysis outputs into MariaDB tables."""
    _ensure_results_schema()
    _persist_analysis_snapshot(run_id, bundle_metadata)
    _persist_analysis_run(run_id, profile_id, bundle_metadata)
    _persist_snapshot_samples(run_id, sample_core_df)
    _persist_snapshot_conflicts(run_id, bundle_metadata)
    _persist_permission_coverage(run_id, coverage_df)
    _persist_dangerous_distribution(run_id, dangerous_df)
    _persist_type_prevalence(type_prevalence_df)
    _persist_family_profiles(family_profiles_df)
    _persist_group_entropy(run_id, type_entropy_df, family_entropy_df)
    _persist_family_jsd(jsd_df)
    _persist_banker_enrichment(banker_enrichment_df)
    _persist_discriminability(discriminability_df)
    _persist_consensus(consensus_df)
    _persist_per_family_spread(per_family_perf_df)
    _persist_ablation_summary(
        run_id=run_id,
        vendor_constrained_run_flag=_as_int(bundle_metadata.get("vendor_constrained_run_flag", 0)),
    )
    _persist_artifacts(run_id, artifact_paths)
    _persist_family_cohesion(run_id, family_entropy_df)
    _persist_banker_family_heterogeneity(
        run_id=run_id,
        assignments_df=banker_cluster_assignments_df,
        cluster_profiles_df=banker_cluster_profiles_df,
    )
    _persist_temporal_trends(temporal_trends_df)
    _persist_type_prevalence_by_view(type_prevalence_by_view_df)
    _persist_family_profiles_by_view(family_profiles_by_view_df)
    _persist_group_entropy_by_view(group_entropy_by_view_df)
    _persist_family_jsd_by_view(family_jsd_by_view_df)
    _persist_banker_enrichment_by_view(banker_enrichment_by_view_df)
    _persist_discriminability_by_view(discriminability_by_view_df)
    du.print_info(f"[WAREHOUSE] Persisted run-scoped results: run_id={run_id}")


def _ensure_results_schema() -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS analysis_run (
            run_id VARCHAR(64) PRIMARY KEY,
            created_at_utc DATETIME NOT NULL,
            profile_id VARCHAR(64) NOT NULL,
            git_commit VARCHAR(64) NULL,
            selection_rule_version VARCHAR(128) NOT NULL,
            snapshot_sha256_hash CHAR(64) NOT NULL,
            snapshot_row_count INT NOT NULL,
            vendor_constrained_run_flag TINYINT(1) NOT NULL DEFAULT 0,
            selected_vendor_count INT NOT NULL DEFAULT 0,
            included_vendor_count INT NOT NULL DEFAULT 0,
            excluded_vendor_count INT NOT NULL DEFAULT 0,
            notes TEXT NULL
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS analysis_snapshot (
            run_id VARCHAR(64) PRIMARY KEY,
            extracted_at_utc DATETIME NOT NULL,
            selection_rule_version VARCHAR(128) NOT NULL,
            snapshot_sha256_hash CHAR(64) NOT NULL,
            snapshot_row_count INT NOT NULL,
            selected_vendor_count INT NOT NULL DEFAULT 0,
            included_vendor_count INT NOT NULL DEFAULT 0,
            excluded_vendor_count INT NOT NULL DEFAULT 0,
            vendor_constrained_run_flag TINYINT(1) NOT NULL DEFAULT 0
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS analysis_snapshot_sample (
            run_id VARCHAR(64) NOT NULL,
            sha256 CHAR(64) NOT NULL,
            sample_id INT UNSIGNED NULL,
            family_id INT NULL,
            family_canonical VARCHAR(255) NULL,
            type_slug VARCHAR(64) NULL,
            extracted_at_utc DATETIME NOT NULL,
            feature_hash CHAR(64) NULL,
            PRIMARY KEY (run_id, sha256),
            KEY idx_snapshot_sample_id (run_id, sample_id),
            KEY idx_snapshot_family (run_id, family_id),
            KEY idx_snapshot_type (run_id, type_slug)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS snapshot_label_conflict (
            run_id VARCHAR(64) NOT NULL,
            sha256 CHAR(64) NOT NULL,
            conflict_type VARCHAR(64) NOT NULL,
            observed_values TEXT NOT NULL,
            created_at_utc DATETIME NOT NULL,
            PRIMARY KEY (run_id, sha256, conflict_type)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS permission_coverage_report (
            run_id VARCHAR(64) PRIMARY KEY,
            profile_id VARCHAR(64) NOT NULL,
            sample_count INT NOT NULL,
            samples_with_permission_rows INT NOT NULL,
            samples_zero_permission_rows INT NOT NULL,
            samples_missing_sha256 INT NOT NULL,
            samples_missing_package_name INT NOT NULL,
            pct_with_permission_rows DOUBLE NOT NULL,
            pct_missing_permission_rows DOUBLE NOT NULL,
            pct_zero_permissions DOUBLE NOT NULL,
            pct_missing_sha256 DOUBLE NOT NULL,
            pct_missing_package_name DOUBLE NOT NULL,
            pct_samples_only_common_perms DOUBLE NOT NULL,
            pct_samples_le2_permissions DOUBLE NOT NULL,
            mean_unique_permissions DOUBLE NOT NULL,
            std_unique_permissions DOUBLE NOT NULL,
            median_unique_permissions DOUBLE NOT NULL
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS dangerous_distribution_by_type (
            run_id VARCHAR(64) NOT NULL,
            type_slug VARCHAR(64) NOT NULL,
            sample_count INT NOT NULL,
            dangerous_count_strict_mean DOUBLE NOT NULL,
            dangerous_count_strict_median DOUBLE NOT NULL,
            dangerous_count_inclusive_mean DOUBLE NOT NULL,
            dangerous_count_inclusive_median DOUBLE NOT NULL,
            dangerous_count_unknown_component_mean DOUBLE NOT NULL,
            unknown_protection_rate DOUBLE NOT NULL,
            total_perm_count_mean DOUBLE NOT NULL,
            total_perm_count_median DOUBLE NOT NULL,
            permission_source_aosp_rate DOUBLE NOT NULL,
            permission_source_oem_rate DOUBLE NOT NULL,
            permission_source_app_defined_rate DOUBLE NOT NULL,
            permission_source_unknown_rate DOUBLE NOT NULL,
            PRIMARY KEY (run_id, type_slug)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS type_permission_prevalence (
            run_id VARCHAR(64) NOT NULL,
            type_slug VARCHAR(64) NOT NULL,
            permission_string VARCHAR(255) NOT NULL,
            prevalence DOUBLE NOT NULL,
            sample_count INT NOT NULL,
            PRIMARY KEY (run_id, type_slug, permission_string)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS family_permission_profile (
            run_id VARCHAR(64) NOT NULL,
            family_id INT NOT NULL,
            family_canonical VARCHAR(255) NULL,
            profile_scope VARCHAR(16) NOT NULL,
            permission_string VARCHAR(255) NOT NULL,
            prevalence DOUBLE NOT NULL,
            sample_count INT NOT NULL,
            PRIMARY KEY (run_id, family_id, profile_scope, permission_string)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS group_permission_entropy (
            run_id VARCHAR(64) NOT NULL,
            group_type VARCHAR(16) NOT NULL,
            group_key VARCHAR(64) NOT NULL,
            sample_count INT NOT NULL,
            permission_entropy DOUBLE NOT NULL,
            effective_diversity DOUBLE NOT NULL,
            PRIMARY KEY (run_id, group_type, group_key)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS family_jsd_matrix (
            run_id VARCHAR(64) NOT NULL,
            family_a VARCHAR(255) NOT NULL,
            family_b VARCHAR(255) NOT NULL,
            js_distance DOUBLE NOT NULL,
            PRIMARY KEY (run_id, family_a, family_b)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS banker_permission_enrichment (
            run_id VARCHAR(64) NOT NULL,
            permission_string VARCHAR(255) NOT NULL,
            banker_with_perm INT NOT NULL,
            banker_without_perm INT NOT NULL,
            non_banker_with_perm INT NOT NULL,
            non_banker_without_perm INT NOT NULL,
            odds_ratio DOUBLE NOT NULL,
            odds_ratio_ci_low DOUBLE NOT NULL,
            odds_ratio_ci_high DOUBLE NOT NULL,
            p_value DOUBLE NOT NULL,
            p_value_fdr_bh DOUBLE NOT NULL,
            cramers_v DOUBLE NULL,
            forced_permission_flag TINYINT(1) NOT NULL DEFAULT 0,
            PRIMARY KEY (run_id, permission_string)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS permission_discriminability_rank (
            run_id VARCHAR(64) NOT NULL,
            permission_string VARCHAR(255) NOT NULL,
            chi2_p_value DOUBLE NOT NULL,
            chi2_p_value_fdr_bh DOUBLE NOT NULL,
            cramers_v DOUBLE NOT NULL,
            mutual_information DOUBLE NOT NULL,
            global_support INT NOT NULL,
            PRIMARY KEY (run_id, permission_string)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS consensus_distribution (
            run_id VARCHAR(64) NOT NULL,
            sha256 CHAR(64) NOT NULL,
            sample_id INT UNSIGNED NULL,
            family_id INT NULL,
            type_slug VARCHAR(64) NULL,
            vendor_count INT NOT NULL,
            top1_vote_share DOUBLE NOT NULL,
            top2_vote_share DOUBLE NOT NULL,
            top1_minus_top2_gap DOUBLE NOT NULL,
            consensus_score_all_vendors DOUBLE NOT NULL,
            consensus_entropy_all_vendors DOUBLE NOT NULL,
            consensus_score_gated_vendors DOUBLE NOT NULL,
            consensus_entropy_gated_vendors DOUBLE NOT NULL,
            low_vendor_count_flag TINYINT(1) NOT NULL,
            PRIMARY KEY (run_id, sha256),
            KEY idx_cons_type (run_id, type_slug)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS per_family_performance_spread (
            run_id VARCHAR(64) NOT NULL,
            family_id INT NOT NULL,
            family_canonical VARCHAR(255) NULL,
            type_slug VARCHAR(64) NULL,
            support INT NOT NULL,
            precision_val DOUBLE NOT NULL,
            recall_val DOUBLE NOT NULL,
            f1_val DOUBLE NOT NULL,
            avg_confidence DOUBLE NULL,
            unstable_flag TINYINT(1) NOT NULL DEFAULT 0,
            PRIMARY KEY (run_id, family_id)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS ablation_summary (
            run_id VARCHAR(64) NOT NULL,
            model_name VARCHAR(64) NOT NULL,
            ablation_variant VARCHAR(64) NOT NULL,
            macro_f1 DOUBLE NOT NULL,
            weighted_f1 DOUBLE NULL,
            accuracy DOUBLE NOT NULL,
            vendor_constrained_run_flag TINYINT(1) NOT NULL DEFAULT 0,
            notes VARCHAR(255) NULL,
            PRIMARY KEY (run_id, model_name, ablation_variant)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS analysis_artifact (
            run_id VARCHAR(64) NOT NULL,
            artifact_key VARCHAR(128) NOT NULL,
            artifact_path TEXT NOT NULL,
            artifact_sha256 CHAR(64) NULL,
            created_at_utc DATETIME NOT NULL,
            PRIMARY KEY (run_id, artifact_key)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS banker_permission_family_heterogeneity (
            run_id VARCHAR(64) NOT NULL,
            family_id INT NOT NULL,
            family_canonical VARCHAR(255) NULL,
            sample_count INT NOT NULL,
            cluster_id INT NOT NULL,
            top_permissions_json TEXT NULL,
            PRIMARY KEY (run_id, family_id)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS family_permission_cohesion (
            run_id VARCHAR(64) NOT NULL,
            family_id INT NOT NULL,
            family_canonical VARCHAR(255) NULL,
            sample_count INT NOT NULL,
            permission_entropy DOUBLE NOT NULL,
            effective_diversity DOUBLE NOT NULL,
            unstable_flag TINYINT(1) NOT NULL DEFAULT 0,
            PRIMARY KEY (run_id, family_id)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS banker_permission_trends_over_time (
            run_id VARCHAR(64) NOT NULL,
            period_quarter VARCHAR(16) NOT NULL,
            year INT NOT NULL,
            quarter INT NOT NULL,
            sample_count INT NOT NULL,
            banker_sample_count INT NOT NULL,
            dangerous_count_strict_mean_all DOUBLE NULL,
            dangerous_count_strict_mean_banker DOUBLE NULL,
            banker_bind_accessibility_service_prevalence DOUBLE NULL,
            banker_system_alert_window_prevalence DOUBLE NULL,
            banker_request_install_packages_prevalence DOUBLE NULL,
            banker_read_sms_prevalence DOUBLE NULL,
            banker_receive_sms_prevalence DOUBLE NULL,
            banker_send_sms_prevalence DOUBLE NULL,
            PRIMARY KEY (run_id, period_quarter)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS type_permission_prevalence_by_view (
            run_id VARCHAR(64) NOT NULL,
            type_slug VARCHAR(64) NOT NULL,
            permission_string VARCHAR(255) NOT NULL,
            view_mode VARCHAR(16) NOT NULL,
            prevalence DOUBLE NOT NULL,
            sample_count INT NOT NULL,
            PRIMARY KEY (run_id, type_slug, permission_string, view_mode)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS family_permission_profile_by_view (
            run_id VARCHAR(64) NOT NULL,
            family_id INT NOT NULL,
            family_canonical VARCHAR(255) NULL,
            profile_scope VARCHAR(16) NOT NULL,
            permission_string VARCHAR(255) NOT NULL,
            view_mode VARCHAR(16) NOT NULL,
            prevalence DOUBLE NOT NULL,
            sample_count INT NOT NULL,
            PRIMARY KEY (run_id, family_id, profile_scope, permission_string, view_mode)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS group_permission_entropy_by_view (
            run_id VARCHAR(64) NOT NULL,
            group_type VARCHAR(16) NOT NULL,
            group_key VARCHAR(64) NOT NULL,
            view_mode VARCHAR(16) NOT NULL,
            sample_count INT NOT NULL,
            permission_entropy DOUBLE NOT NULL,
            effective_diversity DOUBLE NOT NULL,
            PRIMARY KEY (run_id, group_type, group_key, view_mode)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS family_jsd_matrix_by_view (
            run_id VARCHAR(64) NOT NULL,
            family_a VARCHAR(255) NOT NULL,
            family_b VARCHAR(255) NOT NULL,
            view_mode VARCHAR(16) NOT NULL,
            js_distance DOUBLE NOT NULL,
            PRIMARY KEY (run_id, family_a, family_b, view_mode)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS banker_permission_enrichment_by_view (
            run_id VARCHAR(64) NOT NULL,
            permission_string VARCHAR(255) NOT NULL,
            view_mode VARCHAR(16) NOT NULL,
            banker_with_perm INT NOT NULL,
            banker_without_perm INT NOT NULL,
            non_banker_with_perm INT NOT NULL,
            non_banker_without_perm INT NOT NULL,
            odds_ratio DOUBLE NOT NULL,
            odds_ratio_ci_low DOUBLE NOT NULL,
            odds_ratio_ci_high DOUBLE NOT NULL,
            p_value DOUBLE NOT NULL,
            p_value_fdr_bh DOUBLE NOT NULL,
            cramers_v DOUBLE NULL,
            forced_permission_flag TINYINT(1) NOT NULL DEFAULT 0,
            PRIMARY KEY (run_id, permission_string, view_mode)
        ) ENGINE=InnoDB
        """,
        """
        CREATE TABLE IF NOT EXISTS permission_discriminability_rank_by_view (
            run_id VARCHAR(64) NOT NULL,
            permission_string VARCHAR(255) NOT NULL,
            view_mode VARCHAR(16) NOT NULL,
            chi2_p_value DOUBLE NOT NULL,
            chi2_p_value_fdr_bh DOUBLE NOT NULL,
            cramers_v DOUBLE NOT NULL,
            mutual_information DOUBLE NOT NULL,
            global_support INT NOT NULL,
            PRIMARY KEY (run_id, permission_string, view_mode)
        ) ENGINE=InnoDB
        """,
    ]
    for sql in statements:
        db_engine.execute_query(sql)


def _persist_analysis_snapshot(run_id: str, bundle_metadata: dict[str, Any]) -> None:
    """Persist snapshot identity and vendor constraints for the run."""
    snapshot = bundle_metadata.get("snapshot_contract", {}) if isinstance(bundle_metadata, dict) else {}
    extracted_raw = _as_str(snapshot.get("extracted_at_utc"))
    extracted_at_utc = _safe_datetime_sql(extracted_raw)
    row = {
        "run_id": run_id,
        "extracted_at_utc": extracted_at_utc,
        "selection_rule_version": _as_str(snapshot.get("selection_rule_version") or "snapshot_v1"),
        "snapshot_sha256_hash": _as_str(snapshot.get("snapshot_sha256_hash"))[:64],
        "snapshot_row_count": _as_int(snapshot.get("sample_count", 0)),
        "selected_vendor_count": _as_int(bundle_metadata.get("selected_vendor_count", 0)),
        "included_vendor_count": _as_int(bundle_metadata.get("engine_included_count", 0)),
        "excluded_vendor_count": _as_int(bundle_metadata.get("engine_excluded_count", 0)),
        "vendor_constrained_run_flag": _as_int(bundle_metadata.get("vendor_constrained_run_flag", 0)),
    }
    _bulk_upsert("analysis_snapshot", [row], unique_keys=["run_id"])


def _persist_analysis_run(run_id: str, profile_id: str, bundle_metadata: dict[str, Any]) -> None:
    snapshot = bundle_metadata.get("snapshot_contract", {}) if isinstance(bundle_metadata, dict) else {}
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    row = {
        "run_id": run_id,
        "created_at_utc": now_utc,
        "profile_id": profile_id,
        "git_commit": str(bundle_metadata.get("code_commit_hash", ""))[:64] or None,
        "selection_rule_version": str(snapshot.get("selection_rule_version", "snapshot_v1")),
        "snapshot_sha256_hash": str(snapshot.get("snapshot_sha256_hash", ""))[:64],
        "snapshot_row_count": _as_int(snapshot.get("sample_count", 0)),
        "vendor_constrained_run_flag": _as_int(bundle_metadata.get("vendor_constrained_run_flag", 0)),
        "selected_vendor_count": _as_int(bundle_metadata.get("selected_vendor_count", 0)),
        "included_vendor_count": _as_int(bundle_metadata.get("engine_included_count", 0)),
        "excluded_vendor_count": _as_int(bundle_metadata.get("engine_excluded_count", 0)),
        "notes": None,
    }
    _bulk_upsert("analysis_run", [row], unique_keys=["run_id"])


def _persist_snapshot_samples(run_id: str, sample_core_df: pd.DataFrame) -> None:
    if sample_core_df.empty:
        return
    extracted_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for _, rec in sample_core_df.iterrows():
        sha256 = str(rec.get("sha256", "")).strip().lower()
        if len(sha256) != 64:
            continue
        rows.append(
            {
                "run_id": run_id,
                "sha256": sha256,
                "sample_id": _as_int(rec.get("sample_id", 0)),
                "family_id": _nullable_int(rec.get("family_id")),
                "family_canonical": _as_str(rec.get("family_canonical")),
                "type_slug": _as_str(rec.get("type_slug")),
                "extracted_at_utc": extracted_at,
                "feature_hash": None,
            }
        )
    _bulk_upsert("analysis_snapshot_sample", rows, unique_keys=["run_id", "sha256"])


def _persist_snapshot_conflicts(run_id: str, bundle_metadata: dict[str, Any]) -> None:
    snapshot = bundle_metadata.get("snapshot_contract", {}) if isinstance(bundle_metadata, dict) else {}
    conflict_count = _as_int(snapshot.get("label_conflict_count", 0))
    if conflict_count <= 0:
        return
    conflict_file = oh.resolve_analysis_snapshot_label_conflicts_path(_diagnostics_dir(), run_id)
    if not conflict_file.exists():
        return
    try:
        df = pd.read_csv(conflict_file)
    except Exception:
        return
    if df.empty:
        return
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    for _, rec in df.iterrows():
        rows.append(
            {
                "run_id": run_id,
                "sha256": _as_str(rec.get("sha256"))[:64],
                "conflict_type": _as_str(rec.get("conflict_type") or "label_conflict"),
                "observed_values": str(rec.to_dict()),
                "created_at_utc": now_utc,
            }
        )
    _bulk_upsert("snapshot_label_conflict", rows, unique_keys=["run_id", "sha256", "conflict_type"])


def _persist_permission_coverage(run_id: str, coverage_df: pd.DataFrame) -> None:
    if coverage_df.empty:
        return
    rec = coverage_df.iloc[0].to_dict()
    row = {
        "run_id": run_id,
        "profile_id": _as_str(rec.get("profile_id")),
        "sample_count": _as_int(rec.get("sample_count", 0)),
        "samples_with_permission_rows": _as_int(rec.get("samples_with_permission_rows", 0)),
        "samples_zero_permission_rows": _as_int(rec.get("samples_zero_permission_rows", 0)),
        "samples_missing_sha256": _as_int(rec.get("samples_missing_sha256", 0)),
        "samples_missing_package_name": _as_int(rec.get("samples_missing_package_name", 0)),
        "pct_with_permission_rows": _as_float(rec.get("pct_with_permission_rows", 0.0)),
        "pct_missing_permission_rows": _as_float(rec.get("pct_missing_permission_rows", 0.0)),
        "pct_zero_permissions": _as_float(rec.get("pct_zero_permissions", 0.0)),
        "pct_missing_sha256": _as_float(rec.get("pct_missing_sha256", 0.0)),
        "pct_missing_package_name": _as_float(rec.get("pct_missing_package_name", 0.0)),
        "pct_samples_only_common_perms": _as_float(rec.get("pct_samples_only_common_perms", 0.0)),
        "pct_samples_le2_permissions": _as_float(rec.get("pct_samples_le2_permissions", 0.0)),
        "mean_unique_permissions": _as_float(rec.get("mean_unique_permissions", 0.0)),
        "std_unique_permissions": _as_float(rec.get("std_unique_permissions", 0.0)),
        "median_unique_permissions": _as_float(rec.get("median_unique_permissions", 0.0)),
    }
    _bulk_upsert("permission_coverage_report", [row], unique_keys=["run_id"])


def _persist_dangerous_distribution(run_id: str, dangerous_df: pd.DataFrame) -> None:
    if dangerous_df.empty:
        return
    rows = []
    for _, rec in dangerous_df.iterrows():
        rows.append(
            {
                "run_id": run_id,
                "type_slug": _as_str(rec.get("type_slug")),
                "sample_count": _as_int(rec.get("sample_count", 0)),
                "dangerous_count_strict_mean": _as_float(rec.get("dangerous_count_strict_mean", 0.0)),
                "dangerous_count_strict_median": _as_float(rec.get("dangerous_count_strict_median", 0.0)),
                "dangerous_count_inclusive_mean": _as_float(rec.get("dangerous_count_inclusive_mean", 0.0)),
                "dangerous_count_inclusive_median": _as_float(rec.get("dangerous_count_inclusive_median", 0.0)),
                "dangerous_count_unknown_component_mean": _as_float(
                    rec.get("dangerous_count_unknown_component_mean", 0.0)
                ),
                "unknown_protection_rate": _as_float(rec.get("unknown_protection_rate", 0.0)),
                "total_perm_count_mean": _as_float(rec.get("total_perm_count_mean", 0.0)),
                "total_perm_count_median": _as_float(rec.get("total_perm_count_median", 0.0)),
                "permission_source_aosp_rate": _as_float(rec.get("permission_source_aosp_rate", 0.0)),
                "permission_source_oem_rate": _as_float(rec.get("permission_source_oem_rate", 0.0)),
                "permission_source_app_defined_rate": _as_float(
                    rec.get("permission_source_app_defined_rate", 0.0)
                ),
                "permission_source_unknown_rate": _as_float(rec.get("permission_source_unknown_rate", 0.0)),
            }
        )
    _bulk_upsert("dangerous_distribution_by_type", rows, unique_keys=["run_id", "type_slug"])


def _persist_type_prevalence(type_prevalence_df: pd.DataFrame) -> None:
    if type_prevalence_df.empty:
        return
    rows = []
    for _, rec in type_prevalence_df.iterrows():
        rows.append(
            {
                "run_id": _as_str(rec.get("run_id")),
                "type_slug": _as_str(rec.get("type_slug")),
                "permission_string": _as_str(rec.get("permission")),
                "prevalence": _as_float(rec.get("prevalence", 0.0)),
                "sample_count": _as_int(rec.get("sample_count", 0)),
            }
        )
    _bulk_upsert("type_permission_prevalence", rows, unique_keys=["run_id", "type_slug", "permission_string"])


def _persist_family_profiles(family_profiles_df: pd.DataFrame) -> None:
    if family_profiles_df.empty:
        return
    rows = []
    for _, rec in family_profiles_df.iterrows():
        rows.append(
            {
                "run_id": _as_str(rec.get("run_id")),
                "family_id": _as_int(rec.get("family_id", 0)),
                "family_canonical": _as_str(rec.get("family_canonical")),
                "profile_scope": _as_str(rec.get("profile_scope")),
                "permission_string": _as_str(rec.get("permission")),
                "prevalence": _as_float(rec.get("prevalence", 0.0)),
                "sample_count": _as_int(rec.get("sample_count", 0)),
            }
        )
    _bulk_upsert(
        "family_permission_profile",
        rows,
        unique_keys=["run_id", "family_id", "profile_scope", "permission_string"],
    )


def _persist_group_entropy(
    run_id: str,
    type_entropy_df: pd.DataFrame,
    family_entropy_df: pd.DataFrame,
) -> None:
    rows = []
    if not type_entropy_df.empty:
        for _, rec in type_entropy_df.iterrows():
            rows.append(
                {
                    "run_id": run_id,
                    "group_type": "type",
                    "group_key": _as_str(rec.get("type_slug")),
                    "sample_count": _as_int(rec.get("sample_count", 0)),
                    "permission_entropy": _as_float(rec.get("permission_entropy", 0.0)),
                    "effective_diversity": _as_float(rec.get("effective_diversity", 0.0)),
                }
            )
    if not family_entropy_df.empty:
        for _, rec in family_entropy_df.iterrows():
            rows.append(
                {
                    "run_id": run_id,
                    "group_type": "family",
                    "group_key": str(_as_int(rec.get("family_id", 0))),
                    "sample_count": _as_int(rec.get("sample_count", 0)),
                    "permission_entropy": _as_float(rec.get("permission_entropy", 0.0)),
                    "effective_diversity": _as_float(rec.get("effective_diversity", 0.0)),
                }
            )
    _bulk_upsert("group_permission_entropy", rows, unique_keys=["run_id", "group_type", "group_key"])


def _persist_family_jsd(jsd_df: pd.DataFrame) -> None:
    if jsd_df.empty:
        return
    rows = []
    for _, rec in jsd_df.iterrows():
        rows.append(
            {
                "run_id": _as_str(rec.get("run_id")),
                "family_a": _as_str(rec.get("family_canonical")),
                "family_b": _as_str(rec.get("other")),
                "js_distance": _as_float(rec.get("js_distance", 0.0)),
            }
        )
    _bulk_upsert("family_jsd_matrix", rows, unique_keys=["run_id", "family_a", "family_b"])


def _persist_banker_enrichment(banker_enrichment_df: pd.DataFrame) -> None:
    if banker_enrichment_df.empty:
        return
    rows = []
    for _, rec in banker_enrichment_df.iterrows():
        rows.append(
            {
                "run_id": _as_str(rec.get("run_id")),
                "permission_string": _as_str(rec.get("permission")),
                "banker_with_perm": _as_int(rec.get("banker_with_perm", 0)),
                "banker_without_perm": _as_int(rec.get("banker_without_perm", 0)),
                "non_banker_with_perm": _as_int(rec.get("non_banker_with_perm", 0)),
                "non_banker_without_perm": _as_int(rec.get("non_banker_without_perm", 0)),
                "odds_ratio": _as_float(rec.get("odds_ratio", 0.0)),
                "odds_ratio_ci_low": _as_float(rec.get("odds_ratio_ci_low", 0.0)),
                "odds_ratio_ci_high": _as_float(rec.get("odds_ratio_ci_high", 0.0)),
                "p_value": _as_float(rec.get("p_value", 1.0)),
                "p_value_fdr_bh": _as_float(rec.get("p_value_fdr_bh", 1.0)),
                "cramers_v": _as_float(rec.get("cramers_v", 0.0)),
                "forced_permission_flag": _as_int(rec.get("forced_permission_flag", 0)),
            }
        )
    _bulk_upsert("banker_permission_enrichment", rows, unique_keys=["run_id", "permission_string"])


def _persist_discriminability(discriminability_df: pd.DataFrame) -> None:
    if discriminability_df.empty:
        return
    rows = []
    for _, rec in discriminability_df.iterrows():
        rows.append(
            {
                "run_id": _as_str(rec.get("run_id")),
                "permission_string": _as_str(rec.get("permission")),
                "chi2_p_value": _as_float(rec.get("chi2_p_value", 1.0)),
                "chi2_p_value_fdr_bh": _as_float(rec.get("chi2_p_value_fdr_bh", 1.0)),
                "cramers_v": _as_float(rec.get("cramers_v", 0.0)),
                "mutual_information": _as_float(rec.get("mutual_information", 0.0)),
                "global_support": _as_int(rec.get("global_support", 0)),
            }
        )
    _bulk_upsert("permission_discriminability_rank", rows, unique_keys=["run_id", "permission_string"])


def _persist_consensus(consensus_df: pd.DataFrame) -> None:
    if consensus_df.empty:
        return
    rows = []
    for _, rec in consensus_df.iterrows():
        sha256 = _as_str(rec.get("sha256")).lower()
        if len(sha256) != 64:
            continue
        rows.append(
            {
                "run_id": _as_str(rec.get("run_id")),
                "sha256": sha256,
                "sample_id": _as_int(rec.get("sample_id", 0)),
                "family_id": _nullable_int(rec.get("family_id")),
                "type_slug": _as_str(rec.get("type_slug")),
                "vendor_count": _as_int(rec.get("vendor_count", 0)),
                "top1_vote_share": _as_float(rec.get("top1_vote_share", 0.0)),
                "top2_vote_share": _as_float(rec.get("top2_vote_share", 0.0)),
                "top1_minus_top2_gap": _as_float(rec.get("top1_minus_top2_gap", 0.0)),
                "consensus_score_all_vendors": _as_float(rec.get("consensus_score_all_vendors", 0.0)),
                "consensus_entropy_all_vendors": _as_float(rec.get("consensus_entropy_all_vendors", 0.0)),
                "consensus_score_gated_vendors": _as_float(rec.get("consensus_score_gated_vendors", 0.0)),
                "consensus_entropy_gated_vendors": _as_float(rec.get("consensus_entropy_gated_vendors", 0.0)),
                "low_vendor_count_flag": _as_int(rec.get("low_vendor_count_flag", 0)),
            }
        )
    _bulk_upsert("consensus_distribution", rows, unique_keys=["run_id", "sha256"])


def _persist_per_family_spread(per_family_perf_df: pd.DataFrame) -> None:
    if per_family_perf_df.empty:
        return
    rows = []
    for _, rec in per_family_perf_df.iterrows():
        support = _as_int(rec.get("support", 0))
        rows.append(
            {
                "run_id": _as_str(rec.get("run_id")),
                "family_id": _as_int(rec.get("family_id", 0)),
                "family_canonical": _as_str(rec.get("family_canonical")),
                "type_slug": _as_str(rec.get("type_slug")),
                "support": support,
                "precision_val": _as_float(rec.get("precision", 0.0)),
                "recall_val": _as_float(rec.get("recall", 0.0)),
                "f1_val": _as_float(rec.get("f1_score", 0.0)),
                "avg_confidence": _as_float(rec.get("avg_confidence", 0.0)),
                "unstable_flag": 1 if support < 30 else 0,
            }
        )
    _bulk_upsert("per_family_performance_spread", rows, unique_keys=["run_id", "family_id"])


def _persist_ablation_summary(run_id: str, vendor_constrained_run_flag: int) -> None:
    path = _diagnostics_dir() / f"ablation_summary_{run_id}.csv"
    if not path.exists():
        return
    try:
        df = pd.read_csv(path)
    except Exception:
        return
    if df.empty:
        return
    rows = []
    for _, rec in df.iterrows():
        rows.append(
            {
                "run_id": run_id,
                "model_name": _as_str(rec.get("model")),
                "ablation_variant": _as_str(rec.get("experiment")),
                "macro_f1": _as_float(rec.get("macro_f1_score", 0.0)),
                "weighted_f1": None,
                "accuracy": _as_float(rec.get("accuracy", 0.0)),
                "vendor_constrained_run_flag": _as_int(vendor_constrained_run_flag),
                "notes": f"leakage_sensitivity_delta={_as_float(rec.get('leakage_sensitivity_delta', 0.0))}",
            }
        )
    _bulk_upsert("ablation_summary", rows, unique_keys=["run_id", "model_name", "ablation_variant"])


def _persist_artifacts(run_id: str, artifact_paths: list[str]) -> None:
    if not artifact_paths:
        return
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows = []
    seen: set[str] = set()
    for path_str in artifact_paths:
        if not path_str or path_str in seen:
            continue
        seen.add(path_str)
        path = Path(path_str)
        key = _artifact_key(path_str)
        rows.append(
            {
                "run_id": run_id,
                "artifact_key": key,
                "artifact_path": str(path),
                "artifact_sha256": _file_sha256(path) if path.exists() and path.is_file() else None,
                "created_at_utc": now_utc,
            }
        )
    _bulk_upsert("analysis_artifact", rows, unique_keys=["run_id", "artifact_key"])


def _persist_type_prevalence_by_view(df: pd.DataFrame | None) -> None:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return
    rows = []
    for _, rec in df.iterrows():
        rows.append(
            {
                "run_id": _as_str(rec.get("run_id")),
                "type_slug": _as_str(rec.get("type_slug")),
                "permission_string": _as_str(rec.get("permission")),
                "view_mode": _as_str(rec.get("view_mode") or "unknown"),
                "prevalence": _as_float(rec.get("prevalence", 0.0)),
                "sample_count": _as_int(rec.get("sample_count", 0)),
            }
        )
    _bulk_upsert(
        "type_permission_prevalence_by_view",
        rows,
        unique_keys=["run_id", "type_slug", "permission_string", "view_mode"],
    )


def _persist_family_profiles_by_view(df: pd.DataFrame | None) -> None:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return
    rows = []
    for _, rec in df.iterrows():
        rows.append(
            {
                "run_id": _as_str(rec.get("run_id")),
                "family_id": _as_int(rec.get("family_id", 0)),
                "family_canonical": _as_str(rec.get("family_canonical")),
                "profile_scope": _as_str(rec.get("profile_scope")),
                "permission_string": _as_str(rec.get("permission")),
                "view_mode": _as_str(rec.get("view_mode") or "unknown"),
                "prevalence": _as_float(rec.get("prevalence", 0.0)),
                "sample_count": _as_int(rec.get("sample_count", 0)),
            }
        )
    _bulk_upsert(
        "family_permission_profile_by_view",
        rows,
        unique_keys=["run_id", "family_id", "profile_scope", "permission_string", "view_mode"],
    )


def _persist_group_entropy_by_view(df: pd.DataFrame | None) -> None:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return
    rows = []
    for _, rec in df.iterrows():
        rows.append(
            {
                "run_id": _as_str(rec.get("run_id")),
                "group_type": _as_str(rec.get("group_type")),
                "group_key": _as_str(rec.get("group_key")),
                "view_mode": _as_str(rec.get("view_mode") or "unknown"),
                "sample_count": _as_int(rec.get("sample_count", 0)),
                "permission_entropy": _as_float(rec.get("permission_entropy", 0.0)),
                "effective_diversity": _as_float(rec.get("effective_diversity", 0.0)),
            }
        )
    _bulk_upsert(
        "group_permission_entropy_by_view",
        rows,
        unique_keys=["run_id", "group_type", "group_key", "view_mode"],
    )


def _persist_family_jsd_by_view(df: pd.DataFrame | None) -> None:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return
    rows = []
    for _, rec in df.iterrows():
        rows.append(
            {
                "run_id": _as_str(rec.get("run_id")),
                "family_a": _as_str(rec.get("family_canonical")),
                "family_b": _as_str(rec.get("other")),
                "view_mode": _as_str(rec.get("view_mode") or "unknown"),
                "js_distance": _as_float(rec.get("js_distance", 0.0)),
            }
        )
    _bulk_upsert(
        "family_jsd_matrix_by_view",
        rows,
        unique_keys=["run_id", "family_a", "family_b", "view_mode"],
    )


def _persist_banker_enrichment_by_view(df: pd.DataFrame | None) -> None:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return
    rows = []
    for _, rec in df.iterrows():
        rows.append(
            {
                "run_id": _as_str(rec.get("run_id")),
                "permission_string": _as_str(rec.get("permission")),
                "view_mode": _as_str(rec.get("view_mode") or "unknown"),
                "banker_with_perm": _as_int(rec.get("banker_with_perm", 0)),
                "banker_without_perm": _as_int(rec.get("banker_without_perm", 0)),
                "non_banker_with_perm": _as_int(rec.get("non_banker_with_perm", 0)),
                "non_banker_without_perm": _as_int(rec.get("non_banker_without_perm", 0)),
                "odds_ratio": _as_float(rec.get("odds_ratio", 0.0)),
                "odds_ratio_ci_low": _as_float(rec.get("odds_ratio_ci_low", 0.0)),
                "odds_ratio_ci_high": _as_float(rec.get("odds_ratio_ci_high", 0.0)),
                "p_value": _as_float(rec.get("p_value", 1.0)),
                "p_value_fdr_bh": _as_float(rec.get("p_value_fdr_bh", 1.0)),
                "cramers_v": _as_float(rec.get("cramers_v", 0.0)),
                "forced_permission_flag": _as_int(rec.get("forced_permission_flag", 0)),
            }
        )
    _bulk_upsert(
        "banker_permission_enrichment_by_view",
        rows,
        unique_keys=["run_id", "permission_string", "view_mode"],
    )


def _persist_discriminability_by_view(df: pd.DataFrame | None) -> None:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return
    rows = []
    for _, rec in df.iterrows():
        rows.append(
            {
                "run_id": _as_str(rec.get("run_id")),
                "permission_string": _as_str(rec.get("permission")),
                "view_mode": _as_str(rec.get("view_mode") or "unknown"),
                "chi2_p_value": _as_float(rec.get("chi2_p_value", 1.0)),
                "chi2_p_value_fdr_bh": _as_float(rec.get("chi2_p_value_fdr_bh", 1.0)),
                "cramers_v": _as_float(rec.get("cramers_v", 0.0)),
                "mutual_information": _as_float(rec.get("mutual_information", 0.0)),
                "global_support": _as_int(rec.get("global_support", 0)),
            }
        )
    _bulk_upsert(
        "permission_discriminability_rank_by_view",
        rows,
        unique_keys=["run_id", "permission_string", "view_mode"],
    )


def _persist_family_cohesion(run_id: str, family_entropy_df: pd.DataFrame) -> None:
    """Persist family-level cohesion metrics derived from entropy."""
    if not isinstance(family_entropy_df, pd.DataFrame) or family_entropy_df.empty:
        return
    rows = []
    for _, rec in family_entropy_df.iterrows():
        support = _as_int(rec.get("sample_count", 0))
        rows.append(
            {
                "run_id": run_id,
                "family_id": _as_int(rec.get("family_id", 0)),
                "family_canonical": _as_str(rec.get("family_canonical")),
                "sample_count": support,
                "permission_entropy": _as_float(rec.get("permission_entropy", 0.0)),
                "effective_diversity": _as_float(rec.get("effective_diversity", 0.0)),
                "unstable_flag": 1 if support < 30 else 0,
            }
        )
    _bulk_upsert("family_permission_cohesion", rows, unique_keys=["run_id", "family_id"])


def _persist_banker_family_heterogeneity(
    run_id: str,
    assignments_df: pd.DataFrame | None,
    cluster_profiles_df: pd.DataFrame | None,
) -> None:
    """Persist banker family cluster assignment and cluster top-permission summaries."""
    if not isinstance(assignments_df, pd.DataFrame) or assignments_df.empty:
        return
    top_permissions_by_cluster: dict[int, list[str]] = {}
    if isinstance(cluster_profiles_df, pd.DataFrame) and not cluster_profiles_df.empty:
        tmp = cluster_profiles_df.copy()
        tmp["cluster_id"] = pd.to_numeric(tmp.get("cluster_id"), errors="coerce").fillna(-1).astype(int)
        for cluster_id, group in tmp.groupby("cluster_id", dropna=False):
            ordered = group.sort_values("mean_prevalence", ascending=False)
            top_permissions_by_cluster[int(cluster_id)] = (
                ordered["permission"].astype(str).head(10).tolist()
            )
    rows = []
    for _, rec in assignments_df.iterrows():
        cluster_id = _as_int(rec.get("cluster_id", -1))
        rows.append(
            {
                "run_id": run_id,
                "family_id": _as_int(rec.get("family_id", 0)),
                "family_canonical": _as_str(rec.get("family_canonical")),
                "sample_count": _as_int(rec.get("sample_count", 0)),
                "cluster_id": cluster_id,
                "top_permissions_json": json.dumps(top_permissions_by_cluster.get(cluster_id, [])),
            }
        )
    _bulk_upsert("banker_permission_family_heterogeneity", rows, unique_keys=["run_id", "family_id"])


def _persist_temporal_trends(df: pd.DataFrame | None) -> None:
    """Persist banker temporal trend series."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return
    rows = []
    for _, rec in df.iterrows():
        rows.append(
            {
                "run_id": _as_str(rec.get("run_id")),
                "period_quarter": _as_str(rec.get("period_quarter")),
                "year": _as_int(rec.get("year", 0)),
                "quarter": _as_int(rec.get("quarter", 0)),
                "sample_count": _as_int(rec.get("sample_count", 0)),
                "banker_sample_count": _as_int(rec.get("banker_sample_count", 0)),
                "dangerous_count_strict_mean_all": _sql_nullable_float(rec.get("dangerous_count_strict_mean_all")),
                "dangerous_count_strict_mean_banker": _sql_nullable_float(
                    rec.get("dangerous_count_strict_mean_banker")
                ),
                "banker_bind_accessibility_service_prevalence": _sql_nullable_float(
                    rec.get("banker_bind_accessibility_service_prevalence")
                ),
                "banker_system_alert_window_prevalence": _sql_nullable_float(
                    rec.get("banker_system_alert_window_prevalence")
                ),
                "banker_request_install_packages_prevalence": _sql_nullable_float(
                    rec.get("banker_request_install_packages_prevalence")
                ),
                "banker_read_sms_prevalence": _sql_nullable_float(rec.get("banker_read_sms_prevalence")),
                "banker_receive_sms_prevalence": _sql_nullable_float(rec.get("banker_receive_sms_prevalence")),
                "banker_send_sms_prevalence": _sql_nullable_float(rec.get("banker_send_sms_prevalence")),
            }
        )
    _bulk_upsert("banker_permission_trends_over_time", rows, unique_keys=["run_id", "period_quarter"])


def _bulk_upsert(table: str, rows: list[dict[str, Any]], unique_keys: list[str], chunk_size: int = 500) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    update_cols = [col for col in columns if col not in set(unique_keys)]
    for idx in range(0, len(rows), chunk_size):
        chunk = rows[idx : idx + chunk_size]
        placeholders = ", ".join(["(" + ", ".join(["%s"] * len(columns)) + ")"] * len(chunk))
        updates = ", ".join([f"`{col}`=VALUES(`{col}`)" for col in update_cols])
        sql = (
            f"INSERT INTO `{table}` ({', '.join([f'`{c}`' for c in columns])}) "
            f"VALUES {placeholders} "
            f"ON DUPLICATE KEY UPDATE {updates}"
        )
        params: list[Any] = []
        for row in chunk:
            for col in columns:
                params.append(_sql_value(row.get(col)))
        db_engine.execute_query(sql, params=tuple(params))


def _sql_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.generic,)):
        value = value.item()
    if isinstance(value, float) and np.isnan(value):
        return None
    return value


def _as_int(value: Any) -> int:
    try:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return 0
        return int(value)
    except Exception:
        return 0


def _nullable_int(value: Any) -> int | None:
    try:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return None
        return int(value)
    except Exception:
        return None


def _as_float(value: Any) -> float:
    try:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _sql_nullable_float(value: Any) -> float | None:
    """Return SQL-nullable float for optional metric fields."""
    try:
        if value is None:
            return None
        if isinstance(value, (np.generic,)):
            value = value.item()
        if isinstance(value, float) and np.isnan(value):
            return None
        return float(value)
    except Exception:
        return None


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _artifact_key(path_str: str) -> str:
    name = Path(path_str).name
    token = name.replace(" ", "_").replace(".", "_")
    if len(token) <= 120:
        return token
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
    return f"{token[:96]}_{digest}"


def _file_sha256(path: Path) -> str | None:
    try:
        h = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _safe_datetime_sql(value: str) -> str:
    """Convert ISO datetime string to SQL datetime, falling back to now UTC."""
    if value:
        normalized = value.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
