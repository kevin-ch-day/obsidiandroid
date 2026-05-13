# Filename: src/obsidiandroid/database/cohort_sql_fragments.py
"""Reusable SQL fragments for cardinality-safe cohort joins (primary DB).

Multi-row VT summary tables, family-resolution outputs, and rows in the artifact
hash registry must be collapsed to one row per natural key *before* joining to
``malware_sample_catalog``, otherwise the cohort query multiplies rows. Uses
MySQL 8+ ``ROW_NUMBER()`` window functions.

Canonical implementation; ``database.cohort_sql_fragments`` is an identity shim.
"""

from __future__ import annotations

# Latest VT scan summary row per sample_id (tie-break: sample_id).
_LATEST_VT_SCAN_SUMMARY_BODY = """
    SELECT z.*
    FROM (
        SELECT
            s0.*,
            ROW_NUMBER() OVER (
                PARTITION BY s0.sample_id
                ORDER BY (s0.updated_at IS NULL) ASC,
                         s0.updated_at DESC,
                         s0.sample_id ASC
            ) AS _vt_scan_rn
        FROM virustotal_sample_scan_summary s0
    ) z
    WHERE z._vt_scan_rn = 1
"""

# One resolved-family row per sample (deterministic lexicographic tie-break).
_LATEST_FAMILY_RESOLUTION_BODY = """
    SELECT z.*
    FROM (
        SELECT
            v0.*,
            ROW_NUMBER() OVER (
                PARTITION BY v0.sample_id
                ORDER BY COALESCE(v0.resolved_family_lc, '') ASC,
                         v0.sample_id ASC
            ) AS _fam_rn
        FROM v_android_apk_family_resolved v0
    ) z
    WHERE z._fam_rn = 1
"""

# One registry row per SHA-256 (deterministic tie-break on md5/sha1).
_LATEST_ARTIFACT_HASH_REGISTRY_BODY = """
    SELECT z.*
    FROM (
        SELECT
            h0.*,
            ROW_NUMBER() OVER (
                PARTITION BY h0.sha256
                ORDER BY COALESCE(h0.md5, '') ASC,
                         COALESCE(h0.sha1, '') ASC,
                         h0.sha256 ASC
            ) AS _artifact_hash_rn
        FROM malware_artifact_hash_registry h0
    ) z
    WHERE z._artifact_hash_rn = 1
"""


def latest_vt_scan_summary_subquery() -> str:
    """Parenthesized subquery: at most one scan-summary row per ``sample_id``."""
    return f"({_LATEST_VT_SCAN_SUMMARY_BODY.strip()})"


def latest_family_resolution_subquery() -> str:
    """Parenthesized subquery: at most one family-resolution row per ``sample_id``."""
    return f"({_LATEST_FAMILY_RESOLUTION_BODY.strip()})"


def latest_artifact_hash_registry_subquery() -> str:
    """Parenthesized subquery: at most one hash-registry row per ``sha256``."""
    return f"({_LATEST_ARTIFACT_HASH_REGISTRY_BODY.strip()})"


__all__ = [
    "latest_artifact_hash_registry_subquery",
    "latest_family_resolution_subquery",
    "latest_vt_scan_summary_subquery",
]
