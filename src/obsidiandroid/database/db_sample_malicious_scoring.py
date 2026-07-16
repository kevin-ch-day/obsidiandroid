# Filename: src/obsidiandroid/database/db_sample_malicious_scoring.py
# Purpose: Compute per-sample malicious detection scores based on trusted AV engines
#
# Canonical implementation; the repo-root
# ``database.db_sample_malicious_scoring`` shim has been retired.

from . import db_engine
from . import schema_map
from .verdict_semantics import sql_non_detection_predicate
from obsidiandroid.cli.ui import display as du


_AUXILIARY_NON_VENDOR_SOURCES = {"androguard", "android_info", "apk"}


def _normalize_engine_key(engine_name: str) -> str:
    """Canonicalize engine/source names for matching against wide verdict columns."""
    return str(engine_name).strip().lower().replace("-", "_").replace(" ", "_")

def get_active_trusted_engines():
    vendors_table = schema_map.table("vendor_engines")
    engine_col = schema_map.column("vendor_engines", "engine_name")
    trusted_col = schema_map.column("vendor_engines", "trusted_flag")
    active_col = schema_map.column("vendor_engines", "active_flag")
    auxiliary_sources_sql = ", ".join(f"'{source}'" for source in sorted(_AUXILIARY_NON_VENDOR_SOURCES))
    query = """
        SELECT {engine_col} AS engine_name
        FROM {vendors_table}
        WHERE {trusted_col} = 1
          AND {active_col} = 1
          AND LOWER(TRIM({engine_col})) NOT IN ({auxiliary_sources_sql})
    """
    query = query.format(
        engine_col=engine_col,
        vendors_table=vendors_table,
        trusted_col=trusted_col,
        active_col=active_col,
        auxiliary_sources_sql=auxiliary_sources_sql,
    )
    try:
        _columns, rows = db_engine.execute_query(query, fetch=True, return_columns=True)
        if not rows:
            du.print_debug("Trusted-engine query returned 0 rows.")
            return []
        
        engines = []
        for idx, row in enumerate(rows):
            if not isinstance(row, (list, tuple)) or len(row) < 1:
                du.print_debug(f"Trusted-engine row {idx} is invalid: {row}")
                continue

            name = row[0]
            if not isinstance(name, str) or len(name.strip()) < 2:
                du.print_debug(f"Skipping suspicious engine name: {name}")
                continue

            engines.append(name.strip())

        du.print_debug(f"Trusted engine count: {len(engines)}")
        return engines

    except Exception as e:
        du.print_error(f"[ERROR] Failed to fetch trusted engines: {e}")
        return []


def build_union_sql(valid_engines: list[str], *, restrict_to_selected_samples: bool = False) -> str:
    """
    Builds UNION ALL SQL to extract engine verdicts:
    - 'malicious' for any positive detection label
    - 'undetected' for NULL / empty / benign / timeout / unsupported labels

    The wide verdict table stores vendor-specific strings rather than boolean
    detection flags, so explicit non-detection tokens must be excluded first.
    """
    union_parts = []

    verdicts_table = schema_map.table("vendor_verdicts")
    for engine in valid_engines:
        if restrict_to_selected_samples:
            source_sql = (
                f"{verdicts_table} AS verdict_row "
                "INNER JOIN selected_samples AS selected "
                "ON selected.sample_id = verdict_row.sample_id"
            )
            sample_id_ref = "verdict_row.sample_id"
            engine_ref = f"verdict_row.`{engine}`"
        else:
            source_sql = verdicts_table
            sample_id_ref = "sample_id"
            engine_ref = f"`{engine}`"
        sql = f"""
            SELECT {sample_id_ref} AS sample_id, '{engine}' AS engine,
                CASE
                    WHEN {sql_non_detection_predicate(engine_ref)}
                        THEN 'undetected'
                    ELSE 'malicious'
                END AS verdict
            FROM {source_sql}
        """
        union_parts.append(sql.strip())

    return "\nUNION ALL\n".join(union_parts)

def get_existing_result_columns():
    """
    Returns a set of column names from virustotal_sample_vendor_engine_verdicts.
    """
    try:
        verdicts_table = schema_map.table("vendor_verdicts")
        query = """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = %s
              AND TABLE_SCHEMA = %s
        """
        params = (verdicts_table, schema_map.current_schema())
        _columns, rows = db_engine.execute_query(query, params=params, fetch=True, return_columns=True)
        if _columns != ["COLUMN_NAME"] or not isinstance(rows, list):
            du.print_warning("[ERROR] Unexpected schema result format.")
            return set()
        return {r[0] for r in rows if isinstance(r, tuple) and r and r[0]}

    except Exception as e:
        du.print_warning(f"[ERROR] Failed to retrieve result columns: {e}")
        return set()


def get_sample_malicious_score(min_engines=5, sample_ids=None):
    """Return trusted-engine scores, optionally restricted to one cohort.

    The enrichment caller only merges rows for its current feature matrix.  A
    scoped query avoids re-aggregating the entire verdict corpus for every
    pipeline run while preserving the former unscoped behavior for callers
    that do not provide sample IDs.
    """
    try:
        trusted_engines = _get_normalized_trusted_engines()
        if not trusted_engines:
            return ([], [])

        valid_engines = _filter_valid_engine_columns(trusted_engines)
        if not valid_engines:
            return ([], [])

        selected_ids = None
        if sample_ids is not None:
            selected_ids = sorted({int(sample_id) for sample_id in sample_ids})
            if not selected_ids:
                return ([], [])

        query = _build_malicious_score_query(
            valid_engines,
            min_engines,
            sample_ids=selected_ids,
        )
        _columns, rows = db_engine.execute_query(
            query,
            params=selected_ids,
            fetch=True,
            return_columns=True,
        )

        if not rows:
            du.print_warning("[INFO] Malicious score query returned no rows.")
        return rows, _columns

    except Exception as e:
        du.print_warning(f"[ERROR] Malicious score query failed: {e}")
        return ([], [])


# --- Helper: Fetch and normalize trusted AV engine names ---
def _get_normalized_trusted_engines():
    trusted_engines = get_active_trusted_engines()
    if not trusted_engines:
        du.print_warning("[ERROR] No trusted AV engines found.")
        return []
    return [_normalize_engine_key(e) for e in trusted_engines]


# --- Helper: Filter out trusted engines not found in the wide verdict table ---
def _filter_valid_engine_columns(normalized_engines):
    available_columns = get_existing_result_columns()
    valid_engines = []
    for e in normalized_engines:
        normalized_engine = _normalize_engine_key(e)
        if normalized_engine in available_columns:
            valid_engines.append(normalized_engine)
        elif normalized_engine in _AUXILIARY_NON_VENDOR_SOURCES:
            du.print_debug(
                f"[SKIP] Auxiliary analysis source '{normalized_engine}' is not modeled as a wide vendor verdict column."
            )
        else:
            du.print_warning(
                f"[SKIP] Trusted engine '{normalized_engine}' not found in results table columns."
            )
    if not valid_engines:
        du.print_warning("[ERROR] No valid trusted AV engine columns found in virustotal_sample_vendor_engine_verdicts.")
    return valid_engines


# --- Helper: Build final SQL query for malicious score aggregation ---
def _build_malicious_score_query(valid_engines, min_engines, *, sample_ids=None):
    selected_ids = None if sample_ids is None else sorted({int(sample_id) for sample_id in sample_ids})
    if selected_ids:
        verdicts_table = schema_map.table("vendor_verdicts")
        placeholders = ", ".join(["%s"] * len(selected_ids))
        scope_sql = f"""
            WITH selected_samples AS (
                SELECT DISTINCT sample_id
                FROM {verdicts_table}
                WHERE sample_id IN ({placeholders})
            )
        """
        union_sql = build_union_sql(valid_engines, restrict_to_selected_samples=True)
    else:
        scope_sql = ""
        union_sql = build_union_sql(valid_engines)
    return f"""
        {scope_sql}
        SELECT
            sample_id,
            COUNT(*) AS total_engines,
            SUM(CASE WHEN verdict = 'malicious' THEN 1 ELSE 0 END) AS malicious_engines,
            ROUND(SUM(CASE WHEN verdict = 'malicious' THEN 1 ELSE 0 END) / COUNT(*) * 100, 2) AS malicious_pct,
            CASE
                WHEN ROUND(SUM(CASE WHEN verdict = 'malicious' THEN 1 ELSE 0 END) / COUNT(*) * 100, 2) >= 90 THEN 'High'
                WHEN ROUND(SUM(CASE WHEN verdict = 'malicious' THEN 1 ELSE 0 END) / COUNT(*) * 100, 2) >= 70 THEN 'Medium'
                WHEN ROUND(SUM(CASE WHEN verdict = 'malicious' THEN 1 ELSE 0 END) / COUNT(*) * 100, 2) >= 40 THEN 'Low'
                ELSE 'Minimal'
            END AS detection_confidence,
            CASE
                WHEN SUM(CASE WHEN verdict = 'malicious' THEN 1 ELSE 0 END) = COUNT(*) THEN 'Full Consensus'
                WHEN SUM(CASE WHEN verdict = 'malicious' THEN 1 ELSE 0 END) >= ROUND(COUNT(*) * 0.75) THEN 'Strong Majority'
                WHEN SUM(CASE WHEN verdict = 'malicious' THEN 1 ELSE 0 END) >= ROUND(COUNT(*) * 0.5) THEN 'Split'
                ELSE 'No Consensus'
            END AS consensus_flag
        FROM (
            {union_sql}
        ) AS unified
        GROUP BY sample_id
        HAVING total_engines >= {min_engines}
        ORDER BY malicious_pct DESC
    """
