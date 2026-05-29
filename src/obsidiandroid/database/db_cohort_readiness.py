"""Read-only cohort-readiness summary for split Erebus + Permission Intel routing."""

from __future__ import annotations

import math
from typing import Any

from . import db_engine
from . import schema_map
from .db_config import DB_NAME, PERMISSION_INTEL_DB_NAME
from obsidiandroid.labeling.taxonomy import is_known_family_name

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
    query = f"""
        SELECT
            sample_id,
            resolved_family_lc,
            family_slug,
            type_slug,
            raw_classification_primary,
            raw_classification_subtype,
            authority_bucket,
            raw_vs_authority_status
        FROM `{DB_NAME}`.`{_ANDROID_AUTHORITY_VIEW}`
    """
    columns, rows = db_engine.execute_query(query, fetch=True, return_columns=True)
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(dict(zip(columns, row)))
    return out


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


def _fetch_missing_primary_label_lane_counts() -> list[dict[str, Any]]:
    """Return lane counts for Android + PI rows that still lack a primary label."""
    if not (
        _table_exists_primary(_PRIMARY_CATALOG_TABLE)
        and _table_exists_primary(_ANDROID_AUTHORITY_VIEW)
        and _table_exists_primary(_VT_CONFIDENCE_TABLE)
        and _table_exists_primary(_FP_SUPPRESSION_TABLE)
        and _table_exists_permission(_PERMISSION_OBS_TABLE)
    ):
        return []
    query = f"""
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
                confidence_bucket,
                vt_malicious_count,
                sample_suppression_weight,
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
                    WHEN confidence_bucket IN ('high', 'strong')
                         THEN 'high_strong_primary_backfill_review'
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
                END AS residual_lane
            FROM base
        )
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
            issue = "type_mismatch"
        elif db_type_slug not in {"<unmapped>", "unknown"} and unlabeled_samples >= max(10, int(math.ceil(samples * 0.70))):
            issue = "label_sparse"
        if not issue:
            continue
        operator_model = _operator_model_candidate(
            family=str(stats["family"]),
            db_type_slug=db_type_slug,
            dominant_semantic=dominant_semantic,
            permission_signals=permission_signal_index.get(str(stats["family"]), {}),
        )
        fraud_posture = _fraud_posture_candidate(
            family=str(stats["family"]),
            operator_model=operator_model,
            dominant_semantic=dominant_semantic,
            permission_signals=permission_signal_index.get(str(stats["family"]), {}),
        )
        permission_signal_summary = str(
            permission_signal_index.get(str(stats["family"]), {}).get("summary", "none")
        )
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
        actionable_count = lane_counts.get("high_strong_primary_backfill_review", 0)
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


__all__ = ["get_cohort_readiness_snapshot"]
