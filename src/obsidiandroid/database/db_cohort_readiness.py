"""Read-only cohort-readiness summary for split Erebus + Permission Intel routing."""

from __future__ import annotations

import math
from typing import Any

from . import db_engine
from . import schema_map
from .db_config import DB_NAME, PERMISSION_INTEL_DB_NAME
from obsidiandroid.labeling.taxonomy import is_known_family_name

from .db_family_mapping_debt import fetch_blank_resolved_family_lane_counts

_PRIMARY_CATALOG_TABLE = "malware_sample_catalog"
_VT_CONFIDENCE_TABLE = "vt_sample_verdict_confidence_current"
_PERMISSION_OBS_TABLE = "android_permission_obs_sample"
_ANDROID_AUTHORITY_VIEW = "v_android_sample_family_type_authority"
_ANDROID_FAMILY_RESOLVED_VIEW = "v_android_apk_family_resolved"
_ANDROID_FAMILY_TABLE = "android_malware_family"
_ANDROID_TYPE_TABLE = "android_malware_type"
_GENERIC_TOKEN_TABLE = "vendor_label_generic_token_fact"
_FP_SUPPRESSION_TABLE = "vt_false_positive_suppression_rule"
_VT_VENDOR_VERDICTS_TABLE = "virustotal_sample_vendor_verdicts"

_SMS_SIGNAL_PERMISSIONS = {
    "android.permission.read_sms",
    "android.permission.receive_sms",
    "android.permission.send_sms",
    "android.permission.receive_mms",
}
_TELEPHONY_SIGNAL_PERMISSIONS = {
    "android.permission.read_contacts",
    "android.permission.read_phone_numbers",
    "android.permission.read_phone_state",
    "android.permission.call_phone",
    "android.permission.read_profile",
}
_OVERLAY_SIGNAL_PERMISSIONS = {
    "android.permission.system_alert_window",
    "android.permission.query_all_packages",
    "android.permission.request_install_packages",
    "android.permission.request_ignore_battery_optimizations",
    "android.permission.use_full_screen_intent",
    "android.permission.write_settings",
    "android.permission.disable_keyguard",
    "android.permission.turn_screen_on",
}
_REMOTE_CONTROL_SIGNAL_PERMISSIONS = {
    "android.permission.media_projection",
    "android.permission.record_audio",
    "android.permission.camera",
}
_SURVEILLANCE_SIGNAL_PERMISSIONS = {
    "android.permission.access_coarse_location",
    "android.permission.access_fine_location",
    "android.permission.access_coarse_updates",
    "android.permission.get_accounts",
}
_PERMISSION_SIGNAL_PERMISSIONS = (
    _SMS_SIGNAL_PERMISSIONS
    | _TELEPHONY_SIGNAL_PERMISSIONS
    | _OVERLAY_SIGNAL_PERMISSIONS
    | _REMOTE_CONTROL_SIGNAL_PERMISSIONS
    | _SURVEILLANCE_SIGNAL_PERMISSIONS
)

_GENERIC_NON_ACTIONABLE_FAMILIES = {"unknown", "adware", "trojan"}

_BUCKET_ORDER: tuple[str, ...] = (
    "all_catalog",
    "android_platform",
    "android_with_permission_obs",
    "android_high_or_strong_vt_with_permission_obs",
    "android_labeled_primary_with_permission_obs",
    "android_banker_with_permission_obs",
    "android_family_ready_min3_permission_obs",
)


def _table_exists_primary(table_name: str) -> bool:
    try:
        return db_engine.table_exists(table_name)
    except Exception:
        return False


def _primary_table_columns(table_name: str) -> set[str]:
    try:
        rows = db_engine.get_table_columns(table_name)
    except Exception:
        return set()
    return {
        str(row).strip().lower()
        for row in rows
        if row is not None and str(row).strip()
    }


def _table_exists_permission(table_name: str) -> bool:
    try:
        return db_engine.table_exists(table_name)
    except Exception:
        return False


def _fetch_catalog_rows() -> list[dict[str, Any]]:
    query = f"""
        SELECT
            sample_id,
            platform,
            family_label,
            classification_primary,
            classification_subtype
        FROM `{DB_NAME}`.`{_PRIMARY_CATALOG_TABLE}`
    """
    columns, rows = db_engine.execute_query(query, fetch=True, return_columns=True)
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(dict(zip(columns, row)))
    return out


def _fetch_permission_observed_sample_ids() -> set[int]:
    query = f"""
        SELECT DISTINCT sample_id
        FROM `{PERMISSION_INTEL_DB_NAME}`.`{_PERMISSION_OBS_TABLE}`
        WHERE sample_id IS NOT NULL
    """
    rows = db_engine.execute_permission_query(query, fetch=True)
    return {int(row[0]) for row in rows if row and row[0] is not None}


def _fetch_high_confidence_sample_ids() -> set[int]:
    query = f"""
        SELECT DISTINCT sample_id
        FROM `{DB_NAME}`.`{_VT_CONFIDENCE_TABLE}`
        WHERE LOWER(TRIM(COALESCE(confidence_bucket, ''))) IN ('high', 'strong')
          AND sample_id IS NOT NULL
    """
    rows = db_engine.execute_query(query, fetch=True)
    return {int(row[0]) for row in rows if row and row[0] is not None}


def _fetch_android_authority_rows() -> list[dict[str, Any]]:
    """Load authority rows plus current family/type lifecycle flags.

    The authority view intentionally preserves historical mappings and therefore
    does not itself mean that both taxonomy records are currently active. The
    joins are read-only and let readiness distinguish broad family authority
    from the strict active-family/active-type surface without changing the
    view's historical semantics.
    """
    query = f"""
        SELECT
            a.sample_id,
            a.resolved_family_lc,
            a.family_slug,
            a.type_slug,
            a.raw_classification_primary,
            a.raw_classification_subtype,
            a.authority_bucket,
            a.raw_vs_authority_status,
            f.is_active AS family_is_active,
            t.is_active AS type_is_active
        FROM `{DB_NAME}`.`{_ANDROID_AUTHORITY_VIEW}` AS a
        LEFT JOIN `{DB_NAME}`.`{_ANDROID_FAMILY_TABLE}` AS f
          ON f.family_id = a.family_id
        LEFT JOIN `{DB_NAME}`.`{_ANDROID_TYPE_TABLE}` AS t
          ON t.type_id = a.type_id
    """
    columns, rows = db_engine.execute_query(query, fetch=True, return_columns=True)
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(dict(zip(columns, row)))
    return out


def _active_flag(value: Any) -> bool | None:
    """Normalize a nullable SQL active flag without guessing unknown values."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    token = str(value).strip().lower()
    if token in {"1", "true", "yes"}:
        return True
    if token in {"0", "false", "no"}:
        return False
    return None


def _authority_lifecycle_coverage(
    *,
    authority_rows: list[dict[str, Any]],
    permission_sample_ids: set[int],
    source_mode: str,
) -> dict[str, int | None]:
    """Measure broad and strict authority surfaces on the Android + PI scope.

    ``authority_family_typed`` only proves that a family/type mapping exists.
    The strict surface additionally requires both linked taxonomy records to
    be active. A legacy fallback cannot supply the lifecycle fields, so strict
    counts are deliberately unavailable rather than approximated.
    """
    keys = (
        "typed_authority_permission_obs_samples",
        "typed_authority_permission_obs_families",
        "strict_active_authority_permission_obs_samples",
        "strict_active_authority_permission_obs_families",
        "retired_type_authority_permission_obs_samples",
        "inactive_family_authority_permission_obs_samples",
        "unknown_lifecycle_authority_permission_obs_samples",
    )
    unavailable = {key: None for key in keys}
    if source_mode != "live_view":
        return unavailable

    typed_rows = [
        row
        for row in authority_rows
        if row.get("sample_id") is not None
        and int(row["sample_id"]) in permission_sample_ids
        and _norm_text(row.get("authority_bucket")).lower() == "authority_family_typed"
    ]
    typed_sample_ids = {int(row["sample_id"]) for row in typed_rows}
    typed_families = {
        _norm_text(row.get("family_slug")).lower()
        for row in typed_rows
        if _norm_text(row.get("family_slug"))
    }
    result: dict[str, int | None] = {
        "typed_authority_permission_obs_samples": len(typed_sample_ids),
        "typed_authority_permission_obs_families": len(typed_families),
        "strict_active_authority_permission_obs_samples": None,
        "strict_active_authority_permission_obs_families": None,
        "retired_type_authority_permission_obs_samples": None,
        "inactive_family_authority_permission_obs_samples": None,
        "unknown_lifecycle_authority_permission_obs_samples": None,
    }
    if not typed_rows:
        result.update(
            {
                "strict_active_authority_permission_obs_samples": 0,
                "strict_active_authority_permission_obs_families": 0,
                "retired_type_authority_permission_obs_samples": 0,
                "inactive_family_authority_permission_obs_samples": 0,
                "unknown_lifecycle_authority_permission_obs_samples": 0,
            }
        )
        return result

    # A view/schema fallback that omits these fields must not be described as
    # strict authority coverage. This is a reporting fail-closed behavior.
    if any(
        _active_flag(row.get("family_is_active")) is None
        or _active_flag(row.get("type_is_active")) is None
        for row in typed_rows
    ):
        return result

    strict_rows = [
        row
        for row in typed_rows
        if _active_flag(row.get("family_is_active")) is True
        and _active_flag(row.get("type_is_active")) is True
    ]
    retired_type_ids = {
        int(row["sample_id"])
        for row in typed_rows
        if _active_flag(row.get("family_is_active")) is True
        and _active_flag(row.get("type_is_active")) is False
    }
    inactive_family_ids = {
        int(row["sample_id"])
        for row in typed_rows
        if _active_flag(row.get("family_is_active")) is False
    }
    strict_sample_ids = {int(row["sample_id"]) for row in strict_rows}
    strict_families = {
        _norm_text(row.get("family_slug")).lower()
        for row in strict_rows
        if _norm_text(row.get("family_slug"))
    }
    result.update(
        {
            "strict_active_authority_permission_obs_samples": len(strict_sample_ids),
            "strict_active_authority_permission_obs_families": len(strict_families),
            "retired_type_authority_permission_obs_samples": len(retired_type_ids),
            "inactive_family_authority_permission_obs_samples": len(inactive_family_ids),
            "unknown_lifecycle_authority_permission_obs_samples": 0,
        }
    )
    return result


def fetch_active_family_inactive_type_gaps(
    *,
    include_authority_sample_count: bool = True,
) -> list[dict[str, Any]]:
    """Return active family mappings whose primary type has been retired.

    This is deliberately a read-only lifecycle check. A family can remain
    active while its type is retired during a taxonomy migration, but treating
    that type as current authority would make the training and label audits
    internally inconsistent. The result is an operator review queue, not an
    automatic type reactivation or family reassignment.
    """
    authority_projection = "COUNT(a.sample_id) AS authority_sample_count"
    authority_join = f"""
        LEFT JOIN `{DB_NAME}`.`{_ANDROID_AUTHORITY_VIEW}` AS a
          ON a.family_slug = f.family_slug
    """
    grouping = """
        GROUP BY
            f.family_id,
            f.family_slug,
            f.family_status,
            f.primary_type_id,
            t.type_slug
    """
    if not include_authority_sample_count:
        # Readiness needs a quick lifecycle warning. Avoid expanding the
        # authority view unless the operator explicitly requests the
        # sample-impact count via the detailed diagnostic report.
        authority_projection = "0 AS authority_sample_count"
        authority_join = ""
        grouping = ""

    query = f"""
        SELECT
            f.family_id,
            f.family_slug,
            f.family_status,
            f.primary_type_id,
            t.type_slug,
            {authority_projection}
        FROM `{DB_NAME}`.`{_ANDROID_FAMILY_TABLE}` AS f
        JOIN `{DB_NAME}`.`{_ANDROID_TYPE_TABLE}` AS t
          ON t.type_id = f.primary_type_id
        {authority_join}
        WHERE f.is_active = 1
          AND t.is_active = 0
        {grouping}
        ORDER BY authority_sample_count DESC, f.family_slug
    """
    columns, rows = db_engine.execute_query(query, fetch=True, return_columns=True)
    return [dict(zip(columns, row)) for row in rows]


def _fetch_android_family_resolution_rows() -> list[dict[str, Any]]:
    query = f"""
        SELECT
            msc.sample_id,
            v.resolved_family_lc,
            t.type_slug
        FROM `{DB_NAME}`.`{_PRIMARY_CATALOG_TABLE}` AS msc
        JOIN `{DB_NAME}`.`{_ANDROID_FAMILY_RESOLVED_VIEW}` AS v
          ON v.sample_id = msc.sample_id
        LEFT JOIN `{DB_NAME}`.`{_ANDROID_FAMILY_TABLE}` AS f
          ON LOWER(f.family_slug) = v.resolved_family_lc
        LEFT JOIN `{DB_NAME}`.`{_ANDROID_TYPE_TABLE}` AS t
          ON t.type_id = f.primary_type_id
        WHERE LOWER(TRIM(COALESCE(msc.platform, ''))) = 'android'
    """
    columns, rows = db_engine.execute_query(query, fetch=True, return_columns=True)
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(dict(zip(columns, row)))
    return out


def _fetch_family_permission_signal_rows() -> list[dict[str, Any]]:
    permission_list = ", ".join(f"'{permission}'" for permission in sorted(_PERMISSION_SIGNAL_PERMISSIONS))
    query = f"""
        SELECT
            r.resolved_family_lc AS family,
            ops.permission_string_norm,
            COUNT(*) AS sample_count
        FROM `{PERMISSION_INTEL_DB_NAME}`.`{_PERMISSION_OBS_TABLE}` AS ops
        JOIN `{DB_NAME}`.`{_PRIMARY_CATALOG_TABLE}` AS msc
          ON msc.sample_id = ops.sample_id
        JOIN `{DB_NAME}`.`{_ANDROID_FAMILY_RESOLVED_VIEW}` AS r
          ON r.sample_id = ops.sample_id
        WHERE LOWER(TRIM(COALESCE(msc.platform, ''))) = 'android'
          AND ops.permission_string_norm IN ({permission_list})
        GROUP BY r.resolved_family_lc, ops.permission_string_norm
    """
    columns, rows = db_engine.execute_permission_query(query, fetch=True, return_columns=True)
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(dict(zip(columns, row)))
    return out


def _fetch_active_generic_token_facts() -> dict[str, str]:
    columns_available = _primary_table_columns(_GENERIC_TOKEN_TABLE)
    active_filter = ""
    active_column = schema_map.resolve_existing_column(
        "vendor_label_generic_tokens",
        "active_flag",
        columns_available,
    )
    if active_column:
        active_filter = f"AND {active_column} = 1"
    query = f"""
        SELECT normalized_token, token_kind
        FROM `{DB_NAME}`.`{_GENERIC_TOKEN_TABLE}`
        WHERE normalized_token IS NOT NULL
          AND TRIM(normalized_token) <> ''
          {active_filter}
    """
    columns, rows = db_engine.execute_query(query, fetch=True, return_columns=True)
    out: dict[str, str] = {}
    for row in rows:
        payload = dict(zip(columns, row))
        token = _family_key(payload.get("normalized_token"))
        if token is None:
            continue
        out[token] = _norm_text(payload.get("token_kind")).lower() or "policy_held_token"
    return out


def _fetch_cross_family_alias_slug_overlaps() -> list[dict[str, Any]]:
    """Load active accepted alias tokens that collide with a different active family slug."""
    alias_columns = _primary_table_columns(_ANDROID_FAMILY_TABLE)
    family_columns = _primary_table_columns("android_malware_family_alias")
    family_active_clause = "AND f.is_active = 1" if "is_active" in alias_columns else ""
    alias_active_clause = "AND a.is_active = 1" if "is_active" in family_columns else ""
    alias_review_clause = "AND a.review_status = 'accepted'" if "review_status" in family_columns else ""
    query = """
        SELECT
            a.alias_name,
            a.family_id AS alias_family_id,
            alias_family.family_slug AS alias_family_slug,
            f.family_id AS slug_family_id,
            f.family_slug,
            f.family_name
        FROM `{db}`.`android_malware_family_alias` AS a
        JOIN `{db}`.`android_malware_family` AS alias_family
          ON alias_family.family_id = a.family_id
        JOIN `{db}`.`android_malware_family` AS f
          ON LOWER(TRIM(f.family_slug)) = LOWER(TRIM(a.alias_name))
        WHERE a.alias_name IS NOT NULL
          AND TRIM(a.alias_name) <> ''
          {alias_active_clause}
          {alias_review_clause}
          {family_active_clause}
          AND alias_family.family_id <> f.family_id
        ORDER BY a.alias_name, a.family_id, f.family_id
    """.format(
        db=DB_NAME,
        alias_active_clause=alias_active_clause,
        alias_review_clause=alias_review_clause,
        family_active_clause=family_active_clause,
    )
    columns, rows = db_engine.execute_query(query, fetch=True, return_columns=True)
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(dict(zip(columns, row)))
    return out


_MISSING_PRIMARY_RESIDUAL_LANE_CASE_SQL = """
                CASE
                    WHEN sample_suppression_weight > 0 THEN 'already_sample_suppressed'
                    WHEN keylogger_hits > 0 THEN 'high_risk_keylogger_signal_review'
                    WHEN fake_app_hits > 0 THEN 'fake_app_or_impersonation_signal_review'
                    WHEN adware_hits > 0 OR pua_testkey_hits > 0 THEN 'pua_adware_or_testkey_signal_review'
                    WHEN authority_bucket = 'missing_resolved_family'
                         AND android_package_name IN (
                            'com.ubnt.easyunifi',
                            'net.telewebion',
                            'by.lsdsl.hdrezka',
                            'com.learn.toppr'
                         )
                         THEN 'public_package_identity_provenance_review'
                    WHEN authority_bucket = 'authority_family_typed'
                         AND COALESCE(TRIM(authority_type_slug), '') NOT IN ('', 'unknown')
                         AND authority_family_is_active = 1
                         AND authority_type_is_active = 1
                         AND confidence_bucket IN ('high', 'strong')
                         THEN 'authority_backed_primary_backfill_review'
                    WHEN authority_bucket = 'authority_family_typed'
                         AND (authority_family_is_active <> 1 OR authority_type_is_active <> 1)
                         THEN 'authority_retired_taxonomy_lifecycle_review'
                    WHEN confidence_bucket IN ('high', 'strong')
                         THEN 'high_strong_primary_no_authority_review'
                    WHEN authority_bucket = 'missing_resolved_family'
                         AND vt_malicious_count = 0
                         THEN 'zero_detection_blank_family_provenance_review'
                    WHEN authority_bucket = 'missing_resolved_family'
                         THEN 'blank_family_low_consensus_manual_review'
                    WHEN authority_bucket = 'resolved_unknown'
                         AND confidence_bucket IN ('none', '')
                         THEN 'unknown_family_zero_signal_review'
                    WHEN authority_bucket = 'resolved_unknown'
                         AND confidence_bucket IN ('review', 'moderate')
                         THEN 'unknown_family_low_consensus_review'
                    ELSE 'manual_review'
                END
"""

_MISSING_PRIMARY_RECOMMENDED_ACTION_CASE_SQL = """
                CASE residual_lane
                    WHEN 'already_sample_suppressed'
                        THEN 'Closed: sample already under FP suppression; no primary backfill.'
                    WHEN 'authority_backed_primary_backfill_review'
                        THEN 'Review authority-derived primary-label proposal; no automatic write.'
                    WHEN 'authority_retired_taxonomy_lifecycle_review'
                        THEN 'Review retired family/type lifecycle before any primary-label backfill; no automatic write.'
                    WHEN 'high_strong_primary_no_authority_review'
                        THEN 'Manual review: high/strong VT consensus lacks governed family/type authority.'
                    WHEN 'high_risk_keylogger_signal_review'
                        THEN 'Review keylogger vendor signals before assigning classification_primary.'
                    WHEN 'fake_app_or_impersonation_signal_review'
                        THEN 'Review impersonation/fake-app vendor signals before primary assignment.'
                    WHEN 'pua_adware_or_testkey_signal_review'
                        THEN 'Review PUA/adware/test-key vendor signals before primary assignment.'
                    WHEN 'public_package_identity_provenance_review'
                        THEN 'Review public-package provenance before primary backfill.'
                    WHEN 'zero_detection_blank_family_provenance_review'
                        THEN 'Review zero-detection provenance before primary backfill.'
                    WHEN 'blank_family_low_consensus_manual_review'
                        THEN 'Manual review: blank family with low consensus.'
                    WHEN 'unknown_family_zero_signal_review'
                        THEN 'Manual review: unknown family with zero VT signal.'
                    WHEN 'unknown_family_low_consensus_review'
                        THEN 'Manual review: unknown family with low/moderate consensus.'
                    ELSE 'Manual review before classification_primary backfill.'
                END
"""


def _missing_primary_label_prerequisites_met() -> bool:
    return bool(
        _table_exists_primary(_PRIMARY_CATALOG_TABLE)
        and _table_exists_primary(_ANDROID_AUTHORITY_VIEW)
        and _table_exists_primary(_ANDROID_FAMILY_TABLE)
        and _table_exists_primary(_ANDROID_TYPE_TABLE)
        and _table_exists_primary(_VT_CONFIDENCE_TABLE)
        and _table_exists_primary(_FP_SUPPRESSION_TABLE)
        and _table_exists_permission(_PERMISSION_OBS_TABLE)
    )


def _missing_primary_label_lane_rows_cte_sql() -> str:
    return f"""
        WITH
        pi AS (
            SELECT DISTINCT sample_id
            FROM `{PERMISSION_INTEL_DB_NAME}`.`{_PERMISSION_OBS_TABLE}`
            WHERE sample_id IS NOT NULL
        ),
        suppression AS (
            SELECT
                msc.sample_id,
                MAX(s.suppression_weight) AS max_suppression_weight
            FROM `{DB_NAME}`.`{_PRIMARY_CATALOG_TABLE}` AS msc
            JOIN `{DB_NAME}`.`{_FP_SUPPRESSION_TABLE}` AS s
              ON s.active_flag = 1
             AND (s.starts_at_utc IS NULL OR s.starts_at_utc <= UTC_TIMESTAMP())
             AND (s.expires_at_utc IS NULL OR s.expires_at_utc > UTC_TIMESTAMP())
             AND (
                (s.scope_type = 'sample' AND s.scope_value = CAST(msc.sample_id AS CHAR))
                OR (s.scope_type = 'package' AND s.scope_value = msc.android_package_name)
             )
            GROUP BY msc.sample_id
        ),
        vendor_labels AS (
            SELECT
                sample_id,
                SUM(CASE WHEN LOWER(verdict_label) REGEXP 'fake(app|wallet|samsung|update)' THEN 1 ELSE 0 END) AS fake_app_hits,
                SUM(CASE WHEN LOWER(verdict_label) REGEXP 'keylogger' THEN 1 ELSE 0 END) AS keylogger_hits,
                SUM(CASE WHEN LOWER(verdict_label) REGEXP 'mobidash|adware' THEN 1 ELSE 0 END) AS adware_hits,
                SUM(CASE WHEN LOWER(verdict_label) REGEXP 'pua|pup|debugkey|testkey' THEN 1 ELSE 0 END) AS pua_testkey_hits
            FROM `{DB_NAME}`.`{_VT_VENDOR_VERDICTS_TABLE}`
            WHERE COALESCE(TRIM(verdict_label), '') <> ''
              AND verdict_category = 'malicious'
            GROUP BY sample_id
        ),
        base AS (
            SELECT
                msc.sample_id,
                msc.android_package_name,
                COALESCE(a.authority_bucket, '<none>') AS authority_bucket,
                COALESCE(a.resolved_family_lc, '') AS resolved_family_lc,
                COALESCE(a.family_slug, '') AS authority_family_slug,
                COALESCE(a.type_slug, '') AS authority_type_slug,
                COALESCE(a.parent_type_slug, '') AS authority_parent_type_slug,
                COALESCE(f.is_active, 0) AS authority_family_is_active,
                COALESCE(t.is_active, 0) AS authority_type_is_active,
                COALESCE(vs.confidence_bucket, 'none') AS confidence_bucket,
                COALESCE(vs.vt_malicious_count, 0) AS vt_malicious_count,
                COALESCE(s.max_suppression_weight, 0) AS sample_suppression_weight,
                COALESCE(vl.fake_app_hits, 0) AS fake_app_hits,
                COALESCE(vl.keylogger_hits, 0) AS keylogger_hits,
                COALESCE(vl.adware_hits, 0) AS adware_hits,
                COALESCE(vl.pua_testkey_hits, 0) AS pua_testkey_hits
            FROM `{DB_NAME}`.`{_PRIMARY_CATALOG_TABLE}` AS msc
            JOIN pi
              ON pi.sample_id = msc.sample_id
            LEFT JOIN `{DB_NAME}`.`{_ANDROID_AUTHORITY_VIEW}` AS a
              ON a.sample_id = msc.sample_id
            LEFT JOIN `{DB_NAME}`.`{_ANDROID_FAMILY_TABLE}` AS f
              ON LOWER(TRIM(f.family_slug)) = LOWER(TRIM(a.family_slug))
            LEFT JOIN `{DB_NAME}`.`{_ANDROID_TYPE_TABLE}` AS t
              ON t.type_id = f.primary_type_id
            LEFT JOIN `{DB_NAME}`.`{_VT_CONFIDENCE_TABLE}` AS vs
              ON vs.sample_id = msc.sample_id
            LEFT JOIN suppression AS s
              ON s.sample_id = msc.sample_id
            LEFT JOIN vendor_labels AS vl
              ON vl.sample_id = msc.sample_id
            WHERE LOWER(TRIM(COALESCE(msc.platform, ''))) = 'android'
              AND COALESCE(TRIM(msc.classification_primary), '') = ''
        ),
        lane_rows AS (
            SELECT
                sample_id,
                android_package_name,
                authority_bucket,
                resolved_family_lc,
                authority_family_slug,
                authority_type_slug,
                authority_parent_type_slug,
                authority_family_is_active,
                authority_type_is_active,
                CASE
                    WHEN authority_bucket = 'authority_family_typed'
                         AND COALESCE(TRIM(authority_type_slug), '') NOT IN ('', 'unknown')
                         AND authority_family_is_active = 1
                         AND authority_type_is_active = 1
                        THEN COALESCE(
                            NULLIF(TRIM(authority_parent_type_slug), ''),
                            NULLIF(TRIM(authority_type_slug), '')
                        )
                    ELSE ''
                END AS proposed_classification_primary,
                confidence_bucket,
                vt_malicious_count,
                sample_suppression_weight,
                {_MISSING_PRIMARY_RESIDUAL_LANE_CASE_SQL} AS residual_lane
            FROM base
        )
    """


def fetch_missing_primary_label_triage_rows(*, include_suppressed: bool = False) -> list[dict[str, Any]]:
    """Return row-level missing-primary triage rows for Android + PI samples."""
    if not _missing_primary_label_prerequisites_met():
        return []
    suppressed_filter = "" if include_suppressed else "WHERE residual_lane <> 'already_sample_suppressed'"
    query = (
        _missing_primary_label_lane_rows_cte_sql()
        + f"""
        SELECT
            sample_id,
            android_package_name,
            authority_bucket,
            resolved_family_lc,
            authority_family_slug,
            authority_type_slug,
            authority_parent_type_slug,
            authority_family_is_active,
            authority_type_is_active,
            proposed_classification_primary,
            confidence_bucket,
            vt_malicious_count,
            sample_suppression_weight,
            residual_lane,
            {_MISSING_PRIMARY_RECOMMENDED_ACTION_CASE_SQL} AS recommended_triage_action
        FROM lane_rows
        {suppressed_filter}
        ORDER BY
            CASE residual_lane
                WHEN 'authority_backed_primary_backfill_review' THEN 0
                WHEN 'authority_retired_taxonomy_lifecycle_review' THEN 1
                WHEN 'high_strong_primary_no_authority_review' THEN 2
                WHEN 'high_risk_keylogger_signal_review' THEN 3
                WHEN 'fake_app_or_impersonation_signal_review' THEN 4
                WHEN 'pua_adware_or_testkey_signal_review' THEN 5
                WHEN 'public_package_identity_provenance_review' THEN 6
                WHEN 'zero_detection_blank_family_provenance_review' THEN 7
                WHEN 'blank_family_low_consensus_manual_review' THEN 8
                WHEN 'unknown_family_zero_signal_review' THEN 9
                WHEN 'unknown_family_low_consensus_review' THEN 10
                WHEN 'manual_review' THEN 11
                ELSE 12
            END,
            vt_malicious_count DESC,
            sample_id
        """
    )
    columns, rows = db_engine.execute_query(query, fetch=True, return_columns=True)
    return [dict(zip(columns, row)) for row in rows]


def _fetch_missing_primary_label_lane_counts() -> list[dict[str, Any]]:
    """Return lane counts for Android + PI rows that still lack a primary label."""
    if not _missing_primary_label_prerequisites_met():
        return []
    query = (
        _missing_primary_label_lane_rows_cte_sql()
        + """
        SELECT
            residual_lane,
            COUNT(*) AS sample_count,
            SUM(CASE WHEN confidence_bucket IN ('high', 'strong') THEN 1 ELSE 0 END) AS high_or_strong_sample_count,
            SUM(CASE WHEN vt_malicious_count = 0 THEN 1 ELSE 0 END) AS zero_malicious_sample_count,
            SUM(CASE WHEN sample_suppression_weight > 0 THEN 1 ELSE 0 END) AS already_suppressed_sample_count
        FROM lane_rows
        GROUP BY residual_lane
        ORDER BY sample_count DESC, residual_lane
        """
    )
    columns, rows = db_engine.execute_query(query, fetch=True, return_columns=True)
    return [dict(zip(columns, row)) for row in rows]


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _family_key(value: Any) -> str | None:
    token = _norm_text(value)
    if not token:
        return None
    return token.lower()


def _sample_and_family_counts(rows: list[dict[str, Any]]) -> tuple[int | None, int | None]:
    families = {
        family
        for family in (_family_key(row.get("family_label")) for row in rows)
        if family is not None
    }
    return len(rows), len(families)


def _bucket(sample_count: int | None, family_count: int | None) -> dict[str, int | None]:
    return {"sample_count": sample_count, "family_count": family_count}


def _unavailable_bucket() -> dict[str, int | None]:
    return _bucket(None, None)


def _label_semantic(row: dict[str, Any]) -> str:
    primary = _norm_text(row.get("classification_primary")).lower()
    subtype = _norm_text(row.get("classification_subtype")).lower()
    subtype_map = {
        "banker": "banker",
        "remote access trojan": "rat",
        "rat": "rat",
        "dropper": "dropper",
        "stealer": "stealer",
        "spyware": "spyware",
        "sms trojan": "sms-trojan",
        "sms-trojan": "sms-trojan",
        "adware": "adware",
    }
    if subtype in subtype_map:
        return subtype_map[subtype]
    if primary in {"adware", "spyware"}:
        return primary
    if primary == "trojan" and not subtype:
        return "trojan_untyped"
    if not primary:
        return "<unlabeled>"
    if not subtype:
        return primary
    return f"{primary}/{subtype}"


def _build_permission_signal_index(rows: list[dict[str, Any]]) -> dict[str, dict[str, bool | str]]:
    by_family: dict[str, set[str]] = {}
    for row in rows:
        family = _family_key(row.get("family"))
        permission = _family_key(row.get("permission_string_norm"))
        if family is None or permission is None:
            continue
        by_family.setdefault(family, set()).add(permission)

    signal_index: dict[str, dict[str, bool | str]] = {}
    for family, permissions in by_family.items():
        has_sms = bool(permissions & _SMS_SIGNAL_PERMISSIONS)
        has_telephony = bool(permissions & _TELEPHONY_SIGNAL_PERMISSIONS)
        has_overlay = bool(permissions & _OVERLAY_SIGNAL_PERMISSIONS)
        has_remote_control = bool(permissions & _REMOTE_CONTROL_SIGNAL_PERMISSIONS)
        has_surveillance = bool(permissions & _SURVEILLANCE_SIGNAL_PERMISSIONS)
        summary_parts = []
        if has_sms:
            summary_parts.append("sms")
        if has_telephony:
            summary_parts.append("telephony")
        if has_overlay:
            summary_parts.append("overlay")
        if has_remote_control:
            summary_parts.append("remote")
        if has_surveillance:
            summary_parts.append("surveillance")
        signal_index[family] = {
            "has_sms": has_sms,
            "has_telephony": has_telephony,
            "has_overlay": has_overlay,
            "has_remote_control": has_remote_control,
            "has_surveillance": has_surveillance,
            "summary": "+".join(summary_parts) if summary_parts else "none",
        }
    return signal_index


def _operator_model_candidate(
    *,
    family: str,
    db_type_slug: str,
    dominant_semantic: str,
    permission_signals: dict[str, bool | str] | None = None,
) -> str:
    family = str(family or "").strip().lower()
    db_type_slug = str(db_type_slug or "").strip().lower()
    dominant_semantic = str(dominant_semantic or "").strip().lower()
    permission_signals = permission_signals or {}
    has_sms = bool(permission_signals.get("has_sms"))
    has_telephony = bool(permission_signals.get("has_telephony"))
    has_overlay = bool(permission_signals.get("has_overlay"))
    has_remote_control = bool(permission_signals.get("has_remote_control"))
    has_surveillance = bool(permission_signals.get("has_surveillance"))
    rat_families = {
        "bingomod",
        "brata",
        "copybara",
        "devixor",
        "gigabud",
        "gravityrat",
        "spynote",
    }
    banker_rat_families = {
        "alien",
        "anatsa",
        "anubis",
        "bankbot",
        "cerberus",
        "chameleon",
        "coper",
        "crocodilus",
        "ermac",
        "eventbot",
        "ginp",
        "godfather",
        "golddigger",
        "irata",
        "klopatra",
        "malibot",
        "marcher",
        "medusa",
        "octo",
        "pixbankbot",
        "pixpirate",
        "sova",
        "sharkbot",
        "teabot",
        "tgtoxic",
        "toxicpanda",
        "trickmo",
        "vultur",
        "xenomorph",
        "zanubis",
    }
    if has_remote_control and (has_sms or has_telephony or has_overlay):
        return "rat"
    if has_overlay and (has_sms or has_telephony):
        return "banker_rat_hybrid"
    if has_sms and has_telephony:
        return "banking_trojan"
    if has_remote_control:
        return "rat"
    if has_surveillance and not (has_sms or has_overlay):
        return "spyware"
    if family in rat_families:
        return "rat"
    if family in banker_rat_families and (db_type_slug in {"banker", "stealer", "<unmapped>", "unknown"} or dominant_semantic in {"banker", "trojan_untyped"}):
        return "banker_rat_hybrid"
    if dominant_semantic == "banker":
        return "banking_trojan"
    if db_type_slug in {"rat", "spyware", "stealer", "dropper", "adware", "sms-trojan"}:
        return db_type_slug
    if db_type_slug in {"unknown", "<unmapped>"} and dominant_semantic in {"rat", "stealer", "spyware", "adware", "sms-trojan"}:
        return dominant_semantic
    return "unclear"


def _fraud_posture_candidate(
    *,
    family: str,
    operator_model: str,
    dominant_semantic: str,
    permission_signals: dict[str, bool | str] | None = None,
) -> str:
    family = str(family or "").strip().lower()
    operator_model = str(operator_model or "").strip().lower()
    dominant_semantic = str(dominant_semantic or "").strip().lower()
    permission_signals = permission_signals or {}
    has_sms = bool(permission_signals.get("has_sms"))
    has_telephony = bool(permission_signals.get("has_telephony"))
    has_overlay = bool(permission_signals.get("has_overlay"))
    has_remote_control = bool(permission_signals.get("has_remote_control"))
    odf_families = {
        "alien",
        "bingomod",
        "copybara",
        "devixor",
        "gigabud",
        "irata",
        "klopatra",
        "malibot",
        "medusa",
        "pixbankbot",
        "pixpirate",
        "teabot",
        "toxicpanda",
    }
    if has_overlay and (has_sms or has_telephony) and has_remote_control:
        return "banking_targeted+odf_capable"
    if has_overlay and (has_sms or has_telephony):
        return "banking_targeted+odf_capable"
    if has_sms or has_telephony:
        return "banking_targeted"
    if family in odf_families or operator_model == "banker_rat_hybrid":
        return "banking_targeted+odf_capable"
    if dominant_semantic == "banker":
        return "banking_targeted"
    if operator_model == "rat":
        return "remote_control_fraudware"
    if operator_model == "stealer":
        return "credential_theft"
    if operator_model == "sms-trojan":
        return "sms_fraud"
    return "unclear"


def _conflict_priority_and_action(
    *,
    issue: str,
    sample_count: int,
    high_strong_sample_count: int,
    known_locally: bool,
    operator_model: str,
    fraud_posture: str,
) -> tuple[str, str]:
    issue = str(issue or "").strip().lower()
    operator_model = str(operator_model or "").strip().lower()
    fraud_posture = str(fraud_posture or "").strip().lower()
    if issue == "type_mismatch":
        if high_strong_sample_count >= 20 or sample_count >= 20:
            return "high", "review_db_type_mapping"
        return "medium", "review_db_type_mapping"
    if issue == "db_family_missing":
        if known_locally and (high_strong_sample_count >= 4 or sample_count >= 4):
            return "high", "add_db_family_mapping"
        return "medium", "review_unmapped_family"
    if issue == "type_unknown":
        if operator_model != "unclear" or fraud_posture != "unclear":
            return "high", "replace_unknown_db_type"
        return "medium", "review_unknown_db_type"
    if issue == "label_sparse":
        if operator_model in {"rat", "banker_rat_hybrid", "banking_trojan"} or "banking_targeted" in fraud_posture:
            return "medium", "backfill_label_semantics"
        return "low", "monitor_label_backfill"
    return "low", "review_manually"


def _build_family_type_conflict_signals(
    *,
    catalog_rows: list[dict[str, Any]],
    permission_sample_ids: set[int],
    authority_rows: list[dict[str, Any]],
    high_confidence_ids: set[int],
    family_permission_signal_rows: list[dict[str, Any]] | None = None,
    held_generic_tokens: dict[str, str] | None = None,
) -> dict[str, Any]:
    resolution_by_sample: dict[int, dict[str, Any]] = {}
    for row in authority_rows:
        sample_id = row.get("sample_id")
        if sample_id is None:
            continue
        resolution_by_sample[int(sample_id)] = row

    family_stats: dict[str, dict[str, Any]] = {}
    for row in catalog_rows:
        if _norm_text(row.get("platform")).lower() != "android":
            continue
        sample_id = row.get("sample_id")
        if sample_id is None:
            continue
        sample_id = int(sample_id)
        if sample_id not in permission_sample_ids:
            continue
        resolution = resolution_by_sample.get(sample_id)
        if not isinstance(resolution, dict):
            continue
        family = _family_key(resolution.get("resolved_family_lc"))
        if family is None:
            continue
        db_type_slug = _norm_text(resolution.get("type_slug")).lower()
        stats = family_stats.setdefault(
            family,
            {
                "family": family,
                "db_type_slug": db_type_slug or "<unmapped>",
                "samples": 0,
                "high_strong_sample_count": 0,
                "known_locally": is_known_family_name(family),
                "label_counts": {},
                "unlabeled_samples": 0,
            },
        )
        stats["samples"] += 1
        if sample_id in high_confidence_ids:
            stats["high_strong_sample_count"] += 1
        semantic = _label_semantic(row)
        counts = stats["label_counts"]
        counts[semantic] = int(counts.get(semantic, 0)) + 1
        if semantic == "<unlabeled>":
            stats["unlabeled_samples"] += 1

    issue_priority = {
        "type_mismatch": 0,
        "db_family_missing": 1,
        "type_unknown": 2,
        "label_sparse": 3,
    }
    permission_signal_index = _build_permission_signal_index(family_permission_signal_rows or [])
    meaningful_semantics = {"banker", "rat", "dropper", "stealer", "spyware", "sms-trojan", "adware"}

    def _suppress_broad_spyware_type_mismatch(*, db_type_slug: str, dominant_semantic: str, operator_model: str) -> bool:
        """Return True when broad raw spyware labeling should not override a stronger RAT family signal."""
        db_type_norm = str(db_type_slug or "").strip().lower()
        semantic_norm = str(dominant_semantic or "").strip().lower()
        operator_norm = str(operator_model or "").strip().lower()
        return semantic_norm == "spyware" and db_type_norm == "rat" and operator_norm == "rat"

    backlog: list[dict[str, Any]] = []
    for stats in family_stats.values():
        samples = int(stats["samples"])
        family_slug = str(stats["family"])
        if family_slug in (held_generic_tokens or {}):
            continue
        label_counts = dict(stats["label_counts"])
        dominant_semantic = ""
        dominant_count = 0
        if label_counts:
            dominant_semantic, dominant_count = max(
                label_counts.items(),
                key=lambda item: (int(item[1]), str(item[0])),
            )
        db_type_slug = str(stats["db_type_slug"])
        unlabeled_samples = int(stats["unlabeled_samples"])
        known_locally = bool(stats["known_locally"])
        permission_signals = permission_signal_index.get(str(stats["family"]), {})
        operator_model = _operator_model_candidate(
            family=str(stats["family"]),
            db_type_slug=db_type_slug,
            dominant_semantic=dominant_semantic,
            permission_signals=permission_signals,
        )
        fraud_posture = _fraud_posture_candidate(
            family=str(stats["family"]),
            operator_model=operator_model,
            dominant_semantic=dominant_semantic,
            permission_signals=permission_signals,
        )
        permission_signal_summary = str(permission_signals.get("summary", "none"))
        issue = ""
        if db_type_slug == "<unmapped>":
            issue = "db_family_missing"
        elif db_type_slug == "unknown" and known_locally:
            issue = "type_unknown"
        elif (
            dominant_semantic in meaningful_semantics
            and dominant_semantic != db_type_slug
            and dominant_count >= max(5, int(math.ceil(samples * 0.60)))
        ):
            if not _suppress_broad_spyware_type_mismatch(
                db_type_slug=db_type_slug,
                dominant_semantic=dominant_semantic,
                operator_model=operator_model,
            ):
                issue = "type_mismatch"
        elif db_type_slug not in {"<unmapped>", "unknown"} and unlabeled_samples >= max(10, int(math.ceil(samples * 0.70))):
            issue = "label_sparse"
        if not issue:
            continue
        priority, suggested_action = _conflict_priority_and_action(
            issue=issue,
            sample_count=samples,
            high_strong_sample_count=int(stats["high_strong_sample_count"]),
            known_locally=known_locally,
            operator_model=operator_model,
            fraud_posture=fraud_posture,
        )
        backlog.append(
            {
                "family": str(stats["family"]),
                "db_type_slug": db_type_slug,
                "issue": issue,
                "sample_count": samples,
                "high_strong_sample_count": int(stats["high_strong_sample_count"]),
                "dominant_label_semantic": dominant_semantic or "<none>",
                "dominant_label_samples": int(dominant_count),
                "unlabeled_samples": unlabeled_samples,
                "known_locally": known_locally,
                "operator_model_candidate": operator_model,
                "fraud_posture_candidate": fraud_posture,
                "permission_signal_summary": permission_signal_summary,
                "priority": priority,
                "suggested_action": suggested_action,
            }
        )

    backlog.sort(
        key=lambda item: (
            issue_priority.get(str(item.get("issue")), 99),
            -int(item.get("sample_count", 0) or 0),
            -int(item.get("high_strong_sample_count", 0) or 0),
            str(item.get("family", "")),
        )
    )
    repair_priority = {"high": 0, "medium": 1, "low": 2}
    repair_candidates = [
        entry
        for entry in backlog
        if str(entry.get("family", "")) not in _GENERIC_NON_ACTIONABLE_FAMILIES
        and (
            bool(entry.get("known_locally"))
            or str(entry.get("issue", "")) in {"type_mismatch", "type_unknown"}
        )
    ]
    repair_candidates.sort(
        key=lambda item: (
            repair_priority.get(str(item.get("priority", "low")), 99),
            issue_priority.get(str(item.get("issue")), 99),
            -int(item.get("high_strong_sample_count", 0) or 0),
            -int(item.get("sample_count", 0) or 0),
            str(item.get("family", "")),
        )
    )
    counts_by_issue: dict[str, int] = {}
    counts_by_priority: dict[str, int] = {}
    counts_by_action: dict[str, int] = {}
    for entry in backlog:
        issue = str(entry.get("issue", ""))
        counts_by_issue[issue] = counts_by_issue.get(issue, 0) + 1
        priority = str(entry.get("priority", "") or "low")
        counts_by_priority[priority] = counts_by_priority.get(priority, 0) + 1
        action = str(entry.get("suggested_action", "") or "review_manually")
        counts_by_action[action] = counts_by_action.get(action, 0) + 1
    return {
        "family_type_conflict_count": len(backlog),
        "family_type_conflict_issue_counts": counts_by_issue,
        "family_type_conflict_priority_counts": counts_by_priority,
        "family_type_conflict_action_counts": counts_by_action,
        "high_priority_conflict_count": counts_by_priority.get("high", 0),
        "top_family_type_conflicts": backlog[:8],
        "repair_candidate_count": len(repair_candidates),
        "top_repair_candidates": repair_candidates[:8],
    }


def get_cohort_readiness_snapshot() -> dict[str, Any]:
    """Return operator-facing cohort counts for the current split-catalog model."""
    payload: dict[str, Any] = {
        "status": "ok",
        "warnings": [],
        "authority_source_mode": "unavailable",
        "primary_available": False,
        "permission_intel_available": False,
        "permission_obs_available": False,
        "vt_confidence_available": False,
        "buckets": {name: _unavailable_bucket() for name in _BUCKET_ORDER},
        "taxonomy_signals": {
            "banker_label_bucket_samples": None,
            "banker_type_bucket_samples": None,
            "banker_type_minus_label_samples": None,
            "missing_primary_label_raw_samples": None,
            "missing_primary_label_samples": None,
            "missing_primary_label_actionable_samples": None,
            "missing_primary_label_residual_samples": None,
            "missing_primary_label_suppressed_samples": None,
            "missing_primary_label_active_residual_samples": None,
            "missing_primary_label_lane_counts": {},
            "top_missing_primary_label_lanes": [],
            "unresolved_family_samples": None,
            "unresolved_family_count": None,
            "known_unresolved_family_samples": None,
            "known_unresolved_family_count": None,
            "policy_held_family_samples": None,
            "policy_held_family_count": None,
            "policy_held_family_token_kind_counts": {},
            "top_policy_held_families": [],
            "top_unresolved_families": [],
            "family_type_conflict_count": None,
            "family_type_conflict_issue_counts": {},
            "family_type_conflict_priority_counts": {},
            "family_type_conflict_action_counts": {},
            "high_priority_conflict_count": None,
            "top_family_type_conflicts": [],
            "repair_candidate_count": None,
            "top_repair_candidates": [],
            "alias_family_overlap_count": None,
            "top_alias_family_overlaps": [],
            "blank_resolved_family_samples": None,
            "blank_resolved_family_bucket_counts": {},
            "top_blank_resolved_family_buckets": [],
            "active_family_retired_type_mapping_count": None,
            "top_active_family_retired_type_mappings": [],
            "typed_authority_permission_obs_samples": None,
            "typed_authority_permission_obs_families": None,
            "strict_active_authority_permission_obs_samples": None,
            "strict_active_authority_permission_obs_families": None,
            "retired_type_authority_permission_obs_samples": None,
            "inactive_family_authority_permission_obs_samples": None,
            "unknown_lifecycle_authority_permission_obs_samples": None,
        },
    }

    if not _table_exists_primary(_PRIMARY_CATALOG_TABLE):
        payload["status"] = "degraded"
        payload["warnings"].append(
            "Primary catalog unavailable: malware_sample_catalog not reachable on the primary Erebus connection."
        )
        return payload

    payload["primary_available"] = True
    try:
        catalog_rows = _fetch_catalog_rows()
    except Exception as exc:
        payload["status"] = "degraded"
        payload["warnings"].append(f"Primary catalog query failed: {exc}")
        return payload

    payload["buckets"]["all_catalog"] = _bucket(*_sample_and_family_counts(catalog_rows))

    android_rows = [row for row in catalog_rows if _norm_text(row.get("platform")).lower() == "android"]
    payload["buckets"]["android_platform"] = _bucket(*_sample_and_family_counts(android_rows))
    android_by_sample = {
        int(row["sample_id"]): row
        for row in android_rows
        if row.get("sample_id") is not None
    }

    if _table_exists_primary(_ANDROID_FAMILY_TABLE) and _table_exists_primary(_ANDROID_TYPE_TABLE):
        try:
            lifecycle_gaps = fetch_active_family_inactive_type_gaps(
                include_authority_sample_count=False,
            )
            payload["taxonomy_signals"]["active_family_retired_type_mapping_count"] = len(lifecycle_gaps)
            payload["taxonomy_signals"]["top_active_family_retired_type_mappings"] = lifecycle_gaps[:8]
            if lifecycle_gaps:
                brief = ", ".join(
                    f"{row.get('family_slug')}→{row.get('type_slug')}"
                    for row in lifecycle_gaps[:4]
                )
                payload["warnings"].append(
                    "Active family mappings reference retired taxonomy types "
                    f"({brief}). They remain in broad cohorts; run "
                    "report_taxonomy_type_lifecycle_gaps.py before using them for type-level claims."
                )
        except Exception:
            # This is additive readiness intelligence. A legacy or partially
            # migrated schema should not block baseline cohort availability.
            pass

    if not _table_exists_permission(_PERMISSION_OBS_TABLE):
        payload["status"] = "degraded"
        payload["warnings"].append(
            "Permission Intel unavailable: android_permission_obs_sample not reachable on the Permission Intel connection."
        )
        return payload

    payload["permission_intel_available"] = True
    payload["permission_obs_available"] = True
    try:
        permission_sample_ids = _fetch_permission_observed_sample_ids()
    except Exception as exc:
        payload["status"] = "degraded"
        payload["warnings"].append(f"Permission observation query failed: {exc}")
        return payload

    android_with_pi_rows = [android_by_sample[sid] for sid in sorted(permission_sample_ids & set(android_by_sample))]
    payload["buckets"]["android_with_permission_obs"] = _bucket(*_sample_and_family_counts(android_with_pi_rows))

    family_permission_signal_rows: list[dict[str, Any]] = []
    try:
        family_permission_signal_rows = _fetch_family_permission_signal_rows()
    except Exception as exc:
        payload["warnings"].append(f"Permission signal summary unavailable: {exc}")

    android_sample_ids = set(android_by_sample)
    pi_outside_android = permission_sample_ids - android_sample_ids
    if pi_outside_android:
        payload["warnings"].append(
            "Permission Intel observations include "
            f"{len(pi_outside_android)} sample_id(s) outside the current Android catalog cohort."
        )

    if _table_exists_primary(_VT_CONFIDENCE_TABLE):
        payload["vt_confidence_available"] = True
        try:
            high_confidence_ids = _fetch_high_confidence_sample_ids()
        except Exception as exc:
            payload["status"] = "degraded"
            payload["warnings"].append(f"VT confidence query failed: {exc}")
            payload["buckets"]["android_high_or_strong_vt_with_permission_obs"] = _unavailable_bucket()
        else:
            high_rows = [android_by_sample[sid] for sid in sorted((permission_sample_ids & high_confidence_ids) & set(android_by_sample))]
            payload["buckets"]["android_high_or_strong_vt_with_permission_obs"] = _bucket(*_sample_and_family_counts(high_rows))
    else:
        payload["status"] = "degraded"
        payload["warnings"].append(
            "VT confidence surface unavailable: vt_sample_verdict_confidence_current missing on the primary Erebus connection."
        )
        payload["buckets"]["android_high_or_strong_vt_with_permission_obs"] = _unavailable_bucket()

    labeled_rows = [
        row
        for row in android_with_pi_rows
        if _norm_text(row.get("classification_primary"))
    ]
    payload["buckets"]["android_labeled_primary_with_permission_obs"] = _bucket(*_sample_and_family_counts(labeled_rows))
    raw_missing_primary_count = len(android_with_pi_rows) - len(labeled_rows)
    missing_primary_count = raw_missing_primary_count
    payload["taxonomy_signals"]["missing_primary_label_raw_samples"] = raw_missing_primary_count
    payload["taxonomy_signals"]["missing_primary_label_samples"] = missing_primary_count
    missing_primary_lane_rows: list[dict[str, Any]] = []
    if raw_missing_primary_count > 0:
        try:
            missing_primary_lane_rows = _fetch_missing_primary_label_lane_counts()
        except Exception as exc:
            payload["warnings"].append(f"Missing-primary residual lane split unavailable: {exc}")
    if missing_primary_lane_rows:
        lane_counts = {
            str(row.get("residual_lane", "") or "manual_review"): int(row.get("sample_count", 0) or 0)
            for row in missing_primary_lane_rows
        }
        actionable_count = lane_counts.get("authority_backed_primary_backfill_review", 0)
        suppressed_count = lane_counts.get("already_sample_suppressed", 0)
        residual_count = max(sum(lane_counts.values()) - actionable_count, 0)
        active_residual_count = max(residual_count - suppressed_count, 0)
        missing_primary_count = actionable_count + active_residual_count
        payload["taxonomy_signals"]["missing_primary_label_samples"] = missing_primary_count
        payload["taxonomy_signals"]["missing_primary_label_actionable_samples"] = actionable_count
        payload["taxonomy_signals"]["missing_primary_label_residual_samples"] = residual_count
        payload["taxonomy_signals"]["missing_primary_label_suppressed_samples"] = suppressed_count
        payload["taxonomy_signals"]["missing_primary_label_active_residual_samples"] = active_residual_count
        payload["taxonomy_signals"]["missing_primary_label_lane_counts"] = lane_counts
        payload["taxonomy_signals"]["top_missing_primary_label_lanes"] = [
            {
                "lane": str(row.get("residual_lane", "") or "manual_review"),
                "sample_count": int(row.get("sample_count", 0) or 0),
                "high_or_strong_sample_count": int(row.get("high_or_strong_sample_count", 0) or 0),
                "zero_malicious_sample_count": int(row.get("zero_malicious_sample_count", 0) or 0),
                "already_suppressed_sample_count": int(row.get("already_suppressed_sample_count", 0) or 0),
            }
            for row in missing_primary_lane_rows[:6]
        ]
    if raw_missing_primary_count > 0:
        actionable = payload["taxonomy_signals"].get("missing_primary_label_actionable_samples")
        residual = payload["taxonomy_signals"].get("missing_primary_label_residual_samples")
        suppressed = payload["taxonomy_signals"].get("missing_primary_label_suppressed_samples")
        active_residual = payload["taxonomy_signals"].get("missing_primary_label_active_residual_samples")
        if (
            actionable is not None
            and suppressed is not None
            and active_residual is not None
            and missing_primary_count <= 0
        ):
            payload["warnings"].append(
                "Primary labels are raw-missing for "
                f"{raw_missing_primary_count} Android + PI-observed sample(s), "
                "but active/actionable missing-primary debt is 0 after suppression-aware triage. "
                f"Suppressed provenance/false-positive rows={suppressed}; "
                f"active residual review rows={active_residual}; "
                f"actionable high/strong label-review rows={actionable}."
            )
        else:
            lane_note = ""
            if actionable is not None and residual is not None:
                lane_note = f" Actionable high/strong label-review rows={actionable}; residual/provenance rows={residual}."
                if suppressed is not None and active_residual is not None:
                    lane_note += f" Already-suppressed rows={suppressed}; active residual review rows={active_residual}."
            payload["warnings"].append(
                "Primary labels are raw-missing for "
                f"{raw_missing_primary_count} Android + PI-observed sample(s); "
                f"active/actionable missing-primary debt={missing_primary_count}."
                f"{lane_note}"
            )

    banker_rows = [
        row
        for row in android_with_pi_rows
        if _norm_text(row.get("classification_primary")).lower() == "trojan"
        and _norm_text(row.get("classification_subtype")).lower() == "banker"
    ]
    payload["buckets"]["android_banker_with_permission_obs"] = _bucket(*_sample_and_family_counts(banker_rows))
    payload["taxonomy_signals"]["banker_label_bucket_samples"] = len(banker_rows)

    family_resolution_tables = (
        _table_exists_primary(_ANDROID_FAMILY_RESOLVED_VIEW)
        and _table_exists_primary(_ANDROID_FAMILY_TABLE)
        and _table_exists_primary(_ANDROID_TYPE_TABLE)
    )
    authority_rows: list[dict[str, Any]] = []
    authority_source_mode = "unavailable"
    held_generic_tokens: dict[str, str] = {}
    if _table_exists_primary(_GENERIC_TOKEN_TABLE):
        try:
            held_generic_tokens = _fetch_active_generic_token_facts()
        except Exception as exc:
            payload["warnings"].append(f"Generic token policy unavailable: {exc}")
    if family_resolution_tables:
        try:
            authority_rows = _fetch_android_authority_rows()
            authority_source_mode = "live_view"
        except Exception as exc:
            payload["warnings"].append(
                f"Authority view unavailable, falling back to legacy family/type joins: {exc}"
            )
            try:
                authority_rows = _fetch_android_family_resolution_rows()
                authority_source_mode = "legacy_resolution_fallback"
            except Exception as inner_exc:
                payload["status"] = "degraded"
                payload["warnings"].append(f"Android family-resolution query failed: {inner_exc}")
    payload["authority_source_mode"] = authority_source_mode
    if authority_rows:
        lifecycle_coverage = _authority_lifecycle_coverage(
            authority_rows=authority_rows,
            permission_sample_ids=permission_sample_ids,
            source_mode=authority_source_mode,
        )
        payload["taxonomy_signals"].update(lifecycle_coverage)
        broad_typed = lifecycle_coverage.get("typed_authority_permission_obs_samples")
        strict_typed = lifecycle_coverage.get("strict_active_authority_permission_obs_samples")
        retired_type_typed = lifecycle_coverage.get("retired_type_authority_permission_obs_samples")
        inactive_family_typed = lifecycle_coverage.get("inactive_family_authority_permission_obs_samples")
        if broad_typed is not None and strict_typed is None:
            payload["warnings"].append(
                "Family-typed authority is available, but strict active-family/active-type coverage is unavailable "
                "because lifecycle flags could not be verified from the live authority projection."
            )
        elif broad_typed is not None and strict_typed is not None and int(broad_typed) != int(strict_typed):
            payload["warnings"].append(
                "Family-typed authority has a stricter active-family/active-type subset: "
                f"broad={int(broad_typed)}, strict={int(strict_typed)}, "
                f"retired_type={int(retired_type_typed or 0)}, inactive_family={int(inactive_family_typed or 0)}."
            )
        banker_type_rows = [
            row
            for row in authority_rows
            if row.get("sample_id") is not None
            and int(row["sample_id"]) in permission_sample_ids
            and _norm_text(row.get("type_slug")).lower() == "banker"
            and (
                authority_source_mode != "live_view"
                or _norm_text(row.get("authority_bucket")).lower() == "authority_family_typed"
            )
        ]
        payload["taxonomy_signals"]["banker_type_bucket_samples"] = len(banker_type_rows)
        banker_gap = max(len(banker_type_rows) - len(banker_rows), 0)
        payload["taxonomy_signals"]["banker_type_minus_label_samples"] = banker_gap
        if banker_gap > 0:
            payload["warnings"].append(
                "Banker type-slug coverage exceeds the current banker label bucket by "
                f"{banker_gap} sample(s); "
                "the banker readiness bucket is label-derived."
            )

        unresolved_counts: dict[str, int] = {}
        unresolved_high_strong_counts: dict[str, int] = {}
        held_counts: dict[str, int] = {}
        held_kind_counts: dict[str, int] = {}
        unresolved_samples = 0
        known_unresolved_samples = 0
        held_unresolved_samples = 0
        unresolved_buckets = {"resolved_but_no_authority_family", "generic_label_candidate"}
        for row in authority_rows:
            sample_id = row.get("sample_id")
            if sample_id is None or int(sample_id) not in permission_sample_ids:
                continue
            resolved_family = _family_key(row.get("resolved_family_lc"))
            authority_bucket = _norm_text(row.get("authority_bucket")).lower()
            unresolved_fallback = authority_source_mode != "live_view" and not _norm_text(row.get("type_slug"))
            unresolved_live = authority_source_mode == "live_view" and authority_bucket in unresolved_buckets
            if resolved_family is None or not (unresolved_live or unresolved_fallback):
                continue
            if resolved_family in held_generic_tokens:
                held_unresolved_samples += 1
                held_counts[resolved_family] = held_counts.get(resolved_family, 0) + 1
                token_kind = held_generic_tokens.get(resolved_family, "policy_held_token")
                held_kind_counts[token_kind] = held_kind_counts.get(token_kind, 0) + 1
                if payload["vt_confidence_available"] and int(sample_id) in high_confidence_ids:
                    unresolved_high_strong_counts[resolved_family] = (
                        unresolved_high_strong_counts.get(resolved_family, 0) + 1
                    )
                continue
            unresolved_samples += 1
            unresolved_counts[resolved_family] = unresolved_counts.get(resolved_family, 0) + 1
            if is_known_family_name(resolved_family):
                known_unresolved_samples += 1
            if payload["vt_confidence_available"] and int(sample_id) in high_confidence_ids:
                unresolved_high_strong_counts[resolved_family] = (
                    unresolved_high_strong_counts.get(resolved_family, 0) + 1
                )
        payload["taxonomy_signals"]["unresolved_family_samples"] = unresolved_samples
        payload["taxonomy_signals"]["unresolved_family_count"] = len(unresolved_counts)
        payload["taxonomy_signals"]["known_unresolved_family_samples"] = known_unresolved_samples
        payload["taxonomy_signals"]["known_unresolved_family_count"] = sum(
            1 for family in unresolved_counts if is_known_family_name(family)
        )
        payload["taxonomy_signals"]["policy_held_family_samples"] = held_unresolved_samples
        payload["taxonomy_signals"]["policy_held_family_count"] = len(held_counts)
        payload["taxonomy_signals"]["policy_held_family_token_kind_counts"] = held_kind_counts
        payload["taxonomy_signals"]["top_policy_held_families"] = [
            {
                "family": family,
                "sample_count": count,
                "token_kind": held_generic_tokens.get(family, "policy_held_token"),
                "high_strong_sample_count": unresolved_high_strong_counts.get(family, 0),
            }
            for family, count in sorted(
                held_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:5]
        ]
        payload["taxonomy_signals"]["top_unresolved_families"] = [
            {
                "family": family,
                "sample_count": count,
                "high_strong_sample_count": unresolved_high_strong_counts.get(family, 0),
                "known_locally": is_known_family_name(family),
            }
            for family, count in sorted(
                unresolved_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:5]
        ]
        if unresolved_counts:
            payload["warnings"].append(
                "Resolved-family coverage includes "
                f"{len(unresolved_counts)} unmapped family slug(s); "
                "type-ready cohorts may undercount live Android malware families."
            )
        if held_counts:
            payload["warnings"].append(
                "Resolved-family coverage also includes "
                f"{len(held_counts)} policy-held generic/coarse token(s); "
                "these are excluded from live family-repair backlog counts."
            )
        if payload["taxonomy_signals"]["known_unresolved_family_count"]:
            payload["warnings"].append(
                "Some unresolved family slugs are already recognized by the local canonical taxonomy; "
                "this suggests DB family catalog lag rather than purely unknown families."
            )
        conflict_signals = _build_family_type_conflict_signals(
            catalog_rows=catalog_rows,
            permission_sample_ids=permission_sample_ids,
            authority_rows=authority_rows,
            high_confidence_ids=high_confidence_ids if payload["vt_confidence_available"] else set(),
            family_permission_signal_rows=family_permission_signal_rows,
            held_generic_tokens=held_generic_tokens,
        )
        payload["taxonomy_signals"].update(conflict_signals)
        if conflict_signals.get("family_type_conflict_count"):
            payload["warnings"].append(
                "Family/type backlog contains "
                f"{conflict_signals['family_type_conflict_count']} family-level conflict candidate(s) "
                "across type mismatch, sparse labels, or missing DB family rows."
            )
        try:
            alias_overlaps = _fetch_cross_family_alias_slug_overlaps()
        except Exception as exc:
            payload["warnings"].append(f"Alias/family overlap diagnostic unavailable: {exc}")
        else:
            payload["taxonomy_signals"]["alias_family_overlap_count"] = len(alias_overlaps)
            payload["taxonomy_signals"]["top_alias_family_overlaps"] = [
                {
                    "alias_name": str(row.get("alias_name", "") or ""),
                    "alias_family_id": int(row.get("alias_family_id", 0) or 0),
                    "alias_family_slug": str(row.get("alias_family_slug", "") or ""),
                    "slug_family_id": int(row.get("slug_family_id", 0) or 0),
                    "family_slug": str(row.get("family_slug", "") or ""),
                    "family_name": str(row.get("family_name", "") or ""),
                }
                for row in alias_overlaps[:8]
            ]
            if alias_overlaps:
                payload["warnings"].append(
                    "Alias/family authority overlap includes "
                    f"{len(alias_overlaps)} accepted alias token(s) that collide with a different active family slug."
                )

    if payload["permission_obs_available"] and _table_exists_primary(_ANDROID_AUTHORITY_VIEW):
        try:
            blank_resolved_rows = fetch_blank_resolved_family_lane_counts()
        except Exception as exc:
            payload["warnings"].append(f"Blank resolved-family lane split unavailable: {exc}")
        else:
            if blank_resolved_rows:
                bucket_counts = {
                    str(row.get("authority_bucket", "") or "<none>"): int(row.get("sample_count", 0) or 0)
                    for row in blank_resolved_rows
                }
                blank_count = int(sum(bucket_counts.values()))
                payload["taxonomy_signals"]["blank_resolved_family_samples"] = blank_count
                payload["taxonomy_signals"]["blank_resolved_family_bucket_counts"] = bucket_counts
                payload["taxonomy_signals"]["top_blank_resolved_family_buckets"] = [
                    {
                        "authority_bucket": str(row.get("authority_bucket", "") or "<none>"),
                        "sample_count": int(row.get("sample_count", 0) or 0),
                        "high_or_strong_sample_count": int(row.get("high_or_strong_sample_count", 0) or 0),
                    }
                    for row in blank_resolved_rows[:6]
                ]
                if blank_count > 0:
                    payload["warnings"].append(
                        "Resolved-family slugs are blank for "
                        f"{blank_count} Android + PI-observed sample(s); "
                        "use Android missing-resolution triage for package/VT-tail provenance review."
                    )

    family_counts: dict[str, int] = {}
    for row in android_with_pi_rows:
        family = _family_key(row.get("family_label"))
        if family is None or family == "unknown":
            continue
        family_counts[family] = family_counts.get(family, 0) + 1

    family_ready_rows = [
        row
        for row in android_with_pi_rows
        if (family := _family_key(row.get("family_label"))) is not None
        and family != "unknown"
        and family_counts.get(family, 0) >= 3
    ]
    payload["buckets"]["android_family_ready_min3_permission_obs"] = _bucket(*_sample_and_family_counts(family_ready_rows))

    return payload


__all__ = [
    "fetch_missing_primary_label_triage_rows",
    "get_cohort_readiness_snapshot",
]
