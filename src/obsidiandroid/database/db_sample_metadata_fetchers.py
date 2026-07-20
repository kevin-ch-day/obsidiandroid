# Filename: src/obsidiandroid/database/db_sample_metadata_fetchers.py
# Canonical implementation; the repo-root
# ``database.db_sample_metadata_fetchers`` shim has been retired.

"""Database fetchers for Android malware sample metadata cohorts.

Row-count terminology for operators and manifests is centralized in
``analysis/diagnostics/cohort_vocabulary.py`` (SQL profile scope vs prepared cohort).
"""

from __future__ import annotations

from hashlib import sha256
from time import perf_counter
from typing import Any
from collections import Counter

from mysql.connector import Error as MySQLError

from . import db_engine
from .cohort_sql_fragments import (
    latest_artifact_hash_registry_subquery,
    latest_family_resolution_subquery,
    latest_vt_scan_summary_subquery,
)
from obsidiandroid.common.family_label_semantics import family_identity_sql


def _cohort_loader_sql_parts(
    *,
    type_slug: str | None,
    min_samples_per_family: int | None,
    require_mapped_family: bool,
    require_sha256: bool,
    allow_missing_package_name: bool,
    exclude_unknown_type_slug: bool,
    exclude_weak_label_kinds: bool,
    exclude_family_label_conflicts: bool,
    effective_time_start_utc: str | None,
    effective_time_end_utc: str | None,
    require_effective_first_seen: bool,
    include_family_canonical: tuple[str, ...] | None,
    exclude_family_ids: tuple[int, ...] | None,
    exclude_family_canonical: tuple[str, ...] | None,
    require_active_type_slug: bool = False,
) -> dict[str, Any]:
    """Build join clauses and WHERE fragments shared by fetch and gate-stat COUNT.

    Returns:
        dict with hash_join_clause, hash_join_clause_inner, scan_one, fam_one,
        where_clauses (list of SQL predicates), params (flat bind list in order).
    """
    # Support minimum-family-support gates for both single-type and all-type cohorts.
    # When type_slug is None, the threshold applies across the full cohort (all represented types).

    where_clauses = ["y.platform = 'android'", "y.file_extension = 'apk'"]
    params: list[Any] = []
    effective_ts_expr = "COALESCE(y.vt_first_seen_itw_date, y.vt_first_submission_at_utc)"

    if require_effective_first_seen:
        where_clauses.append(f"{effective_ts_expr} IS NOT NULL")
    if effective_time_start_utc:
        where_clauses.append(f"{effective_ts_expr} >= %s")
        params.append(effective_time_start_utc)
    if effective_time_end_utc:
        where_clauses.append(f"{effective_ts_expr} < %s")
        params.append(effective_time_end_utc)

    if type_slug:
        where_clauses.append("t.type_slug = %s")
        params.append(type_slug)
    elif exclude_unknown_type_slug:
        where_clauses.append("COALESCE(LOWER(TRIM(t.type_slug)), '') <> 'unknown'")
        where_clauses.append("COALESCE(TRIM(t.type_slug), '') <> ''")
    if require_active_type_slug:
        where_clauses.append("COALESCE(t.is_active, 0) = 1")

    if require_mapped_family:
        where_clauses.append("f.family_id IS NOT NULL")

    if require_sha256:
        where_clauses.append("y.sha256 IS NOT NULL")
        where_clauses.append("LENGTH(TRIM(y.sha256)) = 64")

    if not allow_missing_package_name:
        where_clauses.append("COALESCE(TRIM(y.android_package_name), '') <> ''")
    family_label_match_override_sql = """
        (
            LOWER(TRIM(COALESCE(y.sample_label, ''))) <> ''
            AND LOWER(TRIM(COALESCE(y.sample_label, ''))) = LOWER(TRIM(COALESCE(y.family_label, '')))
            AND LOWER(TRIM(COALESCE(y.family_label, ''))) = LOWER(TRIM(COALESCE(f.family_name, '')))
            AND LOWER(TRIM(COALESCE(f.family_name, ''))) NOT IN ('', 'unknown', 'other', 'unmapped', 'none', 'null')
        )
    """
    if exclude_weak_label_kinds:
        where_clauses.append(
            f"""(
                COALESCE(LOWER(TRIM(y.sample_label_kind)), '') NOT IN ('filename', 'hash_like', 'opaque_string', 'unclassified')
                OR {family_label_match_override_sql}
            )"""
        )
    if exclude_family_label_conflicts:
        raw_family_identity = family_identity_sql("y.family_label")
        canonical_family_identity = family_identity_sql("f.family_name")
        where_clauses.append(
            f"""
            NOT (
                {raw_family_identity} NOT IN ('', 'unknown', 'generic', 'unclassified', 'unlabeled', 'n_a')
                AND {canonical_family_identity} NOT IN ('', 'unknown', 'other', 'unmapped', 'none', 'null', 'nan', 'n_a')
                AND {raw_family_identity} <> {canonical_family_identity}
            )
            """
        )

    normalized_exclude_canonical = tuple(
        str(family).strip().lower()
        for family in (exclude_family_canonical or ())
        if str(family).strip()
    )
    normalized_include_canonical = tuple(
        str(family).strip().lower()
        for family in (include_family_canonical or ())
        if str(family).strip()
    )
    normalized_exclude_ids = tuple(
        int(family_id)
        for family_id in (exclude_family_ids or ())
        if str(family_id).strip()
    )

    hash_one = latest_artifact_hash_registry_subquery()
    hash_join_clause = f"JOIN {hash_one} x ON x.sha256 = y.sha256"
    hash_join_clause_inner = f"JOIN {hash_one} x_inner ON x_inner.sha256 = y_inner.sha256"
    if not require_sha256:
        hash_join_clause = f"LEFT JOIN {hash_one} x ON x.sha256 = y.sha256"
        hash_join_clause_inner = f"LEFT JOIN {hash_one} x_inner ON x_inner.sha256 = y_inner.sha256"

    scan_one = latest_vt_scan_summary_subquery()
    fam_one = latest_family_resolution_subquery()

    if min_samples_per_family is not None:
        inner_where_clauses = ["y_inner.platform = 'android'", "y_inner.file_extension = 'apk'"]
        inner_params: list[Any] = []
        effective_ts_expr_inner = (
            "COALESCE(y_inner.vt_first_seen_itw_date, y_inner.vt_first_submission_at_utc)"
        )

        if require_effective_first_seen:
            inner_where_clauses.append(f"{effective_ts_expr_inner} IS NOT NULL")
        if effective_time_start_utc:
            inner_where_clauses.append(f"{effective_ts_expr_inner} >= %s")
            inner_params.append(effective_time_start_utc)
        if effective_time_end_utc:
            inner_where_clauses.append(f"{effective_ts_expr_inner} < %s")
            inner_params.append(effective_time_end_utc)
        if type_slug:
            inner_where_clauses.append("t_inner.type_slug = %s")
            inner_params.append(type_slug)
        elif exclude_unknown_type_slug:
            inner_where_clauses.append("COALESCE(LOWER(TRIM(t_inner.type_slug)), '') <> 'unknown'")
            inner_where_clauses.append("COALESCE(TRIM(t_inner.type_slug), '') <> ''")
        if require_active_type_slug:
            inner_where_clauses.append("COALESCE(t_inner.is_active, 0) = 1")
        if require_mapped_family:
            inner_where_clauses.append("f_inner.family_id IS NOT NULL")
        if require_sha256:
            inner_where_clauses.append("y_inner.sha256 IS NOT NULL")
            inner_where_clauses.append("LENGTH(TRIM(y_inner.sha256)) = 64")
        if not allow_missing_package_name:
            inner_where_clauses.append("COALESCE(TRIM(y_inner.android_package_name), '') <> ''")
        if exclude_weak_label_kinds:
            inner_where_clauses.append(
                "COALESCE(LOWER(TRIM(y_inner.sample_label_kind)), '') NOT IN ('filename', 'hash_like', 'opaque_string', 'unclassified')"
            )
        if exclude_family_label_conflicts:
            raw_family_identity_inner = family_identity_sql("y_inner.family_label")
            canonical_family_identity_inner = family_identity_sql("f_inner.family_name")
            inner_where_clauses.append(
                f"""
                NOT (
                    {raw_family_identity_inner} NOT IN ('', 'unknown', 'generic', 'unclassified', 'unlabeled', 'n_a')
                    AND {canonical_family_identity_inner} NOT IN ('', 'unknown', 'other', 'unmapped', 'none', 'null', 'nan', 'n_a')
                    AND {raw_family_identity_inner} <> {canonical_family_identity_inner}
                )
                """
            )
        if normalized_include_canonical:
            placeholders = ", ".join(["%s"] * len(normalized_include_canonical))
            inner_where_clauses.append(
                f"LOWER(TRIM(COALESCE(f_inner.family_name, ''))) IN ({placeholders})"
            )
            inner_params.extend(normalized_include_canonical)
        if normalized_exclude_ids:
            placeholders = ", ".join(["%s"] * len(normalized_exclude_ids))
            inner_where_clauses.append(
                f"(f_inner.family_id IS NULL OR f_inner.family_id NOT IN ({placeholders}))"
            )
            inner_params.extend(normalized_exclude_ids)
        if normalized_exclude_canonical:
            placeholders = ", ".join(["%s"] * len(normalized_exclude_canonical))
            inner_where_clauses.append(
                "(f_inner.family_name IS NULL OR "
                f"LOWER(TRIM(f_inner.family_name)) NOT IN ({placeholders}))"
            )
            inner_params.extend(normalized_exclude_canonical)

        where_clauses.append(
            f"""
            f.family_id IN (
                SELECT f_inner.family_id
                FROM malware_sample_catalog y_inner
                {hash_join_clause_inner}
                LEFT JOIN {scan_one} s_inner ON s_inner.sample_id = y_inner.sample_id
                LEFT JOIN {fam_one} v_inner
                  ON v_inner.sample_id = y_inner.sample_id
                LEFT JOIN android_malware_family f_inner
                  ON LOWER(f_inner.family_slug) = v_inner.resolved_family_lc
                LEFT JOIN android_malware_type t_inner
                  ON t_inner.type_id = f_inner.primary_type_id
                WHERE {" AND ".join(inner_where_clauses)}
                GROUP BY f_inner.family_id
                HAVING COUNT(*) >= %s
            )
            """
        )
        params.extend(inner_params)
        params.append(int(min_samples_per_family))
    if normalized_include_canonical:
        placeholders = ", ".join(["%s"] * len(normalized_include_canonical))
        where_clauses.append(
            f"LOWER(TRIM(COALESCE(f.family_name, ''))) IN ({placeholders})"
        )
        params.extend(normalized_include_canonical)
    if normalized_exclude_ids:
        placeholders = ", ".join(["%s"] * len(normalized_exclude_ids))
        where_clauses.append(f"(f.family_id IS NULL OR f.family_id NOT IN ({placeholders}))")
        params.extend(normalized_exclude_ids)

    if normalized_exclude_canonical:
        placeholders = ", ".join(["%s"] * len(normalized_exclude_canonical))
        where_clauses.append(
            f"(f.family_name IS NULL OR LOWER(TRIM(f.family_name)) NOT IN ({placeholders}))"
        )
        params.extend(normalized_exclude_canonical)

    return {
        "hash_join_clause": hash_join_clause,
        "hash_join_clause_inner": hash_join_clause_inner,
        "scan_one": scan_one,
        "fam_one": fam_one,
        "where_clauses": where_clauses,
        "params": params,
    }


def _profile_viability_predicates(
    *,
    type_slug: str | None,
    require_mapped_family: bool,
    require_sha256: bool,
    allow_missing_package_name: bool,
    exclude_unknown_type_slug: bool,
    exclude_weak_label_kinds: bool,
    exclude_family_label_conflicts: bool,
    effective_time_start_utc: str | None,
    effective_time_end_utc: str | None,
    require_effective_first_seen: bool,
    include_family_canonical: tuple[str, ...] | None,
    exclude_family_ids: tuple[int, ...] | None,
    exclude_family_canonical: tuple[str, ...] | None,
    require_active_type_slug: bool,
) -> tuple[list[str], tuple[Any, ...]]:
    """Reuse the canonical gate predicates without embedding support/count work."""
    parts = _cohort_loader_sql_parts(
        type_slug=type_slug,
        min_samples_per_family=None,
        require_mapped_family=require_mapped_family,
        require_sha256=require_sha256,
        allow_missing_package_name=allow_missing_package_name,
        exclude_unknown_type_slug=exclude_unknown_type_slug,
        exclude_weak_label_kinds=exclude_weak_label_kinds,
        exclude_family_label_conflicts=exclude_family_label_conflicts,
        effective_time_start_utc=effective_time_start_utc,
        effective_time_end_utc=effective_time_end_utc,
        require_effective_first_seen=require_effective_first_seen,
        include_family_canonical=include_family_canonical,
        exclude_family_ids=exclude_family_ids,
        exclude_family_canonical=exclude_family_canonical,
        require_active_type_slug=require_active_type_slug,
    )
    return list(parts["where_clauses"]), tuple(parts["params"])


def build_profile_cohort_viability_query(
    *,
    type_slug: str | None,
    min_samples_per_family: int | None = None,
    require_mapped_family: bool = True,
    require_sha256: bool = True,
    allow_missing_package_name: bool = True,
    exclude_unknown_type_slug: bool = False,
    exclude_weak_label_kinds: bool = False,
    exclude_family_label_conflicts: bool = False,
    effective_time_start_utc: str | None = None,
    effective_time_end_utc: str | None = None,
    require_effective_first_seen: bool = True,
    include_family_canonical: tuple[str, ...] | None = None,
    exclude_family_ids: tuple[int, ...] | None = None,
    exclude_family_canonical: tuple[str, ...] | None = None,
    require_active_type_slug: bool = False,
) -> tuple[str, tuple[Any, ...]]:
    """Build a bounded existence probe for routine menu profile selection.

    This deliberately does not reuse the detailed gate-stat query.  It uses
    the cardinality-safe authority view and the primary-key hash registry for
    eligibility, omits the unused VT scan-summary reduction, and returns at
    most one row.  Exact counts remain available from
    :func:`get_type_cohort_gate_stats` for explicit diagnostics.
    """
    predicates, outer_params = _profile_viability_predicates(
        type_slug=type_slug,
        require_mapped_family=require_mapped_family,
        require_sha256=require_sha256,
        allow_missing_package_name=allow_missing_package_name,
        exclude_unknown_type_slug=exclude_unknown_type_slug,
        exclude_weak_label_kinds=exclude_weak_label_kinds,
        exclude_family_label_conflicts=exclude_family_label_conflicts,
        effective_time_start_utc=effective_time_start_utc,
        effective_time_end_utc=effective_time_end_utc,
        require_effective_first_seen=require_effective_first_seen,
        include_family_canonical=include_family_canonical,
        exclude_family_ids=exclude_family_ids,
        exclude_family_canonical=exclude_family_canonical,
        require_active_type_slug=require_active_type_slug,
    )
    where_sql = " AND ".join(predicates)
    params: list[Any] = list(outer_params)
    if min_samples_per_family is not None:
        # A qualifying family is itself proof that at least one eligible row
        # exists.  Do not scan the same cohort a second time just to test an
        # outer ``IN`` membership predicate.
        params.append(int(min_samples_per_family))
        query = f"""
            SELECT 1
            FROM malware_sample_catalog AS y
            JOIN malware_artifact_hash_registry AS x
              ON x.sha256 = y.sha256
            JOIN v_android_sample_family_type_authority AS a
              ON a.sample_id = y.sample_id
            JOIN android_malware_family AS f
              ON f.family_id = a.family_id
            JOIN android_malware_type AS t
              ON t.type_id = a.type_id
            WHERE {where_sql}
            GROUP BY a.family_id
            HAVING COUNT(*) >= %s
            LIMIT 1
        """
    else:
        query = f"""
        SELECT 1
        FROM malware_sample_catalog AS y
        JOIN malware_artifact_hash_registry AS x
          ON x.sha256 = y.sha256
        JOIN v_android_sample_family_type_authority AS a
          ON a.sample_id = y.sample_id
        JOIN android_malware_family AS f
          ON f.family_id = a.family_id
        JOIN android_malware_type AS t
          ON t.type_id = a.type_id
        WHERE {where_sql}
        LIMIT 1
    """
    return query, tuple(params)


def probe_profile_cohort_viability(
    *,
    timeout_seconds: float = 15.0,
    **kwargs: Any,
) -> dict[str, object]:
    """Return a bounded read-only answer to "does this profile have one row?".

    MariaDB's statement timeout applies only to this existence query.  It does
    not alter server configuration or session state, and a timeout is reported
    as an inconclusive preflight rather than an empty cohort.
    """
    # A direct grouped query against the authority view can still force a full
    # view materialization before MariaDB applies LIMIT.  First inspect a small
    # authority window, then test those concrete sample ids against the catalog
    # and hash registry.  A positive result is exact (three observed members
    # prove support >= 3); an exhausted window is explicitly inconclusive.
    return _probe_profile_cohort_viability_windowed(timeout_seconds=timeout_seconds, **kwargs)


def _probe_profile_cohort_viability_windowed(*, timeout_seconds: float, **kwargs: Any) -> dict[str, object]:
    type_slug = kwargs.get("type_slug")
    min_support = kwargs.get("min_samples_per_family")
    require_mapped = bool(kwargs.get("require_mapped_family", True))
    require_active_type = bool(kwargs.get("require_active_type_slug", False))
    exclude_unknown = bool(kwargs.get("exclude_unknown_type_slug", False))
    include_families = {str(v).strip().lower() for v in (kwargs.get("include_family_canonical") or ()) if str(v).strip()}
    exclude_families = {str(v).strip().lower() for v in (kwargs.get("exclude_family_canonical") or ()) if str(v).strip()}
    exclude_ids = {int(v) for v in (kwargs.get("exclude_family_ids") or ()) if str(v).strip()}
    fingerprint_source = "profile-viability-windowed-v1|" + repr(sorted(kwargs.items()))
    fingerprint = sha256(fingerprint_source.encode("utf-8")).hexdigest()
    started = perf_counter()
    # Keep this intentionally small: the authority surface is a view and the
    # menu needs a fast positive proof, not a census.  A too-small window is
    # reported as inconclusive rather than as an empty cohort.
    candidate_limit = 64
    # The authority surface contains resolved family assignments.  It cannot
    # prove viability for profiles that intentionally admit unresolved rows.
    if not require_mapped:
        return _viability_result(False, "inconclusive_authority_surface", fingerprint, started, timed_out=False)
    authority_sql = f"""
        SELECT a.sample_id, a.family_id, a.family_name, a.type_id, a.type_slug,
               COALESCE(t.is_active, 0) AS type_is_active
        FROM v_android_sample_family_type_authority AS a
        LEFT JOIN android_malware_type AS t ON t.type_id = a.type_id
        LIMIT %s
    """
    try:
        _cols, authority_rows = db_engine.execute_query(
            "SET STATEMENT max_statement_time = %s FOR " + authority_sql,
            params=(max(0.1, min(float(timeout_seconds), 5.0)), candidate_limit),
            fetch=True,
            return_columns=True,
        )
        candidates = {
            int(row[0]): {
                "family_id": int(row[1]),
                "family_name": str(row[2] or "").strip().lower(),
                "type_id": row[3],
                "type_slug": str(row[4] or "").strip().lower(),
                "type_is_active": bool(row[5]),
            }
            for row in authority_rows
            if row and row[0] is not None and row[1] is not None
        }
        candidates = {
            sample_id: value
            for sample_id, value in candidates.items()
            if value["family_id"] not in exclude_ids
            and (not include_families or value["family_name"] in include_families)
            and value["family_name"] not in exclude_families
            and (not type_slug or value["type_slug"] == str(type_slug).strip().lower())
            and (not exclude_unknown or value["type_slug"] not in {"", "unknown"})
            and (not require_active_type or value["type_is_active"])
        }
        if not candidates:
            return _viability_result(False, "inconclusive_candidate_window", fingerprint, started, timed_out=False)
        sample_ids = tuple(candidates)
        catalog_predicates = ["y.platform = 'android'", "y.file_extension = 'apk'", "y.sample_id IN (" + ", ".join(["%s"] * len(sample_ids)) + ")"]
        catalog_params: list[Any] = list(sample_ids)
        if bool(kwargs.get("require_effective_first_seen", True)):
            catalog_predicates.append("COALESCE(y.vt_first_seen_itw_date, y.vt_first_submission_at_utc) IS NOT NULL")
        if kwargs.get("effective_time_start_utc"):
            catalog_predicates.append("COALESCE(y.vt_first_seen_itw_date, y.vt_first_submission_at_utc) >= %s")
            catalog_params.append(kwargs["effective_time_start_utc"])
        if kwargs.get("effective_time_end_utc"):
            catalog_predicates.append("COALESCE(y.vt_first_seen_itw_date, y.vt_first_submission_at_utc) < %s")
            catalog_params.append(kwargs["effective_time_end_utc"])
        if bool(kwargs.get("require_sha256", True)):
            catalog_predicates.extend(["y.sha256 IS NOT NULL", "LENGTH(TRIM(y.sha256)) = 64"])
        if not bool(kwargs.get("allow_missing_package_name", True)):
            catalog_predicates.append("COALESCE(TRIM(y.android_package_name), '') <> ''")
        if bool(kwargs.get("exclude_weak_label_kinds", False)) or bool(kwargs.get("exclude_family_label_conflicts", False)):
            return _viability_result(False, "inconclusive_quality_gate", fingerprint, started, timed_out=False)
        hash_join = "JOIN malware_artifact_hash_registry AS x ON x.sha256 = y.sha256" if bool(kwargs.get("require_sha256", True)) else ""
        catalog_sql = f"SELECT y.sample_id FROM malware_sample_catalog AS y {hash_join} WHERE {' AND '.join(catalog_predicates)}"
        _cols, catalog_rows = db_engine.execute_query(
            "SET STATEMENT max_statement_time = %s FOR " + catalog_sql,
            params=(max(0.1, float(timeout_seconds)), *catalog_params),
            fetch=True,
            return_columns=True,
        )
    except MySQLError as exc:
        message = str(exc).lower()
        timed_out = int(getattr(exc, "errno", 0) or 0) in {1969, 3024} or "max_statement_time" in message
        if timed_out:
            return _viability_result(False, "query_timeout", fingerprint, started, timed_out=True)
        raise
    support = Counter(candidates[int(row[0])]["family_id"] for row in catalog_rows if row and int(row[0]) in candidates)
    if min_support is None:
        return _viability_result(bool(support), "eligible_sample_found" if support else "inconclusive_candidate_window", fingerprint, started, timed_out=False)
    if any(count >= int(min_support) for count in support.values()):
        return _viability_result(True, "eligible_sample_found", fingerprint, started, timed_out=False)
    return _viability_result(False, "inconclusive_candidate_window", fingerprint, started, timed_out=False)


def _viability_result(runnable: bool, reason_code: str, fingerprint: str, started: float, *, timed_out: bool) -> dict[str, object]:
    return {
        "runnable": runnable,
        "reason_code": reason_code,
        "probe_kind": "bounded_candidate_window",
        "query_fingerprint": fingerprint,
        "elapsed_ms": round((perf_counter() - started) * 1000, 3),
        "timed_out": timed_out,
    }


def _cohort_catalog_semantics_base_sql(parts: dict[str, Any]) -> tuple[str, tuple[Any, ...]]:
    """Return a governed-cohort SQL subquery for catalog-semantics profiling."""
    governed_where = " AND ".join(parts["where_clauses"])
    base_sql = f"""
        SELECT
            COALESCE(TRIM(y.analysis_lane), '') AS analysis_lane,
            COALESCE(TRIM(y.sample_label), '') AS sample_label,
            COALESCE(TRIM(y.sample_label_kind), '') AS sample_label_kind,
            COALESCE(TRIM(y.payload_target_platform), '') AS payload_target_platform,
            COALESCE(TRIM(y.payload_target_source), '') AS payload_target_source,
            COALESCE(TRIM(y.unknown_artifact_kind), '') AS unknown_artifact_kind,
            COALESCE(TRIM(y.source_batch_label), '') AS source_batch_label,
            COALESCE(TRIM(f.family_name), '') AS family_canonical,
            COALESCE(TRIM(y.family_label), '') AS family_label_raw,
            COALESCE(TRIM(y.vt_family_token), '') AS vt_family_token,
            COALESCE(TRIM(t.type_slug), '') AS type_slug
        FROM malware_sample_catalog y
        {parts["hash_join_clause"]}
        LEFT JOIN {parts["scan_one"]} s ON s.sample_id = y.sample_id
        LEFT JOIN {parts["fam_one"]} v ON v.sample_id = y.sample_id
        LEFT JOIN android_malware_family f ON LOWER(f.family_slug) = v.resolved_family_lc
        LEFT JOIN android_malware_type t ON t.type_id = f.primary_type_id
        WHERE {governed_where}
    """
    return base_sql, tuple(parts["params"])


def _scalar_semantics_count(base_sql: str, params: tuple[Any, ...], predicate_sql: str) -> int:
    query = f"SELECT COUNT(*) AS c FROM ({base_sql}) sem WHERE {predicate_sql}"
    _columns, rows = db_engine.execute_query(query, params=params, fetch=True, return_columns=True)
    return int(rows[0][0]) if rows else 0


def _semantics_aggregate_counts(base_sql: str, params: tuple[Any, ...]) -> dict[str, int]:
    """Return all scalar semantics counters from one governed-cohort scan."""
    raw_family_identity = family_identity_sql("family_label_raw")
    canonical_family_identity = family_identity_sql("family_canonical")
    query = f"""
        SELECT
            SUM(CASE WHEN LOWER(TRIM(analysis_lane)) <> 'android_artifact' THEN 1 ELSE 0 END) AS non_android_lane_rows,
            SUM(
                CASE
                    WHEN TRIM(payload_target_platform) <> ''
                     AND LOWER(TRIM(payload_target_platform)) <> 'android'
                    THEN 1 ELSE 0
                END
            ) AS non_android_payload_target_rows,
            SUM(CASE WHEN LOWER(TRIM(sample_label_kind)) = 'hash_like' THEN 1 ELSE 0 END) AS hash_like_label_rows,
            SUM(CASE WHEN LOWER(TRIM(sample_label_kind)) = 'opaque_string' THEN 1 ELSE 0 END) AS opaque_label_rows,
            SUM(CASE WHEN LOWER(TRIM(sample_label_kind)) = 'unclassified' THEN 1 ELSE 0 END) AS unclassified_label_rows,
            SUM(CASE WHEN LOWER(TRIM(sample_label_kind)) = 'filename' THEN 1 ELSE 0 END) AS filename_label_rows,
            SUM(CASE WHEN TRIM(vt_family_token) <> '' THEN 1 ELSE 0 END) AS vt_family_token_rows,
            SUM(
                CASE
                    WHEN TRIM(vt_family_token) <> ''
                     AND LOWER(TRIM(family_label_raw)) IN ('', 'unknown', 'generic', 'unclassified', 'unlabeled')
                    THEN 1 ELSE 0
                END
            ) AS blank_family_raw_with_vt_token_rows,
            SUM(
                CASE
                    WHEN LOWER(TRIM(sample_label_kind)) IN ('filename', 'hash_like', 'opaque_string', 'unclassified')
                     AND NOT (
                        LOWER(TRIM(COALESCE(sample_label, ''))) <> ''
                        AND LOWER(TRIM(COALESCE(sample_label, ''))) = LOWER(TRIM(COALESCE(family_label_raw, '')))
                        AND LOWER(TRIM(COALESCE(family_label_raw, ''))) = LOWER(TRIM(COALESCE(family_canonical, '')))
                        AND LOWER(TRIM(COALESCE(family_canonical, ''))) NOT IN ('', 'unknown', 'other', 'unmapped', 'none', 'null')
                     )
                     AND LOWER(TRIM(family_canonical)) NOT IN ('', 'unknown', 'other', 'unmapped', 'none', 'null')
                    THEN 1 ELSE 0
                END
            ) AS weak_label_with_canonical_family_rows,
            SUM(
                CASE
                    WHEN {raw_family_identity} NOT IN ('', 'unknown', 'generic', 'unclassified', 'unlabeled', 'n_a')
                     AND {canonical_family_identity} NOT IN ('', 'unknown', 'other', 'unmapped', 'none', 'null', 'nan', 'n_a')
                     AND {raw_family_identity} <> {canonical_family_identity}
                    THEN 1 ELSE 0
                END
            ) AS raw_family_vs_canonical_conflict_rows
        FROM ({base_sql}) sem
    """
    columns, rows = db_engine.execute_query(query, params=params, fetch=True, return_columns=True)
    if not rows:
        return {}
    row = rows[0]
    return {
        str(columns[idx]): int(row[idx] or 0)
        for idx in range(min(len(columns), len(row)))
    }


def _top_semantics_distribution(
    base_sql: str,
    params: tuple[Any, ...],
    column: str,
    *,
    top_n: int = 20,
) -> dict[str, int]:
    query = f"""
        SELECT
            COALESCE(NULLIF(TRIM({column}), ''), '<blank>') AS label,
            COUNT(*) AS c
        FROM ({base_sql}) sem
        GROUP BY label
        ORDER BY c DESC, label ASC
        LIMIT %s
    """
    _columns, rows = db_engine.execute_query(
        query,
        params=tuple(params) + (int(top_n),),
        fetch=True,
        return_columns=True,
    )
    return {
        str(row[0]): int(row[1])
        for row in rows
        if row and str(row[0]).strip() != ""
    }


def _top_semantics_drift_groups(
    base_sql: str,
    params: tuple[Any, ...],
    group_column: str,
    output_key: str,
    *,
    top_n: int = 10,
) -> list[dict[str, Any]]:
    raw_family_identity = family_identity_sql("family_label_raw")
    canonical_family_identity = family_identity_sql("family_canonical")
    query = f"""
        SELECT
            COALESCE(NULLIF(TRIM({group_column}), ''), '<blank>') AS group_label,
            COUNT(*) AS row_count,
            SUM(CASE WHEN LOWER(TRIM(analysis_lane)) <> 'android_artifact' THEN 1 ELSE 0 END) AS non_android_lane_rows,
            SUM(CASE WHEN TRIM(payload_target_platform) <> '' AND LOWER(TRIM(payload_target_platform)) <> 'android' THEN 1 ELSE 0 END) AS non_android_payload_target_rows,
            SUM(
                CASE
                    WHEN LOWER(TRIM(sample_label_kind)) IN ('filename', 'hash_like', 'opaque_string', 'unclassified')
                     AND LOWER(TRIM(family_canonical)) NOT IN ('', 'unknown', 'other', 'unmapped', 'none', 'null')
                    THEN 1 ELSE 0
                END
            ) AS weak_label_rows,
            SUM(
                CASE
                    WHEN TRIM(vt_family_token) <> ''
                     AND LOWER(TRIM(family_label_raw)) IN ('', 'unknown', 'generic', 'unclassified', 'unlabeled')
                    THEN 1 ELSE 0
                END
            ) AS blank_family_raw_with_vt_token_rows,
            SUM(
                CASE
                    WHEN {raw_family_identity} NOT IN ('', 'unknown', 'generic', 'unclassified', 'unlabeled', 'n_a')
                     AND {canonical_family_identity} NOT IN ('', 'unknown', 'other', 'unmapped', 'none', 'null', 'nan', 'n_a')
                     AND {raw_family_identity} <> {canonical_family_identity}
                    THEN 1 ELSE 0
                END
            ) AS raw_family_vs_canonical_conflict_rows,
            (
                SUM(CASE WHEN LOWER(TRIM(analysis_lane)) <> 'android_artifact' THEN 1 ELSE 0 END)
                + SUM(CASE WHEN TRIM(payload_target_platform) <> '' AND LOWER(TRIM(payload_target_platform)) <> 'android' THEN 1 ELSE 0 END)
                + SUM(
                    CASE
                        WHEN LOWER(TRIM(sample_label_kind)) IN ('filename', 'hash_like', 'opaque_string', 'unclassified')
                         AND LOWER(TRIM(family_canonical)) NOT IN ('', 'unknown', 'other', 'unmapped', 'none', 'null')
                        THEN 1 ELSE 0
                    END
                )
                + SUM(
                    CASE
                        WHEN TRIM(vt_family_token) <> ''
                         AND LOWER(TRIM(family_label_raw)) IN ('', 'unknown', 'generic', 'unclassified', 'unlabeled')
                        THEN 1 ELSE 0
                    END
                )
                + SUM(
                    CASE
                        WHEN {raw_family_identity} NOT IN ('', 'unknown', 'generic', 'unclassified', 'unlabeled', 'n_a')
                         AND {canonical_family_identity} NOT IN ('', 'unknown', 'other', 'unmapped', 'none', 'null', 'nan', 'n_a')
                         AND {raw_family_identity} <> {canonical_family_identity}
                        THEN 1 ELSE 0
                    END
                )
        ) AS issue_events
        FROM ({base_sql}) sem
        GROUP BY group_label
        HAVING issue_events > 0
        ORDER BY issue_events DESC, row_count DESC, group_label ASC
        LIMIT %s
    """
    _columns, rows = db_engine.execute_query(
        query,
        params=tuple(params) + (int(top_n),),
        fetch=True,
        return_columns=True,
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        if not row:
            continue
        out.append(
            {
                output_key: str(row[0]),
                "rows": int(row[1]),
                "non_android_lane_rows": int(row[2]),
                "non_android_payload_target_rows": int(row[3]),
                "weak_label_rows": int(row[4]),
                "blank_family_raw_with_vt_token_rows": int(row[5]),
                "raw_family_vs_canonical_conflict_rows": int(row[6]),
                "issue_events": int(row[7]),
            }
        )
    return out


def fetch_samples_by_type(
    type_slug: str | None,
    min_samples_per_family: int | None = None,
    require_mapped_family: bool = True,
    require_sha256: bool = True,
    allow_missing_package_name: bool = True,
    exclude_unknown_type_slug: bool = False,
    exclude_weak_label_kinds: bool = False,
    exclude_family_label_conflicts: bool = False,
    limit: int | None = None,
    family_cap: int | None = None,
    family_cap_seed: int | None = None,
    type_cap: int | None = None,
    type_cap_seed: int | None = None,
    type_cap_by_slug: dict[str, int] | None = None,
    effective_time_start_utc: str | None = None,
    effective_time_end_utc: str | None = None,
    require_effective_first_seen: bool = True,
    include_family_canonical: tuple[str, ...] | None = None,
    exclude_family_ids: tuple[int, ...] | None = None,
    exclude_family_canonical: tuple[str, ...] | None = None,
    require_active_type_slug: bool = False,
    as_dataframe: bool = False,
):
    """Fetch Android APK samples joined to canonical family/type taxonomy."""
    output_columns = """
                sample_id,
                sha256,
                hash_sha256,
                sample_name,
                sample_label_raw,
                sample_label_kind,
                observed_filename,
                family_label_raw,
                vt_family_token,
                family_id,
                family_canonical,
                type_slug,
                family_name,
                category_primary,
                category_subtype,
                vt_suggested_label,
                analysis_lane,
                payload_target_platform,
                payload_target_source,
                unknown_artifact_kind,
                source_batch_label,
                vt_first_submission_date,
                vt_first_seen_itw_date,
                effective_first_seen_at_utc,
                vt_scan_status,
                package_name,
                android_package_name,
                main_activity,
                target_min_version,
                target_sdk_version,
                permissions,
                vt_malicious_count,
                vt_suspicious_count,
                vt_undetected_count,
                vt_harmless_count,
                vt_timeout_count,
                vt_confirmed_timeout_count,
                vt_failure_count,
                vt_type_unsupported_count,
                vt_reputation,
                vt_times_submitted,
                vt_unique_sources,
                vt_suggested_threat_label,
                vt_tags,
                hash_id,
                hash_md5,
                hash_sha1
    """
    return _execute_samples_by_type_query(
        output_columns=output_columns,
        type_slug=type_slug,
        min_samples_per_family=min_samples_per_family,
        require_mapped_family=require_mapped_family,
        require_sha256=require_sha256,
        allow_missing_package_name=allow_missing_package_name,
        exclude_unknown_type_slug=exclude_unknown_type_slug,
        exclude_weak_label_kinds=exclude_weak_label_kinds,
        exclude_family_label_conflicts=exclude_family_label_conflicts,
        limit=limit,
        family_cap=family_cap,
        family_cap_seed=family_cap_seed,
        type_cap=type_cap,
        type_cap_seed=type_cap_seed,
        type_cap_by_slug=type_cap_by_slug,
        effective_time_start_utc=effective_time_start_utc,
        effective_time_end_utc=effective_time_end_utc,
        require_effective_first_seen=require_effective_first_seen,
        include_family_canonical=include_family_canonical,
        exclude_family_ids=exclude_family_ids,
        exclude_family_canonical=exclude_family_canonical,
        require_active_type_slug=require_active_type_slug,
        as_dataframe=as_dataframe,
    )


def fetch_sample_ids_by_type(
    type_slug: str | None,
    min_samples_per_family: int | None = None,
    require_mapped_family: bool = True,
    require_sha256: bool = True,
    allow_missing_package_name: bool = True,
    exclude_unknown_type_slug: bool = False,
    exclude_weak_label_kinds: bool = False,
    exclude_family_label_conflicts: bool = False,
    limit: int | None = None,
    family_cap: int | None = None,
    family_cap_seed: int | None = None,
    type_cap: int | None = None,
    type_cap_seed: int | None = None,
    type_cap_by_slug: dict[str, int] | None = None,
    effective_time_start_utc: str | None = None,
    effective_time_end_utc: str | None = None,
    require_effective_first_seen: bool = True,
    include_family_canonical: tuple[str, ...] | None = None,
    exclude_family_ids: tuple[int, ...] | None = None,
    exclude_family_canonical: tuple[str, ...] | None = None,
    require_active_type_slug: bool = False,
) -> set[int]:
    """Fetch only governed ``sample_id`` values for a cohort loader query."""
    columns, rows = _execute_samples_by_type_query(
        output_columns="                sample_id",
        type_slug=type_slug,
        min_samples_per_family=min_samples_per_family,
        require_mapped_family=require_mapped_family,
        require_sha256=require_sha256,
        allow_missing_package_name=allow_missing_package_name,
        exclude_unknown_type_slug=exclude_unknown_type_slug,
        exclude_weak_label_kinds=exclude_weak_label_kinds,
        exclude_family_label_conflicts=exclude_family_label_conflicts,
        limit=limit,
        family_cap=family_cap,
        family_cap_seed=family_cap_seed,
        type_cap=type_cap,
        type_cap_seed=type_cap_seed,
        type_cap_by_slug=type_cap_by_slug,
        effective_time_start_utc=effective_time_start_utc,
        effective_time_end_utc=effective_time_end_utc,
        require_effective_first_seen=require_effective_first_seen,
        include_family_canonical=include_family_canonical,
        exclude_family_ids=exclude_family_ids,
        exclude_family_canonical=exclude_family_canonical,
        require_active_type_slug=require_active_type_slug,
        as_dataframe=False,
        id_only_projection=True,
    )
    if not columns or not rows:
        return set()
    sample_idx = next((idx for idx, name in enumerate(columns) if str(name).strip() == "sample_id"), None)
    if sample_idx is None:
        return set()
    return {
        int(sample_id)
        for row in rows
        for sample_id in [row[sample_idx] if len(row) > sample_idx else None]
        if sample_id is not None and str(sample_id).strip() != ""
    }


def _execute_samples_by_type_query(
    *,
    output_columns: str,
    type_slug: str | None,
    min_samples_per_family: int | None = None,
    require_mapped_family: bool = True,
    require_sha256: bool = True,
    allow_missing_package_name: bool = True,
    exclude_unknown_type_slug: bool = False,
    exclude_weak_label_kinds: bool = False,
    exclude_family_label_conflicts: bool = False,
    limit: int | None = None,
    family_cap: int | None = None,
    family_cap_seed: int | None = None,
    type_cap: int | None = None,
    type_cap_seed: int | None = None,
    type_cap_by_slug: dict[str, int] | None = None,
    effective_time_start_utc: str | None = None,
    effective_time_end_utc: str | None = None,
    require_effective_first_seen: bool = True,
    include_family_canonical: tuple[str, ...] | None = None,
    exclude_family_ids: tuple[int, ...] | None = None,
    exclude_family_canonical: tuple[str, ...] | None = None,
    require_active_type_slug: bool = False,
    as_dataframe: bool = False,
    id_only_projection: bool = False,
):
    """Execute the cohort loader query with a caller-provided projection."""
    parts = _cohort_loader_sql_parts(
        type_slug=type_slug,
        min_samples_per_family=min_samples_per_family,
        require_mapped_family=require_mapped_family,
        require_sha256=require_sha256,
        allow_missing_package_name=allow_missing_package_name,
        exclude_unknown_type_slug=exclude_unknown_type_slug,
        exclude_weak_label_kinds=exclude_weak_label_kinds,
        exclude_family_label_conflicts=exclude_family_label_conflicts,
        effective_time_start_utc=effective_time_start_utc,
        effective_time_end_utc=effective_time_end_utc,
        require_effective_first_seen=require_effective_first_seen,
        include_family_canonical=include_family_canonical,
        exclude_family_ids=exclude_family_ids,
        exclude_family_canonical=exclude_family_canonical,
        require_active_type_slug=require_active_type_slug,
    )
    params = list(parts["params"])
    where_sql = " AND ".join(parts["where_clauses"])
    scan_one = parts["scan_one"]
    fam_one = parts["fam_one"]
    hash_join_clause = parts["hash_join_clause"]
    raw_family_identity = family_identity_sql("y.family_label")
    canonical_family_identity = family_identity_sql("f.family_name")

    limit_value = int(limit) if isinstance(limit, int) and limit > 0 else None
    family_cap_value = int(family_cap) if isinstance(family_cap, int) and family_cap > 0 else None
    sampling_seed = int(family_cap_seed) if isinstance(family_cap_seed, int) else 42
    type_cap_value = int(type_cap) if isinstance(type_cap, int) and type_cap > 0 else None
    type_cap_by_slug_value = {
        str(key).strip().lower(): int(value)
        for key, value in (type_cap_by_slug or {}).items()
        if str(key).strip() and isinstance(value, int) and value > 0
    } if isinstance(type_cap_by_slug, dict) else {}
    type_sampling_seed = (
        int(type_cap_seed)
        if isinstance(type_cap_seed, int)
        else int(family_cap_seed) if isinstance(family_cap_seed, int)
        else 42
    )
    needs_rank_wrappers = bool(
        family_cap_value is not None
        or type_cap_value is not None
        or type_cap_by_slug_value
        or limit_value is not None
    )

    if id_only_projection and not needs_rank_wrappers:
        base_select_sql = f"""
            SELECT
                y.sample_id
            FROM malware_sample_catalog y
            {hash_join_clause}
            LEFT JOIN {scan_one} s ON s.sample_id = y.sample_id
            LEFT JOIN {fam_one} v ON v.sample_id = y.sample_id
            LEFT JOIN android_malware_family f ON LOWER(f.family_slug) = v.resolved_family_lc
            LEFT JOIN android_malware_type t ON t.type_id = f.primary_type_id
            WHERE {where_sql}
        """
    elif id_only_projection:
        base_select_sql = f"""
            SELECT
                y.sample_id,
                f.family_id,
                f.family_name AS family_canonical,
                t.type_slug,
                CASE
                    WHEN LOWER(TRIM(COALESCE(y.sample_label_kind, ''))) IN ('filename', 'hash_like', 'opaque_string', 'unclassified')
                    THEN 1 ELSE 0
                END AS _weak_label_rank,
                CASE
                    WHEN f.family_id IS NULL THEN 1 ELSE 0
                END AS _family_mapping_rank,
                CASE
                    WHEN {raw_family_identity} NOT IN ('', 'unknown', 'generic', 'unclassified', 'unlabeled', 'n_a')
                     AND {canonical_family_identity} NOT IN ('', 'unknown', 'other', 'unmapped', 'none', 'null', 'nan', 'n_a')
                     AND {raw_family_identity} <> {canonical_family_identity}
                    THEN 1 ELSE 0
                END AS _family_conflict_rank,
                CASE
                    WHEN COALESCE(LOWER(TRIM(t.type_slug)), '') IN ('', 'unknown') THEN 1 ELSE 0
                END AS _type_unknown_rank,
                LOWER(TRIM(COALESCE(t.type_slug, ''))) AS _type_slug_cap_probe,
                CRC32(CONCAT(%s, ':', COALESCE(CAST(y.sample_id AS CHAR), ''))) AS _loader_order_key,
                CRC32(CONCAT(%s, ':', COALESCE(CAST(y.sample_id AS CHAR), ''))) AS _type_loader_order_key
            FROM malware_sample_catalog y
            {hash_join_clause}
            LEFT JOIN {scan_one} s ON s.sample_id = y.sample_id
            LEFT JOIN {fam_one} v ON v.sample_id = y.sample_id
            LEFT JOIN android_malware_family f ON LOWER(f.family_slug) = v.resolved_family_lc
            LEFT JOIN android_malware_type t ON t.type_id = f.primary_type_id
            WHERE {where_sql}
        """
    elif not needs_rank_wrappers:
        base_select_sql = f"""
            SELECT
                y.sample_id,
                y.sha256 AS sha256,
                y.sha256 AS hash_sha256,
                y.sample_label AS sample_name,
                y.sample_label AS sample_label_raw,
                y.sample_label_kind,
                y.observed_filename,
                y.family_label AS family_label_raw,
                y.vt_family_token,
                f.family_id,
                f.family_name AS family_canonical,
                t.type_slug,
                COALESCE(f.family_name, y.family_label) AS family_name,
                y.classification_primary AS category_primary,
                y.classification_subtype AS category_subtype,
                y.vt_suggested_label,
                y.analysis_lane,
                y.payload_target_platform,
                y.payload_target_source,
                y.unknown_artifact_kind,
                y.source_batch_label,
                y.vt_first_submission_at_utc AS vt_first_submission_date,
                y.vt_first_seen_itw_date AS vt_first_seen_itw_date,
                COALESCE(y.vt_first_seen_itw_date, y.vt_first_submission_at_utc) AS effective_first_seen_at_utc,
                NULL AS vt_scan_status,
                y.android_package_name AS package_name,
                y.android_package_name AS android_package_name,
                y.android_launcher_activity AS main_activity,
                y.android_min_sdk AS target_min_version,
                y.android_target_sdk AS target_sdk_version,
                y.android_permission_count AS permissions,
                s.vt_malicious_count,
                s.vt_suspicious_count,
                s.vt_undetected_count,
                s.vt_harmless_count,
                s.vt_timeout_count,
                s.vt_confirmed_timeout_count,
                s.vt_failure_count,
                s.vt_type_unsupported_count,
                s.vt_reputation,
                s.vt_times_submitted,
                s.vt_unique_sources,
                s.vt_suggested_threat_label,
                s.vt_tags,
                NULL AS hash_id,
                x.md5 AS hash_md5,
                x.sha1 AS hash_sha1
            FROM malware_sample_catalog y
            {hash_join_clause}
            LEFT JOIN {scan_one} s ON s.sample_id = y.sample_id
            LEFT JOIN {fam_one} v ON v.sample_id = y.sample_id
            LEFT JOIN android_malware_family f ON LOWER(f.family_slug) = v.resolved_family_lc
            LEFT JOIN android_malware_type t ON t.type_id = f.primary_type_id
            WHERE {where_sql}
        """
    else:
        base_select_sql = f"""
            SELECT
                y.sample_id,
                y.sha256 AS sha256,
                y.sha256 AS hash_sha256,
                y.sample_label AS sample_name,
                y.sample_label AS sample_label_raw,
                y.sample_label_kind,
                y.observed_filename,
                y.family_label AS family_label_raw,
                y.vt_family_token,
                f.family_id,
                f.family_name AS family_canonical,
                t.type_slug,
                COALESCE(f.family_name, y.family_label) AS family_name,
                y.classification_primary AS category_primary,
                y.classification_subtype AS category_subtype,
                y.vt_suggested_label,
                y.analysis_lane,
                y.payload_target_platform,
                y.payload_target_source,
                y.unknown_artifact_kind,
                y.source_batch_label,
                y.vt_first_submission_at_utc AS vt_first_submission_date,
                y.vt_first_seen_itw_date AS vt_first_seen_itw_date,
                COALESCE(y.vt_first_seen_itw_date, y.vt_first_submission_at_utc) AS effective_first_seen_at_utc,
                NULL AS vt_scan_status,
                y.android_package_name AS package_name,
                y.android_package_name AS android_package_name,
                y.android_launcher_activity AS main_activity,
                y.android_min_sdk AS target_min_version,
                y.android_target_sdk AS target_sdk_version,
                y.android_permission_count AS permissions,
                s.vt_malicious_count,
                s.vt_suspicious_count,
                s.vt_undetected_count,
                s.vt_harmless_count,
                s.vt_timeout_count,
                s.vt_confirmed_timeout_count,
                s.vt_failure_count,
                s.vt_type_unsupported_count,
                s.vt_reputation,
                s.vt_times_submitted,
                s.vt_unique_sources,
                s.vt_suggested_threat_label,
                s.vt_tags,
                NULL AS hash_id,
                x.md5 AS hash_md5,
                x.sha1 AS hash_sha1,
                CASE
                    WHEN LOWER(TRIM(COALESCE(y.sample_label_kind, ''))) IN ('filename', 'hash_like', 'opaque_string', 'unclassified')
                    THEN 1 ELSE 0
                END AS _weak_label_rank,
                CASE
                    WHEN f.family_id IS NULL THEN 1 ELSE 0
                END AS _family_mapping_rank,
                CASE
                    WHEN {raw_family_identity} NOT IN ('', 'unknown', 'generic', 'unclassified', 'unlabeled', 'n_a')
                     AND {canonical_family_identity} NOT IN ('', 'unknown', 'other', 'unmapped', 'none', 'null', 'nan', 'n_a')
                     AND {raw_family_identity} <> {canonical_family_identity}
                    THEN 1 ELSE 0
                END AS _family_conflict_rank,
                CASE
                    WHEN COALESCE(LOWER(TRIM(t.type_slug)), '') IN ('', 'unknown') THEN 1 ELSE 0
                END AS _type_unknown_rank,
                LOWER(TRIM(COALESCE(t.type_slug, ''))) AS _type_slug_cap_probe,
                CRC32(CONCAT(%s, ':', COALESCE(CAST(y.sample_id AS CHAR), ''))) AS _loader_order_key,
                CRC32(CONCAT(%s, ':', COALESCE(CAST(y.sample_id AS CHAR), ''))) AS _type_loader_order_key
            FROM malware_sample_catalog y
            {hash_join_clause}
            LEFT JOIN {scan_one} s ON s.sample_id = y.sample_id
            LEFT JOIN {fam_one} v ON v.sample_id = y.sample_id
            LEFT JOIN android_malware_family f ON LOWER(f.family_slug) = v.resolved_family_lc
            LEFT JOIN android_malware_type t ON t.type_id = f.primary_type_id
            WHERE {where_sql}
        """
    query_params: list[Any] = [sampling_seed, type_sampling_seed, *params] if needs_rank_wrappers else list(params)

    stage_sql = base_select_sql
    stage_alias = "base"

    if family_cap_value is not None:
        stage_sql = f"""
            SELECT
                {stage_alias}.*,
                ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(CAST({stage_alias}.family_id AS CHAR), LOWER(TRIM(COALESCE({stage_alias}.family_canonical, ''))), CONCAT('sample:', CAST({stage_alias}.sample_id AS CHAR)))
                    ORDER BY
                        {stage_alias}._family_mapping_rank ASC,
                        {stage_alias}._weak_label_rank ASC,
                        {stage_alias}._family_conflict_rank ASC,
                        {stage_alias}._type_unknown_rank ASC,
                        {stage_alias}._loader_order_key ASC,
                        {stage_alias}.sample_id ASC
                ) AS _family_loader_rn
            FROM ({stage_sql}) {stage_alias}
        """
        stage_alias = "family_capped"
        query_params.append(family_cap_value)

    final_where_clauses: list[str] = []
    if family_cap_value is not None:
        final_where_clauses.append("_family_loader_rn <= %s")

    if type_cap_value is not None:
        stage_sql = f"""
            SELECT
                {stage_alias}.*,
                ROW_NUMBER() OVER (
                    PARTITION BY COALESCE(LOWER(TRIM(COALESCE({stage_alias}.type_slug, ''))), '<blank>')
                    ORDER BY
                        {stage_alias}._family_mapping_rank ASC,
                        {stage_alias}._weak_label_rank ASC,
                        {stage_alias}._family_conflict_rank ASC,
                        {stage_alias}._type_unknown_rank ASC,
                        {stage_alias}._type_loader_order_key ASC,
                        {stage_alias}.sample_id ASC
                ) AS _type_loader_rn
            FROM ({stage_sql}) {stage_alias}
        """
        stage_alias = "type_capped"
        if not type_cap_by_slug_value:
            final_where_clauses.append("_type_loader_rn <= %s")
            query_params.append(type_cap_value)
    if type_cap_by_slug_value:
        case_clauses: list[str] = []
        for slug, cap in sorted(type_cap_by_slug_value.items()):
            case_clauses.append("WHEN LOWER(TRIM(COALESCE(_type_slug_cap_probe, ''))) = %s THEN %s")
            query_params.extend([slug, cap])
        fallback_cap = type_cap_value if type_cap_value is not None else 999999999
        final_where_clauses.append(
            "_type_loader_rn <= CASE "
            + " ".join(case_clauses)
            + " ELSE %s END"
        )
        query_params.append(fallback_cap)

    final_where_sql = ""
    if final_where_clauses:
        final_where_sql = "\nWHERE " + " AND ".join(final_where_clauses)

    if needs_rank_wrappers:
        query = f"""
            SELECT
{output_columns}
            FROM ({stage_sql}) {stage_alias}
            {final_where_sql}
            ORDER BY
                {stage_alias}._family_mapping_rank ASC,
                {stage_alias}._weak_label_rank ASC,
                {stage_alias}._family_conflict_rank ASC,
                {stage_alias}._type_unknown_rank ASC,
                {stage_alias}._loader_order_key ASC,
                {stage_alias}.sample_id ASC
        """
    else:
        query = base_select_sql

    if limit_value is not None:
        query += "\nLIMIT %s"
        query_params.append(limit_value)

    return db_engine.execute_query(
        query,
        params=tuple(query_params),
        fetch=True,
        return_columns=True,
        as_dataframe=as_dataframe,
        log_label=("cohort_sample_id_load" if id_only_projection else "cohort_metadata_load"),
    )


def get_type_cohort_gate_stats(
    type_slug: str | None,
    min_samples_per_family: int | None = None,
    require_mapped_family: bool = True,
    require_sha256: bool = True,
    allow_missing_package_name: bool = True,
    exclude_unknown_type_slug: bool = False,
    exclude_weak_label_kinds: bool = False,
    exclude_family_label_conflicts: bool = False,
    effective_time_start_utc: str | None = None,
    effective_time_end_utc: str | None = None,
    require_effective_first_seen: bool = True,
    include_family_canonical: tuple[str, ...] | None = None,
    exclude_family_ids: tuple[int, ...] | None = None,
    exclude_family_canonical: tuple[str, ...] | None = None,
    require_active_type_slug: bool = False,
    include_governed_count: bool = True,
) -> dict:
    """Return SQL-scope diagnostic counts for the cohort loader (pre-``samples_df``).

    The returned dict mixes **head-count buckets** (marginal ``excluded_*`` fields can
    overlap) with one **conjunctive** count:

    * ``total_candidates`` — rows matching the loose base join + type/time filters
      (cohort **SQL profile scope** head count).
    * ``governed_cohort_count`` / ``final_count_estimate`` — same value: authoritative
      COUNT for the full conjunctive cohort predicate used by ``load_samples_by_type``.
      Callers that will immediately materialize that loader may set
      ``include_governed_count=False`` and fill this exact value from the loaded
      frame, avoiding a duplicate full-cohort scan.
    * ``final_count_estimate_sequential_legacy`` — legacy marginal subtraction; diagnostic
      only when it disagrees with ``governed_cohort_count``.

    See ``analysis/diagnostics/cohort_vocabulary.py`` for how these map to manifest keys.
    """
    hash_one = latest_artifact_hash_registry_subquery()
    # Gate stats audit exclusion buckets from a left-joined base relation so rows can still
    # be counted as missing hash-registry coverage even when the governed loader later requires
    # a successful hash join.
    hash_join_clause = f"LEFT JOIN {hash_one} x ON x.sha256 = y.sha256"

    scan_one = latest_vt_scan_summary_subquery()
    fam_one = latest_family_resolution_subquery()
    raw_family_identity = family_identity_sql("base.family_label")
    canonical_family_identity = family_identity_sql("base.family_name")

    base_query = f"""
        FROM malware_sample_catalog y
        {hash_join_clause}
        LEFT JOIN {scan_one} s ON s.sample_id = y.sample_id
        LEFT JOIN {fam_one} v ON v.sample_id = y.sample_id
        LEFT JOIN android_malware_family f ON LOWER(f.family_slug) = v.resolved_family_lc
        LEFT JOIN android_malware_type t ON t.type_id = f.primary_type_id
        WHERE y.platform = 'android'
          AND y.file_extension = 'apk'
    """
    params: tuple = ()
    if type_slug:
        base_query += "\n          AND t.type_slug = %s"
        params = (type_slug,)
    if require_effective_first_seen:
        base_query += "\n          AND COALESCE(y.vt_first_seen_itw_date, y.vt_first_submission_at_utc) IS NOT NULL"
    if effective_time_start_utc:
        base_query += "\n          AND COALESCE(y.vt_first_seen_itw_date, y.vt_first_submission_at_utc) >= %s"
        params = tuple(list(params) + [effective_time_start_utc])
    if effective_time_end_utc:
        base_query += "\n          AND COALESCE(y.vt_first_seen_itw_date, y.vt_first_submission_at_utc) < %s"
        params = tuple(list(params) + [effective_time_end_utc])

    normalized_exclude_canonical = tuple(
        str(family).strip().lower()
        for family in (exclude_family_canonical or ())
        if str(family).strip()
    )
    normalized_include_canonical = tuple(
        str(family).strip().lower()
        for family in (include_family_canonical or ())
        if str(family).strip()
    )
    normalized_exclude_ids = tuple(
        int(family_id)
        for family_id in (exclude_family_ids or ())
        if str(family_id).strip()
    )
    if normalized_include_canonical:
        placeholders = ", ".join(["%s"] * len(normalized_include_canonical))
        base_query += (
            "\n          AND "
            f"LOWER(TRIM(COALESCE(f.family_name, ''))) IN ({placeholders})"
        )
        params = tuple(list(params) + list(normalized_include_canonical))
    if normalized_exclude_ids:
        placeholders = ", ".join(["%s"] * len(normalized_exclude_ids))
        base_query += f"\n          AND (f.family_id IS NULL OR f.family_id NOT IN ({placeholders}))"
        params = tuple(list(params) + list(normalized_exclude_ids))
    if normalized_exclude_canonical:
        placeholders = ", ".join(["%s"] * len(normalized_exclude_canonical))
        base_query += (
            "\n          AND "
            f"(f.family_name IS NULL OR LOWER(TRIM(f.family_name)) NOT IN ({placeholders}))"
        )
        params = tuple(list(params) + list(normalized_exclude_canonical))

    aggregate_params: list[Any] = list(params)
    low_support_expr = "0 AS low_support_rows"
    low_support_family_counts_cte = ""
    low_support_join = ""
    if min_samples_per_family is not None:
        low_support_family_counts_cte = """
            , low_support_family_counts AS (
                SELECT base.family_id, COUNT(*) AS family_count
                FROM base_candidates base
                WHERE base.family_id IS NOT NULL
                GROUP BY base.family_id
            )
        """
        low_support_expr = """
            SUM(
                CASE
                    WHEN base.family_id IS NOT NULL
                     AND COALESCE(low_support_family_counts.family_count, 0) < %s
                    THEN 1 ELSE 0
                END
            ) AS low_support_rows
        """
        aggregate_params.append(int(min_samples_per_family))
        low_support_join = """
        LEFT JOIN low_support_family_counts
          ON low_support_family_counts.family_id = base.family_id
        """

    aggregate_sql = f"""
        WITH base_candidates AS (
            SELECT
                y.sha256,
                x.sha256 AS registry_sha256,
                f.family_id,
                f.family_name,
                y.android_package_name,
                t.type_slug,
                t.is_active AS type_is_active,
                y.sample_label_kind,
                y.family_label
            {base_query}
        )
        {low_support_family_counts_cte}
        SELECT
            COUNT(*) AS total_candidates,
            SUM(CASE WHEN base.sha256 IS NULL OR LENGTH(TRIM(base.sha256)) <> 64 THEN 1 ELSE 0 END) AS missing_sha256,
            SUM(
                CASE
                    WHEN base.sha256 IS NOT NULL
                     AND LENGTH(TRIM(base.sha256)) = 64
                     AND base.registry_sha256 IS NULL
                    THEN 1 ELSE 0
                END
            ) AS missing_hash_registry,
            SUM(CASE WHEN base.family_id IS NULL THEN 1 ELSE 0 END) AS unmapped_family,
            SUM(CASE WHEN COALESCE(TRIM(base.android_package_name), '') = '' THEN 1 ELSE 0 END) AS missing_package,
            SUM(CASE WHEN COALESCE(LOWER(TRIM(base.type_slug)), '') = 'unknown' THEN 1 ELSE 0 END) AS unknown_type_slug,
            SUM(CASE WHEN COALESCE(base.type_is_active, 0) <> 1 THEN 1 ELSE 0 END) AS inactive_type_slug,
            SUM(
                CASE
                    WHEN COALESCE(LOWER(TRIM(base.sample_label_kind)), '') IN ('filename', 'hash_like', 'opaque_string', 'unclassified')
                    THEN 1 ELSE 0
                END
            ) AS weak_label_kind_rows,
            SUM(
                CASE
                    WHEN {raw_family_identity} NOT IN ('', 'unknown', 'generic', 'unclassified', 'unlabeled', 'n_a')
                     AND {canonical_family_identity} NOT IN ('', 'unknown', 'other', 'unmapped', 'none', 'null', 'nan', 'n_a')
                     AND {raw_family_identity} <> {canonical_family_identity}
                    THEN 1 ELSE 0
                END
            ) AS family_label_conflict_rows,
            {low_support_expr}
        FROM base_candidates base
        {low_support_join}
    """
    columns, rows = db_engine.execute_query(
        aggregate_sql,
        params=tuple(aggregate_params),
        fetch=True,
        return_columns=True,
        log_label="cohort_gate_stats_aggregate",
    )
    aggregate_map = {
        str(columns[idx]): int((rows[0][idx] if rows else 0) or 0)
        for idx in range(min(len(columns), len(rows[0]) if rows else 0))
    }
    total_candidates = int(aggregate_map.get("total_candidates", 0))
    missing_sha256 = int(aggregate_map.get("missing_sha256", 0))
    missing_hash_registry = int(aggregate_map.get("missing_hash_registry", 0))
    unmapped_family = int(aggregate_map.get("unmapped_family", 0))
    missing_package = int(aggregate_map.get("missing_package", 0))
    unknown_type_slug = int(aggregate_map.get("unknown_type_slug", 0))
    inactive_type_slug = int(aggregate_map.get("inactive_type_slug", 0))
    weak_label_kind_rows = int(aggregate_map.get("weak_label_kind_rows", 0))
    family_label_conflict_rows = int(aggregate_map.get("family_label_conflict_rows", 0))

    low_support_excluded = int(aggregate_map.get("low_support_rows", 0))

    # Authoritative row count matching fetch_samples_by_type (conjunctive gates).
    loader_parts = _cohort_loader_sql_parts(
        type_slug=type_slug,
        min_samples_per_family=min_samples_per_family,
        require_mapped_family=require_mapped_family,
        require_sha256=require_sha256,
        allow_missing_package_name=allow_missing_package_name,
        exclude_unknown_type_slug=exclude_unknown_type_slug,
        exclude_weak_label_kinds=exclude_weak_label_kinds,
        exclude_family_label_conflicts=exclude_family_label_conflicts,
        effective_time_start_utc=effective_time_start_utc,
        effective_time_end_utc=effective_time_end_utc,
        require_effective_first_seen=require_effective_first_seen,
        include_family_canonical=include_family_canonical,
        exclude_family_ids=exclude_family_ids,
        exclude_family_canonical=exclude_family_canonical,
        require_active_type_slug=require_active_type_slug,
    )
    governed_where = " AND ".join(loader_parts["where_clauses"])
    governed_params = tuple(loader_parts["params"])
    governed_cohort_count: int | None = None
    if include_governed_count:
        governed_sql = f"""
        SELECT COUNT(*) AS c /* cohort_governed_count */
        FROM malware_sample_catalog y
        {loader_parts["hash_join_clause"]}
        LEFT JOIN {loader_parts["scan_one"]} s ON s.sample_id = y.sample_id
        LEFT JOIN {loader_parts["fam_one"]} v ON v.sample_id = y.sample_id
        LEFT JOIN android_malware_family f ON LOWER(f.family_slug) = v.resolved_family_lc
        LEFT JOIN android_malware_type t ON t.type_id = f.primary_type_id
        WHERE {governed_where}
    """
        _gcolumns, grows = db_engine.execute_query(
            governed_sql,
            params=governed_params,
            fetch=True,
            return_columns=True,
            log_label="cohort_governed_count",
        )
        governed_cohort_count = int(grows[0][0]) if grows else 0

    # Legacy sequential estimate (marginal buckets can overlap — diagnostic only).
    final_count_legacy = total_candidates
    if require_sha256:
        final_count_legacy -= missing_sha256
        final_count_legacy -= missing_hash_registry
    if require_mapped_family:
        final_count_legacy -= unmapped_family
    if not allow_missing_package_name:
        final_count_legacy -= missing_package
    if min_samples_per_family is not None:
        final_count_legacy -= low_support_excluded
    if exclude_unknown_type_slug:
        final_count_legacy -= unknown_type_slug
    final_count_legacy = max(0, final_count_legacy)

    return {
        "type_slug": type_slug or "all",
        "time_window_start_utc": effective_time_start_utc,
        "time_window_end_utc": effective_time_end_utc,
        "total_candidates": total_candidates,
        "excluded_unmapped_family": unmapped_family if require_mapped_family else 0,
        "excluded_missing_sha256": missing_sha256 if require_sha256 else 0,
        "excluded_missing_hash_registry": missing_hash_registry if require_sha256 else 0,
        "excluded_missing_package_name": missing_package if not allow_missing_package_name else 0,
        "excluded_low_support": low_support_excluded if min_samples_per_family is not None else 0,
        "excluded_unknown_type_slug": unknown_type_slug if exclude_unknown_type_slug else 0,
        "excluded_inactive_type_slug": inactive_type_slug if require_active_type_slug else 0,
        "excluded_weak_label_kind": weak_label_kind_rows if exclude_weak_label_kinds else 0,
        "excluded_family_label_conflict": family_label_conflict_rows if exclude_family_label_conflicts else 0,
        "excluded_family_ids": list(normalized_exclude_ids),
        "excluded_family_canonical": list(normalized_exclude_canonical),
        "governed_cohort_count": governed_cohort_count,
        "final_count_estimate": governed_cohort_count,
        "final_count_estimate_sequential_legacy": final_count_legacy,
    }


def get_type_cohort_catalog_semantics_profile(
    type_slug: str | None,
    min_samples_per_family: int | None = None,
    require_mapped_family: bool = True,
    require_sha256: bool = True,
    allow_missing_package_name: bool = True,
    exclude_unknown_type_slug: bool = False,
    exclude_weak_label_kinds: bool = False,
    exclude_family_label_conflicts: bool = False,
    effective_time_start_utc: str | None = None,
    effective_time_end_utc: str | None = None,
    require_effective_first_seen: bool = True,
    exclude_family_ids: tuple[int, ...] | None = None,
    exclude_family_canonical: tuple[str, ...] | None = None,
    include_family_canonical: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Return SQL-scope Android cohort semantics using the governed cohort filters."""
    parts = _cohort_loader_sql_parts(
        type_slug=type_slug,
        min_samples_per_family=min_samples_per_family,
        require_mapped_family=require_mapped_family,
        require_sha256=require_sha256,
        allow_missing_package_name=allow_missing_package_name,
        exclude_unknown_type_slug=exclude_unknown_type_slug,
        exclude_weak_label_kinds=exclude_weak_label_kinds,
        exclude_family_label_conflicts=exclude_family_label_conflicts,
        effective_time_start_utc=effective_time_start_utc,
        effective_time_end_utc=effective_time_end_utc,
        require_effective_first_seen=require_effective_first_seen,
        include_family_canonical=include_family_canonical,
        exclude_family_ids=exclude_family_ids,
        exclude_family_canonical=exclude_family_canonical,
    )
    base_sql, params = _cohort_catalog_semantics_base_sql(parts)
    aggregate_counts = _semantics_aggregate_counts(base_sql, params)
    return {
        "scope": "sql_governed_android_cohort",
        "analysis_lane_distribution": _top_semantics_distribution(base_sql, params, "analysis_lane"),
        "sample_label_kind_distribution": _top_semantics_distribution(base_sql, params, "sample_label_kind"),
        "payload_target_platform_distribution": _top_semantics_distribution(base_sql, params, "payload_target_platform"),
        "payload_target_source_distribution": _top_semantics_distribution(base_sql, params, "payload_target_source"),
        "unknown_artifact_kind_distribution": _top_semantics_distribution(base_sql, params, "unknown_artifact_kind"),
        "source_batch_label_distribution": _top_semantics_distribution(base_sql, params, "source_batch_label"),
        "non_android_lane_rows": int(aggregate_counts.get("non_android_lane_rows", 0)),
        "non_android_payload_target_rows": int(aggregate_counts.get("non_android_payload_target_rows", 0)),
        "hash_like_label_rows": int(aggregate_counts.get("hash_like_label_rows", 0)),
        "opaque_label_rows": int(aggregate_counts.get("opaque_label_rows", 0)),
        "unclassified_label_rows": int(aggregate_counts.get("unclassified_label_rows", 0)),
        "filename_label_rows": int(aggregate_counts.get("filename_label_rows", 0)),
        "vt_family_token_rows": int(aggregate_counts.get("vt_family_token_rows", 0)),
        "blank_family_raw_with_vt_token_rows": int(aggregate_counts.get("blank_family_raw_with_vt_token_rows", 0)),
        "weak_label_with_canonical_family_rows": int(aggregate_counts.get("weak_label_with_canonical_family_rows", 0)),
        "raw_family_vs_canonical_conflict_rows": int(aggregate_counts.get("raw_family_vs_canonical_conflict_rows", 0)),
        "top_drift_families": _top_semantics_drift_groups(base_sql, params, "family_canonical", "family_canonical"),
        "top_drift_types": _top_semantics_drift_groups(base_sql, params, "type_slug", "type_slug"),
        "top_drift_source_batches": _top_semantics_drift_groups(base_sql, params, "source_batch_label", "source_batch_label"),
    }


def fetch_available_android_type_slugs() -> tuple[str, ...]:
    """Fetch active canonical Android malware type slugs from DB taxonomy."""
    query = """
        SELECT type_slug
        FROM android_malware_type
        WHERE is_active = 1
          AND type_slug IS NOT NULL
          AND TRIM(type_slug) <> ''
        ORDER BY type_slug ASC
    """
    _columns, rows = db_engine.execute_query(query, fetch=True, return_columns=True)
    return tuple(str(row[0]).strip() for row in rows if row and str(row[0]).strip())


def fetch_all_android_malware(as_dataframe: bool = False):
    """Retrieve metadata for all Android-tagged malware samples."""
    hash_one = latest_artifact_hash_registry_subquery()
    query = f"""
        SELECT
            y.sample_id,
            y.sample_label AS sample_name,
            y.family_label AS family_name,
            y.classification_primary AS category_primary,
            y.classification_subtype AS category_subtype,
            y.vt_suggested_label,
            y.vt_first_submission_at_utc AS vt_first_submission_date,
            NULL AS vt_scan_status,
            y.android_package_name AS package_name,
            y.android_launcher_activity AS main_activity,
            y.android_min_sdk AS target_min_version,
            y.android_target_sdk AS target_sdk_version,
            y.android_permission_count AS permissions,
            NULL AS hash_id,
            x.md5 AS hash_md5,
            x.sha1 AS hash_sha1,
            x.sha256 AS hash_sha256
        FROM malware_sample_catalog y
        JOIN {hash_one} x ON x.sha256 = y.sha256
        WHERE y.platform = 'android'
        ORDER BY y.sample_id ASC
    """
    return db_engine.execute_query(
        query,
        fetch=True,
        return_columns=True,
        as_dataframe=as_dataframe,
    )


def fetch_android_malware_with_min_family_samples(min_count: int = 3, as_dataframe: bool = False):
    """Get Android malware samples from families with at least ``min_count`` samples."""
    hash_one = latest_artifact_hash_registry_subquery()
    query = f"""
        SELECT
            y.sample_id,
            y.sample_label AS sample_name,
            y.family_label AS family_name,
            y.classification_primary AS category_primary,
            y.classification_subtype AS category_subtype,
            y.vt_suggested_label,
            y.vt_first_submission_at_utc AS vt_first_submission_date,
            NULL AS vt_scan_status,
            y.android_package_name AS package_name,
            y.android_launcher_activity AS main_activity,
            y.android_min_sdk AS target_min_version,
            y.android_target_sdk AS target_sdk_version,
            y.android_permission_count AS permissions,
            NULL AS hash_id,
            x.md5 AS hash_md5,
            x.sha1 AS hash_sha1,
            x.sha256 AS hash_sha256
        FROM malware_sample_catalog y
        JOIN {hash_one} x ON x.sha256 = y.sha256
        WHERE y.platform = 'android'
          AND y.family_label IN (
              SELECT family_label
              FROM malware_sample_catalog
              WHERE platform = 'android' AND family_label IS NOT NULL
              GROUP BY family_label
              HAVING COUNT(*) >= %s
          )
        ORDER BY y.sample_id ASC
    """
    return db_engine.execute_query(
        query,
        params=(min_count,),
        fetch=True,
        return_columns=True,
        as_dataframe=as_dataframe,
    )


def fetch_sample_metadata(sample_id, as_dataframe: bool = False):
    """Return metadata for a specific malware sample ID."""
    query = """
        SELECT
            sample_id,
            sample_label AS sample_name,
            family_label AS family_name,
            vt_suggested_label,
            vt_first_submission_at_utc AS vt_first_submission_date,
            android_target_sdk AS target_sdk_version,
            android_package_name AS package_name,
            sha256 AS hash_sha256
        FROM malware_sample_catalog
        WHERE sample_id = %s
        ORDER BY sample_id ASC
    """
    return db_engine.execute_query(
        query,
        params=(sample_id,),
        fetch=True,
        return_columns=True,
        as_dataframe=as_dataframe,
    )
