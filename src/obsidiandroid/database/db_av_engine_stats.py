# Filename: src/obsidiandroid/database/db_av_engine_stats.py
#
# Canonical implementation; the repo-root ``database.db_av_engine_stats`` shim
# has been retired. Exported from ``obsidiandroid.database`` (see
# ``facade_manifest.FACADE_EXPORT_NAMES``).

from __future__ import annotations

import re

import pandas as pd

from obsidiandroid.cli.ui import display as du

from . import db_engine
from .verdict_semantics import sql_non_detection_predicate

MALICIOUS_REGEX = "trojan|backdoor|spy|rat|banker|keylogger|stealer|dropper|ransom|clipbank|loader|exploit"
SUSPICIOUS_REGEX = "risktool|adware|grayware|heur|not[-]?a[-]?virus|monitor|obfus|pua|testkey|dualuse|demo"
EMPTY_TOKENS = {"", "none", "null", "n/a", "undetected"}


def _normalize_engine_col(engine_name: str) -> str:
    return engine_name.strip().replace("`", "").replace('"', "").replace("-", "_")


def _get_engine_names(trusted_only: bool = False, active_only: bool = True) -> list:
    filters = []
    if trusted_only:
        filters.append("is_trusted_vendor = 1")
    if active_only:
        filters.append("is_engine_active = 1")

    condition = " AND ".join(filters) if filters else "1=1"
    engine_query = f"""
        SELECT vendor_key AS engine_name
        FROM virustotal_vendor_engines
        WHERE {condition}
        ORDER BY vendor_key
    """
    _, rows = db_engine.execute_query(engine_query, fetch=True, return_columns=True)
    return [_normalize_engine_col(row[0]) for row in rows if row and row[0]]


def _build_result_category_case(column_ref: str) -> str:
    return f"""
        CASE
            WHEN {sql_non_detection_predicate(column_ref)}
                THEN 'undetected'
            WHEN LOWER(TRIM({column_ref})) REGEXP '{MALICIOUS_REGEX}'
                THEN 'malicious'
            WHEN LOWER(TRIM({column_ref})) REGEXP '{SUSPICIOUS_REGEX}'
                THEN 'suspicious'
            ELSE 'malicious'
        END
    """


# -------------------------------------------------------------
# Verdict Distribution
# -------------------------------------------------------------


def get_overall_verdict_distribution(as_dataframe=False):
    engines = _get_engine_names(trusted_only=False, active_only=True)
    if not engines:
        return pd.DataFrame() if as_dataframe else ([], [])

    union_sql = "\nUNION ALL\n".join([
        f"SELECT {_build_result_category_case(f'`{e}`')} AS result_category "
        f"FROM virustotal_sample_vendor_engine_verdicts"
        for e in engines
    ])

    query = f"""
        SELECT result_category, COUNT(*) AS count
        FROM (
            {union_sql}
        ) AS melted
        GROUP BY result_category
        ORDER BY count DESC
    """
    return db_engine.execute_query(query, fetch=True, return_columns=True, as_dataframe=as_dataframe)


# -------------------------------------------------------------
# Consensus Matrix & High-Confidence Detections
# -------------------------------------------------------------


def get_av_verdict_matrix(trusted_only=True, active_only=True):
    engines = _get_engine_names(trusted_only=trusted_only, active_only=active_only)

    if not engines:
        return "", []

    columns = ", ".join([f"`{e}`" for e in engines])
    query = f"SELECT sample_id, {columns} FROM virustotal_sample_vendor_engine_verdicts"
    return query, engines


def get_consensus_malicious_samples(min_pct=90, trusted_only=True, active_only=True, as_dataframe=False):
    query, engines = get_av_verdict_matrix(trusted_only, active_only)
    if not engines:
        du.print_warning("[WARN] No trusted/active engines found.")
        return pd.DataFrame() if as_dataframe else ([], [])

    df = db_engine.execute_query(query, fetch=True, return_columns=True, as_dataframe=True)
    malicious_re = re.compile(MALICIOUS_REGEX)
    df["malicious_count"] = df[engines].apply(
        lambda row: sum(
            isinstance(val, str) and bool(malicious_re.search(val.strip().lower()))
            for val in row
        ),
        axis=1,
    )
    df["total_engines"] = df[engines].apply(
        lambda row: sum(
            pd.notna(val) and (not isinstance(val, str) or val.strip().lower() not in EMPTY_TOKENS)
            for val in row
        ),
        axis=1,
    )
    df["malicious_pct"] = (df["malicious_count"] / df["total_engines"]) * 100
    df = df[df["malicious_pct"] >= min_pct]

    cols = ["sample_id", "total_engines", "malicious_count", "malicious_pct"]
    return df[cols] if as_dataframe else (df[cols].values.tolist(), cols)


# -------------------------------------------------------------
# Sample/Engine-Level Utilities
# -------------------------------------------------------------


def get_samples_by_engine_and_verdict(engine_name: str, result_category: str, as_dataframe=False):
    safe_col = _normalize_engine_col(engine_name)
    category_case = _build_result_category_case(f"`{safe_col}`")
    query = f"""
        SELECT
            sample_id,
            '{safe_col}' AS engine_name,
            `{safe_col}` AS result_label,
            {category_case} AS result_category
        FROM virustotal_sample_vendor_engine_verdicts
        WHERE {category_case} = %s
    """
    return db_engine.execute_query(query, (result_category,), fetch=True, return_columns=True, as_dataframe=as_dataframe)


def get_sample_engine_scan_counts(as_dataframe=False):
    query = """
        SELECT
            sample_id,
            (
                COALESCE(vt_malicious_count, 0) +
                COALESCE(vt_suspicious_count, 0) +
                COALESCE(vt_undetected_count, 0) +
                COALESCE(vt_harmless_count, 0) +
                COALESCE(vt_timeout_count, 0) +
                COALESCE(vt_confirmed_timeout_count, 0) +
                COALESCE(vt_failure_count, 0) +
                COALESCE(vt_type_unsupported_count, 0)
            ) AS engines_scanned
        FROM virustotal_sample_scan_summary
    """
    return db_engine.execute_query(query, fetch=True, return_columns=True, as_dataframe=as_dataframe)


def get_engine_coverage_per_sample(as_dataframe=False):
    engines = _get_engine_names(trusted_only=False, active_only=True)
    if not engines:
        return pd.DataFrame() if as_dataframe else ([], [])

    union_sql = "\nUNION ALL\n".join([
        f"""
        SELECT sample_id, '{engine}' AS engine_name
        FROM virustotal_sample_vendor_engine_verdicts
        WHERE `{engine}` IS NOT NULL
          AND TRIM(LOWER(`{engine}`)) NOT IN ('', 'none', 'null', 'n/a')
        """.strip()
        for engine in engines
    ])

    query = f"""
        SELECT
            engine_name,
            COUNT(DISTINCT sample_id) AS sample_count
        FROM (
            {union_sql}
        ) AS coverage
        GROUP BY engine_name
        ORDER BY sample_count DESC
    """
    return db_engine.execute_query(query, fetch=True, return_columns=True, as_dataframe=as_dataframe)
