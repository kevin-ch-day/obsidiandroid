"""Permission feature extraction for sample-level modeling."""

from __future__ import annotations

import re
import hashlib
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from config import app_config
from obsidiandroid.database import db_engine
from obsidiandroid.database import permission_contracts
from obsidiandroid.database.permission_current_interpretation import (
    interpretation_joins,
    interpretation_selects,
)
from obsidiandroid.cli.ui import display as du
from obsidiandroid.orchestration.source_aware_permission_features import (
    CONTRACT_VERSION as SOURCE_AWARE_CONTRACT_VERSION,
    _build_from_verified_evidence,
    _hash_evidence_file,
)
from obsidiandroid.orchestration.recovery_receipt_evidence import (
    load_recovery_receipt_evidence,
    reconcile_provider_observations,
)
from obsidiandroid.orchestration.static_projection_evidence import (
    load_static_projection_evidence,
)
from obsidiandroid.orchestration.permission_v2_research_gate import (
    assert_legacy_observation_read_allowed,
)
from obsidiandroid.orchestration.permission_v2_export import (
    CONTRACT_VERSION as V2_EXPORT_CONTRACT_VERSION,
    build_v2_unresolved_features,
)

# Grouped permission bundles (coarse capability families; counts are per observed permission row).
PERMISSION_GROUP_DEFINITIONS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("sms_telephony_count", re.compile(r"(?:sms|telephon|mms|send_sms|receive_sms|read_sms|write_sms)", re.I)),
    ("network_c2_count", re.compile(r"(?:internet|network_state|access_network|change_network|vpn|wifi|c2|socket)", re.I)),
    (
        "persistence_autostart_count",
        re.compile(
            r"(?:boot_completed|device_admin|foreground_service|persist|install_shortcut|receive_boot|scheduled|alarm)",
            re.I,
        ),
    ),
    (
        "overlay_accessibility_count",
        re.compile(r"(?:system_alert_window|draw_overlay|accessibility|bind_accessibility)", re.I),
    ),
    (
        "storage_file_access_count",
        re.compile(
            r"(?:external_storage|manage_external|read_external|write_external|media_|documents|downloads|storage)",
            re.I,
        ),
    ),
    (
        "surveillance_sensor_count",
        re.compile(r"(?:camera|microphone|audio|record_audio|video|fine_location|access_fine|body_sensors)", re.I),
    ),
    ("account_contact_count", re.compile(r"(?:account|contacts|read_contacts|write_contacts|call_log|phone_state)", re.I)),
    ("package_inventory_count", re.compile(r"(?:package|query_all_packages|install_packages|request_install)", re.I)),
    ("oem_vendor_specific_count", re.compile(r"^com\.[a-z0-9_.]+\.permission\.", re.I)),
)

_TOKEN_PATTERN = re.compile(r"[^a-z0-9]+")
def _permission_obs_key_expr() -> str:
    """Return the SQL expression for the canonical permission grouping key.

    ``permission_string_norm`` is the governed normalized key when present in the
    live Permission Intel schema. Older fixtures or deployments may not expose it,
    so we fall back to the legacy lowercase/trim expression.
    """
    return permission_contracts.permission_obs_key_expr(alias="ops")


def augment_grouped_permission_counts(permission_df: pd.DataFrame, feature_df: pd.DataFrame) -> pd.DataFrame:
    """Attach ``perm_grp__*`` aggregate counts derived from raw permission rows.

    The previous implementation iterated every sample and every regular
    expression in Python.  A current-corpus run has thousands of samples, so
    this vectorized form keeps the same per-row count semantics while grouping
    only the rows that match each capability pattern.
    """
    if permission_df.empty or feature_df.empty:
        return feature_df
    if "sample_id" not in permission_df.columns or "permission_string" not in permission_df.columns:
        return feature_df

    work = permission_df.copy()
    work["permission_string"] = work["permission_string"].fillna("").astype(str).str.strip().str.lower()
    work = work[work["permission_string"] != ""]
    if work.empty:
        return feature_df

    wide = feature_df.copy()
    if "sample_id" not in wide.columns:
        return feature_df
    sample_ids = sorted({int(x) for x in wide["sample_id"].tolist() if pd.notna(x)})
    base_idx = pd.Index(sample_ids, name="sample_id")
    if base_idx.empty:
        return wide
    work["_sample_id_int"] = pd.to_numeric(work["sample_id"], errors="coerce")
    work = work[work["_sample_id_int"].notna()].copy()
    work["_sample_id_int"] = work["_sample_id_int"].astype(int)
    work = work[work["_sample_id_int"].isin(base_idx)]
    if work.empty:
        return wide

    agg = pd.DataFrame(index=base_idx)
    permission_text = work["permission_string"]
    for group_name, pattern in PERMISSION_GROUP_DEFINITIONS:
        matched_ids = work.loc[
            permission_text.str.contains(pattern, na=False), "_sample_id_int"
        ]
        counts = matched_ids.value_counts().reindex(base_idx, fill_value=0)
        agg[f"perm_grp__{group_name}"] = counts.to_numpy(dtype=int)

    agg = agg.reset_index()
    merged = wide.merge(agg, on="sample_id", how="left")
    grp_cols = [c for c in merged.columns if c.startswith("perm_grp__")]
    for col in grp_cols:
        merged[col] = pd.to_numeric(merged[col], errors="coerce").fillna(0).astype(int)
    return merged


def _sanitize_permission_name(permission: str) -> str:
    token = _TOKEN_PATTERN.sub("_", str(permission).strip().lower()).strip("_")
    return token or "unknown_permission"


def _iter_chunks(values: list[int], chunk_size: int = 500) -> Iterable[list[int]]:
    for idx in range(0, len(values), chunk_size):
        yield values[idx : idx + chunk_size]


def _fetch_permission_rows(sample_ids: list[int]) -> pd.DataFrame:
    if not sample_ids:
        return pd.DataFrame()

    # Never degrade a governance refusal to an empty feature frame. The
    # observation table can receive recovered rows without any v1 current-row
    # change, so this check must precede the legacy feature query.
    assert_legacy_observation_read_allowed()

    frames = []
    for chunk in _iter_chunks(sample_ids):
        placeholders = ", ".join(["%s"] * len(chunk))
        permission_key_expr = _permission_obs_key_expr()
        oem_join = permission_contracts.oem_dictionary_join_predicate(
            observation_alias="ops",
            oem_alias="o",
        )
        interpretation = interpretation_selects(
            historical_source_expr="UPPER(COALESCE(ops.classification, 'UNKNOWN'))",
            raw_expr="ops.permission_string",
        )
        interpretation_sql = interpretation_joins(
            key_expr=permission_key_expr,
            raw_expr="ops.permission_string",
        )
        query = f"""
            SELECT
                ops.sample_id,
                ops.permission_string AS permission_string_raw,
                {permission_key_expr} AS permission_string,
                {interpretation['historical_permission_source']} AS historical_permission_source,
                {interpretation['permission_source']} AS permission_source,
                UPPER(COALESCE(
                    ({interpretation['safe_protection_expression']}),
                    o.protection_level,
                    'UNKNOWN'
                )) AS protection_level,
                {interpretation['current_authority_scope']} AS current_authority_scope,
                {interpretation['current_identifier_kind']} AS current_identifier_kind,
                {interpretation['current_declaration_state']} AS current_declaration_state,
                {interpretation['current_evidence_state']} AS current_evidence_state,
                {interpretation['current_feature_dependency']} AS current_feature_dependency
            FROM android_permission_obs_sample ops
            {interpretation_sql}
            LEFT JOIN android_permission_dict_oem o
                ON {oem_join}
            WHERE ops.sample_id IN ({placeholders})
              AND ops.permission_string IS NOT NULL
              AND TRIM(ops.permission_string) <> ''
        """
        try:
            frame = db_engine.execute_permission_query(
                query,
                params=tuple(chunk),
                fetch=True,
                as_dataframe=True,
            )
        except Exception as exc:  # pylint: disable=broad-except
            setattr(app_config, "RUNTIME_PERMISSION_ENRICHMENT_DEGRADED", True)
            strict_in_evidence = bool(
                getattr(app_config, "PERMISSION_ENRICHMENT_STRICT_IN_EVIDENCE", False)
            )
            evidence_mode = bool(getattr(app_config, "RUNTIME_EVIDENCE_MODE", False))
            if strict_in_evidence and evidence_mode:
                raise RuntimeError(
                    "[INTEGRITY] Permission enrichment DB fetch failed in evidence mode: "
                    f"{exc}"
                ) from exc
            du.print_warning(
                "[PERMISSIONS] Failed to fetch permission rows; "
                f"continuing without permission enrichment ({exc})."
            )
            return pd.DataFrame()
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            frames.append(frame)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _fetch_source_aware_permission_rows(sample_ids: list[int]) -> pd.DataFrame:
    """Read PI observation origin and exact VT event lineage without writes."""
    assert_legacy_observation_read_allowed()
    frames: list[pd.DataFrame] = []
    for chunk in _iter_chunks(sample_ids):
        placeholders = ", ".join(["%s"] * len(chunk))
        interpretation_sql = interpretation_joins(
            key_expr=_permission_obs_key_expr(), raw_expr="ops.permission_string"
        )
        query = f"""
            SELECT ops.sample_id, ops.permission_string,
                   ops.source AS observation_source,
                   ops.classification_recovery_plan_core_sha256 AS recovery_plan_core,
                   ops.classification_recovery_batch_id AS recovery_batch_id,
                   DATE_FORMAT(vte.vt_analysis_date_utc, '%Y-%m-%dT%H:%i:%SZ')
                       AS event_analysis_date_utc,
                   vte.source_system AS event_source_system,
                   vte.source_engine AS event_source_engine,
                   pi.canonical_permission,
                   CASE WHEN pi.identity_status = 'ACCEPTED'
                              AND BINARY pi.source_provenance_status = BINARY 'PRESENT'
                              AND pi.feature_dependency IS NULL
                              AND COALESCE(pic.unresolved_conflict_count, 0) = 0
                              AND COALESCE(pi.lifecycle, '') NOT IN
                                  ('historical', 'legacy_removed', 'removed')
                        THEN 'ACCEPTED_CANONICAL'
                        ELSE 'UNRESOLVED' END AS current_evidence_state,
                   CASE WHEN pi.identity_status = 'ACCEPTED' THEN 'PERMISSION'
                        ELSE 'UNKNOWN' END AS current_identifier_kind,
                   COALESCE(pic.unresolved_conflict_count, 0) AS unresolved_conflict_count
              FROM android_permission_obs_sample ops
              {interpretation_sql}
              LEFT JOIN android_permission_enrich_vt_event vte
                ON vte.sample_id = ops.sample_id
               AND vte.permission_string_bin_sha256 = ops.permission_string_bin_sha256
               AND BINARY vte.permission_string = BINARY ops.permission_string
               AND vte.source_system = 'virustotal'
               AND vte.source_engine = 'androguard'
             WHERE ops.sample_id IN ({placeholders})
        """
        frame = db_engine.execute_permission_query(
            query, params=tuple(chunk), fetch=True, as_dataframe=True
        )
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_permission_feature_frame(
    samples_df: pd.DataFrame,
    min_permission_support: int = 2,
    max_permission_features: int | None = None,
    *,
    feature_contract_version: str = "legacy",
    source_aware_evidence: pd.DataFrame | None = None,
    training_sample_ids: Iterable[int] | None = None,
    recovery_plan_path: Path | None = None,
    recovery_receipt_directory: Path | None = None,
    expected_recovery_plan_digest: str | None = None,
    expected_recovery_manifest_digest: str | None = None,
    expected_recovery_selection_digest: str | None = None,
    manifest_projection_paths: Iterable[Path] | None = None,
    manifest_baseline_paths_by_sha: dict[str, Path] | None = None,
    expected_manifest_projection_digests_by_sha: dict[str, str] | None = None,
    accepted_aliases: dict[tuple[str, str], str] | None = None,
    v2_export_path: Path | None = None,
) -> pd.DataFrame:
    """Build per-sample permission features from observed permission table.

    Args:
        samples_df: Cohort samples containing ``sample_id``.
        min_permission_support: Minimum sample support to keep a permission token.
        max_permission_features: Optional cap for bag-of-words permission columns.

    Returns:
        DataFrame with ``sample_id`` plus permission-derived features.
    """
    setattr(app_config, "RUNTIME_PERMISSION_ENRICHMENT_DEGRADED", False)
    if feature_contract_version == V2_EXPORT_CONTRACT_VERSION:
        if v2_export_path is None or training_sample_ids is None:
            raise ValueError("PI V2 requires export path and frozen training membership")
        if (source_aware_evidence is not None or recovery_plan_path is not None
            or manifest_projection_paths is not None or accepted_aliases):
            raise ValueError("PI V2 export cannot be mixed with caller or legacy evidence")
        return build_v2_unresolved_features(
            samples_df, v2_export_path, training_sample_ids=training_sample_ids,
            min_support=min_permission_support)
    if feature_contract_version == SOURCE_AWARE_CONTRACT_VERSION:
        if training_sample_ids is None:
            raise ValueError(
                "source-aware v1 requires training membership"
            )
        if source_aware_evidence is not None:
            raise ValueError("caller-supplied source-aware DataFrames are untrusted")
        evidence_parts: list[pd.DataFrame] = []
        source_paths: list[Path] = []
        if recovery_plan_path and recovery_receipt_directory and expected_recovery_plan_digest:
            source_paths.extend([recovery_plan_path, *sorted(recovery_receipt_directory.glob(
                "pi-production-sample-*.json"))])
        if manifest_projection_paths is not None:
            manifest_projection_paths = list(manifest_projection_paths)
            source_paths.extend(manifest_projection_paths)
            source_paths.extend((manifest_baseline_paths_by_sha or {}).values())
        if not source_paths:
            raise ValueError("source-aware evidence requires retained source files")

        def bindings() -> tuple[tuple[str, str], ...]:
            return tuple(sorted((str(path.resolve(strict=True)),
                                 _hash_evidence_file(path))
                                for path in source_paths))

        def directories() -> tuple[tuple[str, tuple[str, ...]], ...]:
            if recovery_receipt_directory is None:
                return ()
            return ((str(recovery_receipt_directory.resolve(strict=True)),
                     tuple(sorted(path.name for path in recovery_receipt_directory.glob(
                         "pi-production-sample-*.json")))),)

        before_bindings = bindings()
        before_directories = directories()
        if recovery_plan_path and recovery_receipt_directory and expected_recovery_plan_digest:
            receipt_rows = load_recovery_receipt_evidence(
                recovery_plan_path, recovery_receipt_directory,
                expected_plan_digest=expected_recovery_plan_digest,
                expected_manifest_digest=expected_recovery_manifest_digest,
                expected_selection_digest=expected_recovery_selection_digest,
            )
            pi_rows = _fetch_source_aware_permission_rows(
                sorted(set(int(value) for value in samples_df["sample_id"]))
            )
            provider_evidence = reconcile_provider_observations(
                samples_df, pi_rows, receipt_rows
            ) if not pi_rows.empty else pd.DataFrame(columns=[
                "sample_id", "sha256", "raw_token", "projected_token",
                "observation_origin", "source_verified", "identity_status",
                "source_receipt_digest", "event_verified", "canonical_token",
                "alias_release_digest",
            ])
            evidence_parts.append(provider_evidence)
        if manifest_projection_paths is not None:
            if (manifest_baseline_paths_by_sha is None
                    or expected_manifest_projection_digests_by_sha is None):
                raise ValueError("static projection baseline paths and reviewed digests are required")
            evidence_parts.append(load_static_projection_evidence(
                samples_df, list(manifest_projection_paths),
                baseline_paths_by_sha=manifest_baseline_paths_by_sha,
                expected_projection_digests_by_sha=expected_manifest_projection_digests_by_sha,
            ))
        if not evidence_parts:
            raise ValueError(
                "source-aware v1 requires receipt-checked evidence and training membership"
            )
        if before_bindings != bindings() or before_directories != directories():
            raise ValueError("source-aware evidence changed during verification")
        source_aware_evidence = pd.concat(evidence_parts, ignore_index=True)
        source_snapshot_digest = hashlib.sha256(json.dumps({
            "files": before_bindings,
            "directories": before_directories,
            "rows": source_aware_evidence.to_json(orient="split", index=False),
            "plan": expected_recovery_plan_digest,
            "manifest": expected_recovery_manifest_digest,
            "selection": expected_recovery_selection_digest,
        }, sort_keys=True).encode()).hexdigest()
        return _build_from_verified_evidence(
            samples_df,
            source_aware_evidence,
            training_sample_ids=training_sample_ids,
            min_support=min_permission_support,
            accepted_aliases=accepted_aliases,
            source_snapshot_digest=source_snapshot_digest,
            source_file_bindings=before_bindings,
            source_directory_memberships=before_directories,
        )
    if feature_contract_version != "legacy":
        raise ValueError("unknown permission feature contract")
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return pd.DataFrame()
    if "sample_id" not in samples_df.columns:
        return pd.DataFrame()

    sample_ids = sorted(
        {
            int(float(sample_id))
            for sample_id in samples_df["sample_id"].tolist()
            if pd.notna(sample_id)
        }
    )
    permission_df = _fetch_permission_rows(sample_ids)
    feature_df = pd.DataFrame({"sample_id": sample_ids})
    if permission_df.empty:
        return feature_df

    permission_df["sample_id"] = pd.to_numeric(permission_df["sample_id"], errors="coerce").fillna(-1).astype(int)
    permission_df["permission_string"] = (
        permission_df["permission_string"].fillna("").astype(str).str.strip().str.lower()
    )
    permission_df = permission_df[permission_df["permission_string"] != ""]
    if permission_df.empty:
        return feature_df

    permission_counts = permission_df.groupby("permission_string")["sample_id"].nunique()
    keep_permissions = permission_counts[permission_counts >= int(min_permission_support)].sort_values(ascending=False)
    if max_permission_features is not None and int(max_permission_features) > 0:
        keep_permissions = keep_permissions.head(int(max_permission_features))
    keep_tokens = set(keep_permissions.index.tolist())

    bow_df = permission_df[permission_df["permission_string"].isin(keep_tokens)]
    if not bow_df.empty:
        bow = pd.crosstab(bow_df["sample_id"], bow_df["permission_string"])
        bow = (bow > 0).astype(int)
        bow.columns = [f"perm__{_sanitize_permission_name(col)}" for col in bow.columns]
        bow = bow.reset_index()
        feature_df = feature_df.merge(bow, on="sample_id", how="left")

    protection = permission_df["protection_level"].fillna("UNKNOWN").astype(str).str.upper()
    permission_df["is_dangerous"] = protection.str.contains("DANGEROUS", regex=False).astype(int)
    permission_df["is_normal"] = protection.str.contains("NORMAL", regex=False).astype(int)

    source = permission_df["permission_source"].fillna("UNKNOWN").astype(str).str.upper()
    permission_df["is_oem"] = source.eq("OEM").astype(int)

    counts = (
        permission_df.groupby("sample_id")
        .agg(
            perm__dangerous_count=("is_dangerous", "sum"),
            perm__normal_count=("is_normal", "sum"),
            perm__oem_count=("is_oem", "sum"),
            perm__total_count=("permission_string", "count"),
        )
        .reset_index()
    )
    feature_df = feature_df.merge(counts, on="sample_id", how="left")

    for col in feature_df.columns:
        if col == "sample_id":
            continue
        feature_df[col] = pd.to_numeric(feature_df[col], errors="coerce").fillna(0).astype(int)

    out = feature_df.drop_duplicates("sample_id")
    return augment_grouped_permission_counts(permission_df, out)
