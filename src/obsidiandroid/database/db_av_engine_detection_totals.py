# Filename: src/obsidiandroid/database/db_av_engine_detection_totals.py
# Purpose : Aggregates AV engine detection statistics using regex pattern analysis and engine metadata.
#
# Canonical implementation; the repo-root
# ``database.db_av_engine_detection_totals`` shim has been retired.

import pandas as pd
from . import db_engine, db_sample_malicious_scoring
from .verdict_semantics import sql_non_detection_predicate
from obsidiandroid.cli.ui import display as du
from obsidiandroid.labeling.malware_family_constants import FAMILY_ALIASES, KNOWN_FAMILIES

EXCLUDE_COLUMNS = {
    "sample_id", "updated_at", "record_id", "malicious", "undetected",
    "timeout", "scan_date", "total_engines"
}


def _family_name_hits_regex() -> str:
    """Return regex covering known family tokens and common alias spellings."""
    tokens = {
        str(token).strip().lower()
        for token in KNOWN_FAMILIES
        if str(token).strip()
    }
    tokens.update(
        str(alias).strip().lower()
        for alias in FAMILY_ALIASES
        if str(alias).strip()
    )
    ordered = sorted(tokens, key=lambda item: (-len(item), item))
    return "|".join(ordered)

# -----------------------------------------------------------------------------
# Step 1: Extract Valid Engine Columns
# -----------------------------------------------------------------------------

def _get_valid_engine_list() -> list:
    all_engines = db_sample_malicious_scoring.get_existing_result_columns()
    return [e.replace("-", "_") for e in all_engines if e not in EXCLUDE_COLUMNS]

def _build_union_sql(engine_list: list) -> str:
    """
    Builds a UNION ALL SQL block that melts the wide verdict table into
    (engine_name, result) rows while filtering out junk entries like NULL, '', 'None', etc.
    """
    cleaned_selects = []

    for engine in engine_list:
        select_stmt = f"""
        SELECT 
            '{engine}' AS engine_name,
            CASE 
                WHEN {sql_non_detection_predicate(f'`{engine}`')} THEN NULL
                ELSE `{engine}`
            END AS result
        FROM virustotal_sample_vendor_engine_verdicts
        """
        cleaned_selects.append(select_stmt.strip())

    return "\nUNION ALL\n".join(cleaned_selects)

# -----------------------------------------------------------------------------
# Step 3: Build Final Aggregation SQL Query
# -----------------------------------------------------------------------------

def _build_engine_stats_query(union_sql: str) -> str:
    benign_regex = "benign|clean|safe|trusted|approved|verified|whitelist"
    suspicious_regex = "risktool|adware|grayware|heur|not[-]?a[-]?virus|monitor|obfus|pua|testkey|dualuse|demo"
    malicious_regex = "trojan|backdoor|spy|rat|banker|keylogger|stealer|dropper|ransom|clipbank|loader|exploit"
    family_hits_regex = _family_name_hits_regex()
    return f"""
    SELECT
        melted.engine_name,
        e.vendor_name AS detection_strategy,
        e.is_trusted_vendor,
        e.is_engine_active,

        -- Basic stats
        COUNT(*) AS total_scanned,

        -- Verdict category counts
        SUM(
            melted.result IS NOT NULL
            AND NOT LOWER(TRIM(melted.result)) REGEXP '{benign_regex}'
        ) AS malicious_count,
        SUM(LOWER(TRIM(melted.result)) REGEXP '{suspicious_regex}') AS suspicious_count,
        SUM(LOWER(TRIM(melted.result)) REGEXP '{benign_regex}') AS benign_count,

        -- Count of null / non-detection values
        SUM(melted.result IS NULL) AS undetected_count,

        -- Positive labels that do not match known malicious/suspicious/benign buckets
        SUM(
            melted.result IS NOT NULL AND TRIM(melted.result) <> '' AND
            NOT LOWER(TRIM(melted.result)) REGEXP '{malicious_regex}|{suspicious_regex}|{benign_regex}'
        ) AS unknown_count,

        -- Detection of known malware-family tokens and common alias spellings
        SUM(LOWER(TRIM(melted.result)) REGEXP '{family_hits_regex}') AS family_name_hits,

        -- Revised detection coverage (percentage of rows with meaningful result)
        ROUND(
            SUM(
                CASE 
                    WHEN melted.result IS NOT NULL
                    THEN 1 
                    ELSE 0 
                END
            ) / COUNT(*) * 100, 
            2
        ) AS coverage_pct,

        -- Positive-detection percentages
        ROUND(
            SUM(
                melted.result IS NOT NULL
                AND NOT LOWER(TRIM(melted.result)) REGEXP '{benign_regex}'
            ) / COUNT(*) * 100,
            2
        ) AS malicious_pct,

        ROUND(
            SUM(LOWER(TRIM(melted.result)) REGEXP '{suspicious_regex}') / COUNT(*) * 100,
            2
        ) AS suspicious_pct,

        -- Threat score: absolute count of positive detections
        SUM(
            melted.result IS NOT NULL
            AND NOT LOWER(TRIM(melted.result)) REGEXP '{benign_regex}'
        ) AS threat_signal_score

    FROM ({union_sql}) AS melted
    JOIN virustotal_vendor_engines e ON melted.engine_name = e.vendor_key
    GROUP BY melted.engine_name
    ORDER BY malicious_count DESC, malicious_pct DESC;
    """

# ----------------------------------------------------------------------
# Step 4: Main Entry Point
# ----------------------------------------------------------------------

def get_engine_detection_totals(as_dataframe: bool = True) -> pd.DataFrame:
    try:
        engine_list = _get_valid_engine_list()
        if not engine_list:
            du.print_warning("[WARN] No valid engine columns found in virustotal_sample_vendor_engine_verdicts.")
            return pd.DataFrame()

        union_sql = _build_union_sql(engine_list)
        full_query = _build_engine_stats_query(union_sql)

        #_export_engine_stats_query(full_query)

        df = db_engine.execute_query(full_query, fetch=True, return_columns=True, as_dataframe=as_dataframe)
        return df

    except Exception as e:
        du.print_error(f"[ERROR] Engine detection total query failed: {e}")
        return pd.DataFrame()

# ----------------------------------------------------------------------
# Step 5: SQL Export Helper
# ----------------------------------------------------------------------

def _export_engine_stats_query(query: str):
    try:
        EXPORT_QUERY_PATH = "output/engine_stats_query.txt"
        with open(EXPORT_QUERY_PATH, "w", encoding="utf-8") as f:
            f.write(query.strip())

        du.print_info(f"[EXPORT] SQL query:{du.format_console_path(EXPORT_QUERY_PATH)}")
    except Exception as e:
        du.print_warning(f"[EXPORT] Failed to write query file: {e}")
