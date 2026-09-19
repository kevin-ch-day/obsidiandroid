# Filename: src/obsidiandroid/database/db_permission_analysis_queries.py
# Purpose: Query Android permission data and AV reports
#
# Canonical implementation; the repo-root
# ``database.db_permission_analysis_queries`` shim has been retired.

from . import db_engine
from . import permission_contracts
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
    oem_join = permission_contracts.oem_dictionary_join_predicate(
        observation_alias="ops",
        oem_alias="mp",
    )
    unknown_join = permission_contracts.unknown_dictionary_join_predicate(
        observation_alias="ops",
        unknown_alias="up",
    )
    alias_join = permission_contracts.token_alias_join(
        raw_expr="ops.permission_string",
        table_sql=_permission_intel("android_permission_token_alias"),
    )
    identity_expr = permission_contracts.catalog_identity_expr(
        raw_expr="ops.permission_string",
    )
    fact_join = permission_contracts.authority_fact_join(
        raw_expr=identity_expr,
        table_sql=_permission_intel("android_permission_authority_fact"),
    )
    vt_join = permission_contracts.vt_current_join(
        raw_expr="ops.permission_string",
        table_sql=_permission_intel("android_permission_enrich_vt_current"),
    )
    current_platform = """pi.permission_id IS NOT NULL
                  AND pi.authority_class IN ('AOSP_PUBLIC','AOSP_HIDDEN','AOSP_INTERNAL','AOSP_MODULE')"""
    fact_exact = f"BINARY paf.permission_string = BINARY {identity_expr}"
    historical_platform = f"""{current_platform} AND (
                  pi.lifecycle IN ('historical','legacy_removed','removed')
                  OR pi.identity_status = 'RETIRED'
                )"""
    current_available_platform = f"({current_platform}) AND NOT ({historical_platform})"
    historical_fact = """(paf.fact_scope = 'removed_api' OR (
                  paf.lifecycle_status IN ('historical','legacy_removed','removed')
                  AND LEFT(COALESCE(paf.authority_source_type,''), 5) = 'aosp_'))"""
    oem_exact = "BINARY mp.permission_string = BINARY ops.permission_string"
    resolved_oem = f"COALESCE(({oem_exact} AND ov.vendor_id IS NOT NULL), FALSE)"
    safe_platform_protection = f"""CASE WHEN {current_available_platform}
                  AND COALESCE(pic.unresolved_conflict_count, 0) = 0
                  AND pi.feature_dependency IS NULL
                THEN piv.compatibility_protection_expression ELSE NULL END"""
    current_scope = f"""CASE
                WHEN {historical_platform} THEN 'HISTORICAL_PLATFORM'
                WHEN {current_platform} THEN 'AOSP_PLATFORM'
                WHEN pi.permission_id IS NOT NULL AND pi.authority_class = 'OEM_OR_VENDOR'
                THEN 'OEM_OR_VENDOR'
                WHEN pi.permission_id IS NOT NULL AND pi.authority_class = 'APPLICATION_DEFINED'
                THEN 'THIRD_PARTY_APPLICATION_DEFINED'
                WHEN {fact_exact} AND {historical_fact} THEN 'HISTORICAL_PLATFORM'
                WHEN {fact_exact} AND paf.fact_scope = 'provider_permission'
                 AND paf.authority_source_type IN ('aosp_package_manifest','aosp_framework_manifest')
                THEN 'AOSP_PROVIDER_ACL'
                WHEN {fact_exact} AND paf.fact_scope = 'permission_definition'
                 AND paf.authority_source_type = 'aosp_package_manifest'
                THEN 'AOSP_PACKAGE_DEFINED'
                WHEN {fact_exact} AND paf.fact_scope = 'permission_definition'
                 AND paf.authority_source_type IN ('sdk_vendor_docs','sdk_inventory')
                THEN 'SDK_INTEGRATION_CUSTOM_PERMISSION'
                WHEN {fact_exact} AND paf.fact_scope = 'permission_definition'
                 AND paf.authority_source_type IN ('chromium_source','androidx_manifest')
                THEN 'THIRD_PARTY_APPLICATION_DEFINED'
                ELSE 'UNKNOWN' END"""
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
                WHEN {current_platform}
                THEN ops.permission_string
                ELSE NULL
            END AS known_permission_id,
            CASE
                WHEN {current_platform}
                THEN pi.canonical_permission
                ELSE NULL
            END AS known_constant,
            CASE
                WHEN {current_available_platform}
                THEN {safe_platform_protection}
                ELSE NULL
            END AS known_protection,
            CASE
                WHEN {current_platform}
                THEN 'AOSP'
                ELSE NULL
            END AS known_vendor,
            CASE
                WHEN {current_platform}
                THEN COALESCE(vtc.andro_type, 'AOSP')
                ELSE NULL
            END AS known_type,
            UPPER(COALESCE(ops.classification, 'UNKNOWN')) AS historical_permission_source,
            {current_scope} AS current_authority_scope,
            CASE
                WHEN {fact_exact} AND paf.fact_scope = 'provider_permission' THEN 'PROVIDER_PERMISSION'
                WHEN {current_platform} OR ({fact_exact} AND paf.fact_scope IN ('permission_definition','removed_api'))
                THEN 'PERMISSION'
                ELSE 'UNKNOWN'
            END AS current_identifier_kind,

            CASE
                WHEN NOT ({current_platform}) AND {resolved_oem}
                THEN ops.permission_string
                ELSE NULL
            END AS manufacturer_permission_id,
            CASE
                WHEN NOT ({current_platform}) AND {resolved_oem}
                THEN mp.permission_string
                ELSE NULL
            END AS manufacturer_constant,
            CASE
                WHEN NOT ({current_platform}) AND {resolved_oem}
                THEN mp.protection_level
                ELSE NULL
            END AS manufacturer_protection,
            CASE
                WHEN NOT ({current_platform}) AND {resolved_oem}
                THEN ov.vendor_name
                ELSE NULL
            END AS manufacturer_vendor,
            CASE
                WHEN NOT ({current_platform}) AND {resolved_oem}
                THEN UPPER(COALESCE(ops.classification, 'OEM'))
                ELSE NULL
            END AS manufacturer_type,

            CASE
                WHEN NOT ({current_platform})
                  AND NOT {resolved_oem}
                  AND (
                    UPPER(COALESCE(ops.classification, 'UNKNOWN')) = 'UNKNOWN'
                    OR up.permission_string IS NOT NULL
                  )
                THEN ops.permission_string
                ELSE NULL
            END AS unknown_permission_id,
            CASE
                WHEN NOT ({current_platform})
                  AND NOT {resolved_oem}
                  AND (
                    UPPER(COALESCE(ops.classification, 'UNKNOWN')) = 'UNKNOWN'
                    OR up.permission_string IS NOT NULL
                  )
                THEN up.permission_string
                ELSE NULL
            END AS unknown_constant,
            NULL AS unknown_protection,
            CASE
                WHEN NOT ({current_platform})
                  AND NOT {resolved_oem}
                  AND (
                    UPPER(COALESCE(ops.classification, 'UNKNOWN')) = 'UNKNOWN'
                    OR up.permission_string IS NOT NULL
                  )
                THEN UPPER(COALESCE(ops.classification, 'UNKNOWN'))
                ELSE NULL
            END AS unknown_type

        FROM {_primary("malware_sample_catalog")} ms
        JOIN {_permission_intel("android_permission_obs_sample")} ops ON ms.sample_id = ops.sample_id
        {alias_join}
        LEFT JOIN {_permission_intel("android_permission_v1_current_permission")} pi
            ON BINARY pi.canonical_permission = BINARY {identity_expr}
        LEFT JOIN {_permission_intel("android_permission_v1_obsidiandroid_permission")} piv
            ON BINARY piv.canonical_permission = BINARY pi.canonical_permission
           AND piv.catalog_release_id = pi.catalog_release_id
           AND piv.catalog_digest = pi.catalog_digest
        LEFT JOIN (
            SELECT permission_id, COUNT(*) AS unresolved_conflict_count
            FROM {_permission_intel("api_permission_declaration_conflict")}
            WHERE resolution_status = 'UNRESOLVED'
            GROUP BY permission_id
        ) pic ON pic.permission_id = pi.permission_id
        {fact_join}
        LEFT JOIN {_permission_intel("android_permission_dict_oem")} mp
            ON {oem_join}
        LEFT JOIN {_permission_intel("android_permission_dict_unknown")} up
            ON {unknown_join}
        LEFT JOIN {_permission_intel("android_permission_meta_oem_vendor")} ov
            ON mp.vendor_id = ov.vendor_id
        {vt_join}
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
