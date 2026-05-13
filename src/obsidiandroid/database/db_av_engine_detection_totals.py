# Filename: src/obsidiandroid/database/db_av_engine_detection_totals.py
# Purpose : Aggregates AV engine detection statistics using regex pattern analysis and engine metadata.
#
# Canonical implementation; ``database.db_av_engine_detection_totals`` is an identity shim.

import pandas as pd
from . import db_engine, db_sample_malicious_scoring
from obsidiandroid.cli.ui import display as du

EXCLUDE_COLUMNS = {
    "sample_id", "updated_at", "record_id", "malicious", "undetected",
    "timeout", "scan_date", "total_engines"
}

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
                WHEN `{engine}` IS NULL THEN NULL
                WHEN TRIM(LOWER(`{engine}`)) IN ('', 'none', 'null', 'n/a') THEN NULL
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
    return f"""
    SELECT
        melted.engine_name,
        e.vendor_name AS detection_strategy,
        e.is_trusted_vendor,
        e.is_engine_active,

        -- Basic stats
        COUNT(*) AS total_scanned,

        -- Verdict category counts
        SUM(LOWER(TRIM(melted.result)) REGEXP 'trojan|backdoor|spy|rat|banker|keylogger|stealer|dropper|ransom|clipbank|loader|exploit') AS malicious_count,
        SUM(LOWER(TRIM(melted.result)) REGEXP 'risktool|adware|grayware|heur|not[-]?a[-]?virus|monitor|obfus|pua|testkey|dualuse|demo') AS suspicious_count,
        SUM(LOWER(TRIM(melted.result)) REGEXP 'benign|clean|safe|trusted|approved|verified|whitelist') AS benign_count,

        -- Count of null, empty string, or trashy values
        SUM(
            melted.result IS NULL OR 
            TRIM(melted.result) = '' OR 
            LOWER(TRIM(melted.result)) IN ('none', 'null', 'n/a')
        ) AS undetected_count,

        -- Count of non-matching unknown classifications
        SUM(
            melted.result IS NOT NULL AND TRIM(melted.result) <> '' AND
            NOT LOWER(TRIM(melted.result)) REGEXP 'trojan|backdoor|spy|rat|banker|keylogger|stealer|dropper|ransom|clipbank|loader|exploit|
                                                  risktool|adware|grayware|heur|not[-]?a[-]?virus|monitor|obfus|pua|testkey|dualuse|demo|
                                                  benign|clean|safe|trusted|approved|verified|whitelist'
        ) AS unknown_count,

        -- Detection of key banking trojan families
        SUM(LOWER(TRIM(melted.result)) REGEXP 'anubis|cerberus|flubot|teabot|sharkbot|blackrock|vultur|sova|ermac|joker|
                                               copybara|coyote|godfather|marcher|chameleon|brata|trickbot|cabassous|
                                               golddigger|fatboypanel|xenomorph') AS family_name_hits,

        -- Revised detection coverage (percentage of rows with meaningful result)
        ROUND(
            SUM(
                CASE 
                    WHEN melted.result IS NOT NULL AND TRIM(LOWER(melted.result)) NOT IN ('', 'none', 'null', 'n/a') 
                    THEN 1 
                    ELSE 0 
                END
            ) / COUNT(*) * 100, 
            2
        ) AS coverage_pct,

        -- Detection percentages
        ROUND(
            SUM(LOWER(TRIM(melted.result)) REGEXP 'trojan|banker|rat|spy|dropper') / COUNT(*) * 100, 
            2
        ) AS malicious_pct,

        ROUND(
            SUM(LOWER(TRIM(melted.result)) REGEXP 'risktool|adware|heur') / COUNT(*) * 100, 
            2
        ) AS suspicious_pct,

        -- Threat score based on non-benign detections
        COUNT(*) - SUM(LOWER(TRIM(melted.result)) REGEXP 'benign|clean|safe|trusted|approved|verified') AS threat_signal_score

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

        du.print_info(f"[EXPORT] SQL query saved to: {EXPORT_QUERY_PATH}")
    except Exception as e:
        du.print_warning(f"[EXPORT] Failed to write query file: {e}")

