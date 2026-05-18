# Filename: src/obsidiandroid/database/db_permission_analysis_queries.py
# Purpose: Query Android permission data and AV reports
#
# Canonical implementation; ``database.db_permission_analysis_queries`` is an identity shim.

from . import db_engine
from .db_config import DB_NAME, PERMISSION_INTEL_DB_NAME

BANKING_TROJAN_FAMILIES = (
    "anubis",
    "blackrock",
    "cabassous",
    "cerberus",
    "chameleon",
    "crocodilus",
    "ermac",
    "eventbot",
    "flubot",
    "golddigger",
    "godfather",
    "marcher",
    "sharkbot",
    "sova",
    "teabot",
    "tgtoxic",
    "trickbot",
    "trickmo",
    "vultur",
)


def _primary(table: str) -> str:
    """Fully qualify a table in the primary Erebus schema."""
    return f"`{DB_NAME}`.`{table}`"


def _permission_intel(table: str) -> str:
    """Fully qualify a table in the Permission Intel schema."""
    return f"`{PERMISSION_INTEL_DB_NAME}`.`{table}`"


def _sql_string_list(values: tuple[str, ...]) -> str:
    """Render a deterministic SQL string list for ``IN (...)`` clauses."""
    return ", ".join(f"'{value}'" for value in values)


def fetch_android_banking_trojans_with_permissions():
    family_filter_sql = _sql_string_list(BANKING_TROJAN_FAMILIES)
    query = f"""
        SELECT
            ms.sample_id,
            ms.sample_label AS sample_name,
            CASE 
                WHEN LOWER(TRIM(ms.family_label)) IN ('cabassous', 'flubot') THEN 'FluBot'
                ELSE ms.family_label
            END AS family_name,
            ms.classification_primary AS category_primary,
            ms.classification_subtype AS category_subtype,
            ms.vt_suggested_label,
            NULL AS vt_scan_status,
            ms.android_package_name AS package_name,
            ms.android_launcher_activity AS main_activity,
            ms.android_min_sdk AS target_min_version,
            ms.android_target_sdk AS target_sdk_version,
            ms.android_permission_count AS permissions,

            CASE
                WHEN kp.constant_value IS NOT NULL
                  OR UPPER(COALESCE(ops.classification, '')) IN ('AOSP', 'GOOGLE')
                THEN ops.permission_string
                ELSE NULL
            END AS known_permission_id,
            CASE
                WHEN kp.constant_value IS NOT NULL
                  OR UPPER(COALESCE(ops.classification, '')) IN ('AOSP', 'GOOGLE')
                THEN kp.constant_value
                ELSE NULL
            END AS known_constant,
            CASE
                WHEN kp.constant_value IS NOT NULL
                  OR UPPER(COALESCE(ops.classification, '')) IN ('AOSP', 'GOOGLE')
                THEN kp.protection_level
                ELSE NULL
            END AS known_protection,
            CASE
                WHEN kp.constant_value IS NOT NULL
                  OR UPPER(COALESCE(ops.classification, '')) IN ('AOSP', 'GOOGLE')
                THEN UPPER(COALESCE(ops.classification, 'AOSP'))
                ELSE NULL
            END AS known_vendor,
            CASE
                WHEN kp.constant_value IS NOT NULL
                  OR UPPER(COALESCE(ops.classification, '')) IN ('AOSP', 'GOOGLE')
                THEN COALESCE(vtc.andro_type, UPPER(COALESCE(ops.classification, 'AOSP')))
                ELSE NULL
            END AS known_type,

            CASE
                WHEN mp.permission_string IS NOT NULL
                  OR UPPER(COALESCE(ops.classification, '')) IN ('OEM', 'APP_DEFINED')
                THEN ops.permission_string
                ELSE NULL
            END AS manufacturer_permission_id,
            CASE
                WHEN mp.permission_string IS NOT NULL
                  OR UPPER(COALESCE(ops.classification, '')) IN ('OEM', 'APP_DEFINED')
                THEN mp.permission_string
                ELSE NULL
            END AS manufacturer_constant,
            CASE
                WHEN mp.permission_string IS NOT NULL
                  OR UPPER(COALESCE(ops.classification, '')) IN ('OEM', 'APP_DEFINED')
                THEN mp.protection_level
                ELSE NULL
            END AS manufacturer_protection,
            CASE
                WHEN mp.permission_string IS NOT NULL
                  OR UPPER(COALESCE(ops.classification, '')) IN ('OEM', 'APP_DEFINED')
                THEN ov.vendor_name
                ELSE NULL
            END AS manufacturer_vendor,
            CASE
                WHEN mp.permission_string IS NOT NULL
                  OR UPPER(COALESCE(ops.classification, '')) IN ('OEM', 'APP_DEFINED')
                THEN UPPER(COALESCE(ops.classification, 'OEM'))
                ELSE NULL
            END AS manufacturer_type,

            CASE
                WHEN kp.constant_value IS NULL
                  AND mp.permission_string IS NULL
                  AND (
                    UPPER(COALESCE(ops.classification, 'UNKNOWN')) = 'UNKNOWN'
                    OR up.permission_string IS NOT NULL
                  )
                THEN ops.permission_string
                ELSE NULL
            END AS unknown_permission_id,
            CASE
                WHEN kp.constant_value IS NULL
                  AND mp.permission_string IS NULL
                  AND (
                    UPPER(COALESCE(ops.classification, 'UNKNOWN')) = 'UNKNOWN'
                    OR up.permission_string IS NOT NULL
                  )
                THEN up.permission_string
                ELSE NULL
            END AS unknown_constant,
            NULL AS unknown_protection,
            CASE
                WHEN kp.constant_value IS NULL
                  AND mp.permission_string IS NULL
                  AND (
                    UPPER(COALESCE(ops.classification, 'UNKNOWN')) = 'UNKNOWN'
                    OR up.permission_string IS NOT NULL
                  )
                THEN UPPER(COALESCE(ops.classification, 'UNKNOWN'))
                ELSE NULL
            END AS unknown_type

        FROM {_primary("malware_sample_catalog")} ms
        JOIN {_permission_intel("android_permission_obs_sample")} ops ON ms.sample_id = ops.sample_id
        LEFT JOIN {_permission_intel("android_permission_dict_aosp")} kp
            ON LOWER(TRIM(ops.permission_string)) = LOWER(TRIM(kp.constant_value))
        LEFT JOIN {_permission_intel("android_permission_dict_oem")} mp
            ON LOWER(TRIM(ops.permission_string)) = LOWER(TRIM(mp.permission_string))
            AND (
                ops.vendor_id = mp.vendor_id
                OR ops.vendor_id IS NULL
            )
        LEFT JOIN {_permission_intel("android_permission_dict_unknown")} up
            ON LOWER(TRIM(ops.permission_string)) = LOWER(TRIM(up.permission_string))
        LEFT JOIN {_permission_intel("android_permission_meta_oem_vendor")} ov
            ON ops.vendor_id = ov.vendor_id
        LEFT JOIN {_permission_intel("android_permission_enrich_vt_current")} vtc
            ON LOWER(TRIM(ops.permission_string)) = LOWER(TRIM(vtc.permission_string))
        WHERE LOWER(ms.family_label) IN ({family_filter_sql})
        ORDER BY ms.sample_id ASC, ops.observed_at_utc ASC, ops.permission_string ASC
    """
    return db_engine.execute_query(query, fetch=True, return_columns=True)

def fetch_android_banking_trojans_with_permissions_count():
    family_filter_sql = _sql_string_list(BANKING_TROJAN_FAMILIES)
    query = f"""
        SELECT
            ms.sample_id, ms.sample_label AS sample_name,
            CASE 
                WHEN LOWER(TRIM(ms.family_label)) IN ('cabassous', 'flubot') THEN 'FluBot'
                ELSE ms.family_label
            END AS family_name,
            ms.android_permission_count AS permission_count
        FROM {_primary("malware_sample_catalog")} ms
        WHERE LOWER(ms.family_label) IN ({family_filter_sql})
        ORDER BY ms.sample_id ASC
    """
    return db_engine.execute_query(query, fetch=True, return_columns=True)

def fetch_av_report_by_sample_id(sample_id):
    query = f"""
        SELECT *
        FROM {_primary("virustotal_sample_vendor_engine_verdicts")}
        WHERE sample_id = %s
    """
    return db_engine.execute_query(query, (sample_id,), fetch=True, return_columns=True)
