# Filename: src/obsidiandroid/database/db_sample_timelines_queries.py
# Purpose : Time-based queries for Android malware sample tracking and trend analysis
#
# Canonical implementation; ``database.db_sample_timelines_queries`` is an identity shim.
# Exported from ``obsidiandroid.database`` (see ``facade_manifest.FACADE_EXPORT_NAMES``).

from __future__ import annotations

from . import db_engine
from .db_config import DB_NAME


def _primary(table: str) -> str:
    """Fully qualify a table in the primary Erebus schema."""
    return f"`{DB_NAME}`.`{table}`"


def _canonical_family_expr(column_ref: str = "family_label") -> str:
    """Return SQL expression for timeline-safe family normalization."""
    return (
        "CASE "
        f"WHEN LOWER(TRIM({column_ref})) IN ('cabassous', 'flubot') THEN 'FluBot' "
        f"ELSE TRIM({column_ref}) "
        "END"
    )

# -----------------------------------------------------------------------------
# Timeline Queries: Global and Family-Level
# -----------------------------------------------------------------------------


def fetch_global_sample_timeline():
    """
    Retrieve all malware samples with submission and optional ITW dates.
    """
    family_expr = _canonical_family_expr("family_label")
    query = f"""
        SELECT 
            sample_id,
            sample_label AS sample_name,
            {family_expr} AS family_name,
            vt_first_submission_at_utc AS submission_date,
            vt_first_seen_itw_date   AS itw_date
        FROM {_primary("malware_sample_catalog")}
        WHERE vt_first_submission_at_utc IS NOT NULL
        ORDER BY vt_first_submission_at_utc ASC, sample_id ASC
    """
    return db_engine.execute_query(query, fetch=True, return_columns=True)


def fetch_family_sample_timeline(family_name):
    """
    Retrieve all samples for a given family with valid submission dates.
    """
    family_expr = _canonical_family_expr("family_label")
    query = f"""
        SELECT 
            sample_id,
            sample_label AS sample_name,
            vt_first_submission_at_utc AS submission_date,
            vt_first_seen_itw_date   AS itw_date
        FROM {_primary("malware_sample_catalog")}
        WHERE LOWER(
            REPLACE({family_expr}, 'FluBot', 'flubot')
        ) = LOWER(%s)
          AND vt_first_submission_at_utc IS NOT NULL
        ORDER BY vt_first_submission_at_utc ASC, sample_id ASC
    """
    return db_engine.execute_query(query, params=(family_name,), fetch=True, return_columns=True)


def summarize_family_timelines():
    """
    Summarize submission date range, sample count, and ITW presence for each family.
    """
    family_expr = _canonical_family_expr("family_label")
    query = f"""
        SELECT 
            {family_expr} AS family_name,
            MIN(vt_first_submission_at_utc) AS first_submission,
            MAX(vt_first_submission_at_utc) AS last_submission,
            COUNT(*) AS sample_count,
            SUM(CASE WHEN vt_first_seen_itw_date IS NOT NULL THEN 1 ELSE 0 END) AS itw_sample_count
        FROM {_primary("malware_sample_catalog")}
        WHERE family_label IS NOT NULL
        GROUP BY {family_expr}
        ORDER BY first_submission ASC, family_name ASC
    """
    return db_engine.execute_query(query, fetch=True, return_columns=True)


# -----------------------------------------------------------------------------
# Coverage + Missing Field Analysis
# -----------------------------------------------------------------------------


def get_itw_coverage_overview():
    """
    Count how many samples have or lack ITW (in-the-wild) dates.
    """
    query = f"""
        SELECT
            COUNT(*) AS total_samples,
            SUM(CASE WHEN vt_first_seen_itw_date IS NOT NULL THEN 1 ELSE 0 END) AS with_itw,
            SUM(CASE WHEN vt_first_seen_itw_date IS NULL THEN 1 ELSE 0 END) AS without_itw
        FROM {_primary("malware_sample_catalog")}
        WHERE vt_first_submission_at_utc IS NOT NULL
    """
    return db_engine.execute_query(query, fetch=True, return_columns=True)


def count_missing_timeline_fields():
    """
    Count how many records are missing submission or ITW dates.
    """
    query = f"""
        SELECT 
            COUNT(*) AS total,
            SUM(CASE WHEN vt_first_submission_at_utc IS NULL THEN 1 ELSE 0 END) AS missing_submission,
            SUM(CASE WHEN vt_first_seen_itw_date IS NULL THEN 1 ELSE 0 END) AS missing_itw
        FROM {_primary("malware_sample_catalog")}
    """
    return db_engine.execute_query(query, fetch=True, return_columns=True)


# -----------------------------------------------------------------------------
# Year and Month-Based Timeline Queries
# -----------------------------------------------------------------------------


def fetch_samples_by_year(year):
    """
    Retrieve malware sample timeline records for a specific calendar year.
    """
    family_expr = _canonical_family_expr("family_label")
    query = f"""
        SELECT 
            sample_id,
            sample_label AS sample_name,
            {family_expr} AS family_name,
            vt_first_submission_at_utc AS submission_date,
            vt_first_seen_itw_date   AS itw_date
        FROM {_primary("malware_sample_catalog")}
        WHERE YEAR(vt_first_submission_at_utc) = %s
        ORDER BY vt_first_submission_at_utc ASC, sample_id ASC
    """
    return db_engine.execute_query(query, params=(year,), fetch=True, return_columns=True)


def fetch_submission_trends_by_month():
    """
    Count number of samples submitted per month globally.
    """
    query = f"""
        SELECT 
            DATE_FORMAT(vt_first_submission_at_utc, '%Y-%m') AS month,
            COUNT(*) AS sample_count
        FROM {_primary("malware_sample_catalog")}
        WHERE vt_first_submission_at_utc IS NOT NULL
        GROUP BY month
        ORDER BY month ASC
    """
    return db_engine.execute_query(query, fetch=True, return_columns=True)


def fetch_family_monthly_submission_trend(family_name):
    """
    Monthly submission count for a specific malware family.
    """
    family_expr = _canonical_family_expr("family_label")
    query = f"""
        SELECT 
            DATE_FORMAT(vt_first_submission_at_utc, '%Y-%m') AS month,
            COUNT(*) AS sample_count
        FROM {_primary("malware_sample_catalog")}
        WHERE LOWER(
            REPLACE({family_expr}, 'FluBot', 'flubot')
        ) = LOWER(%s)
          AND vt_first_submission_at_utc IS NOT NULL
        GROUP BY month
        ORDER BY month ASC
    """
    return db_engine.execute_query(query, params=(family_name,), fetch=True, return_columns=True)
