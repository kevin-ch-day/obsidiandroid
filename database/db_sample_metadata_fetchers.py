"""Database fetchers for Android malware sample metadata cohorts.

Row-count terminology for operators and manifests is centralized in
``analysis/diagnostics/cohort_vocabulary.py`` (SQL profile scope vs prepared cohort).
"""

from __future__ import annotations

from typing import Any

from database import db_engine
from database.cohort_sql_fragments import (
    latest_artifact_hash_registry_subquery,
    latest_family_resolution_subquery,
    latest_vt_scan_summary_subquery,
)


def _cohort_loader_sql_parts(
    *,
    type_slug: str | None,
    min_samples_per_family: int | None,
    require_mapped_family: bool,
    require_sha256: bool,
    allow_missing_package_name: bool,
    exclude_unknown_type_slug: bool,
    effective_time_start_utc: str | None,
    effective_time_end_utc: str | None,
    require_effective_first_seen: bool,
    exclude_family_ids: tuple[int, ...] | None,
    exclude_family_canonical: tuple[str, ...] | None,
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

    if require_mapped_family:
        where_clauses.append("f.family_id IS NOT NULL")

    if require_sha256:
        where_clauses.append("y.sha256 IS NOT NULL")
        where_clauses.append("LENGTH(TRIM(y.sha256)) = 64")

    if not allow_missing_package_name:
        where_clauses.append("COALESCE(TRIM(y.android_package_name), '') <> ''")

    normalized_exclude_canonical = tuple(
        str(family).strip().lower()
        for family in (exclude_family_canonical or ())
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
        if require_mapped_family:
            inner_where_clauses.append("f_inner.family_id IS NOT NULL")
        if require_sha256:
            inner_where_clauses.append("y_inner.sha256 IS NOT NULL")
            inner_where_clauses.append("LENGTH(TRIM(y_inner.sha256)) = 64")
        if not allow_missing_package_name:
            inner_where_clauses.append("COALESCE(TRIM(y_inner.android_package_name), '') <> ''")
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


def fetch_samples_by_type(
    type_slug: str | None,
    min_samples_per_family: int | None = None,
    require_mapped_family: bool = True,
    require_sha256: bool = True,
    allow_missing_package_name: bool = True,
    exclude_unknown_type_slug: bool = False,
    limit: int | None = None,
    effective_time_start_utc: str | None = None,
    effective_time_end_utc: str | None = None,
    require_effective_first_seen: bool = True,
    exclude_family_ids: tuple[int, ...] | None = None,
    exclude_family_canonical: tuple[str, ...] | None = None,
    as_dataframe: bool = False,
):
    """Fetch Android APK samples joined to canonical family/type taxonomy."""
    parts = _cohort_loader_sql_parts(
        type_slug=type_slug,
        min_samples_per_family=min_samples_per_family,
        require_mapped_family=require_mapped_family,
        require_sha256=require_sha256,
        allow_missing_package_name=allow_missing_package_name,
        exclude_unknown_type_slug=exclude_unknown_type_slug,
        effective_time_start_utc=effective_time_start_utc,
        effective_time_end_utc=effective_time_end_utc,
        require_effective_first_seen=require_effective_first_seen,
        exclude_family_ids=exclude_family_ids,
        exclude_family_canonical=exclude_family_canonical,
    )
    params = list(parts["params"])
    where_sql = " AND ".join(parts["where_clauses"])
    scan_one = parts["scan_one"]
    fam_one = parts["fam_one"]
    hash_join_clause = parts["hash_join_clause"]

    limit_clause = ""
    if isinstance(limit, int) and limit > 0:
        limit_clause = "LIMIT %s"
        params.append(limit)

    query = f"""
        SELECT
            y.sample_id,
            y.sha256 AS sha256,
            y.sha256 AS hash_sha256,
            y.sample_label AS sample_name,
            y.family_label AS family_label_raw,
            f.family_id,
            f.family_name AS family_canonical,
            t.type_slug,
            COALESCE(f.family_name, y.family_label) AS family_name,
            y.classification_primary AS category_primary,
            y.classification_subtype AS category_subtype,
            y.vt_suggested_label,
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
        ORDER BY y.sample_id ASC
        {limit_clause}
    """
    return db_engine.execute_query(
        query,
        params=tuple(params),
        fetch=True,
        return_columns=True,
        as_dataframe=as_dataframe,
    )


def get_type_cohort_gate_stats(
    type_slug: str | None,
    min_samples_per_family: int | None = None,
    require_mapped_family: bool = True,
    require_sha256: bool = True,
    allow_missing_package_name: bool = True,
    exclude_unknown_type_slug: bool = False,
    effective_time_start_utc: str | None = None,
    effective_time_end_utc: str | None = None,
    require_effective_first_seen: bool = True,
    exclude_family_ids: tuple[int, ...] | None = None,
    exclude_family_canonical: tuple[str, ...] | None = None,
) -> dict:
    """Return SQL-scope diagnostic counts for the cohort loader (pre-``samples_df``).

    The returned dict mixes **head-count buckets** (marginal ``excluded_*`` fields can
    overlap) with one **conjunctive** count:

    * ``total_candidates`` — rows matching the loose base join + type/time filters
      (cohort **SQL profile scope** head count).
    * ``governed_cohort_count`` / ``final_count_estimate`` — same value: authoritative
      COUNT for the full conjunctive cohort predicate used by ``load_samples_by_type``.
    * ``final_count_estimate_sequential_legacy`` — legacy marginal subtraction; diagnostic
      only when it disagrees with ``governed_cohort_count``.

    See ``analysis/diagnostics/cohort_vocabulary.py`` for how these map to manifest keys.
    """
    hash_one = latest_artifact_hash_registry_subquery()
    hash_join_clause = f"JOIN {hash_one} x ON x.sha256 = y.sha256"
    if not require_sha256:
        hash_join_clause = f"LEFT JOIN {hash_one} x ON x.sha256 = y.sha256"

    scan_one = latest_vt_scan_summary_subquery()
    fam_one = latest_family_resolution_subquery()

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
    normalized_exclude_ids = tuple(
        int(family_id)
        for family_id in (exclude_family_ids or ())
        if str(family_id).strip()
    )
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

    def _scalar(where_extra: str = "") -> int:
        query = f"SELECT COUNT(*) AS c {base_query} {where_extra}"
        _columns, rows = db_engine.execute_query(query, params=params, fetch=True, return_columns=True)
        return int(rows[0][0]) if rows else 0

    total_candidates = _scalar()
    missing_sha256 = _scalar("AND (y.sha256 IS NULL OR LENGTH(TRIM(y.sha256)) <> 64)")
    missing_hash_registry = _scalar(
        "AND y.sha256 IS NOT NULL "
        "AND LENGTH(TRIM(y.sha256)) = 64 "
        "AND x.sha256 IS NULL"
    )
    unmapped_family = _scalar("AND f.family_id IS NULL")
    missing_package = _scalar("AND COALESCE(TRIM(y.android_package_name), '') = ''")
    unknown_type_slug = _scalar("AND COALESCE(LOWER(TRIM(t.type_slug)), '') = 'unknown'")

    low_support_excluded = 0
    if min_samples_per_family is not None:
        q_low = f"""
            SELECT COALESCE(SUM(cnt), 0) AS c
            FROM (
                SELECT f.family_id, COUNT(*) AS cnt
                {base_query}
                  AND f.family_id IS NOT NULL
                GROUP BY f.family_id
                HAVING COUNT(*) < %s
            ) x
        """
        _columns, rows = db_engine.execute_query(
            q_low,
            params=(*(params or ()), int(min_samples_per_family)),
            fetch=True,
            return_columns=True,
        )
        low_support_excluded = int(rows[0][0]) if rows else 0

    # Authoritative row count matching fetch_samples_by_type (conjunctive gates).
    loader_parts = _cohort_loader_sql_parts(
        type_slug=type_slug,
        min_samples_per_family=min_samples_per_family,
        require_mapped_family=require_mapped_family,
        require_sha256=require_sha256,
        allow_missing_package_name=allow_missing_package_name,
        exclude_unknown_type_slug=exclude_unknown_type_slug,
        effective_time_start_utc=effective_time_start_utc,
        effective_time_end_utc=effective_time_end_utc,
        require_effective_first_seen=require_effective_first_seen,
        exclude_family_ids=exclude_family_ids,
        exclude_family_canonical=exclude_family_canonical,
    )
    governed_where = " AND ".join(loader_parts["where_clauses"])
    governed_params = tuple(loader_parts["params"])
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
        "excluded_family_ids": list(normalized_exclude_ids),
        "excluded_family_canonical": list(normalized_exclude_canonical),
        "governed_cohort_count": governed_cohort_count,
        "final_count_estimate": governed_cohort_count,
        "final_count_estimate_sequential_legacy": final_count_legacy,
    }


def fetch_available_android_type_slugs() -> tuple[str, ...]:
    """Fetch canonical Android malware type slugs from DB taxonomy table."""
    query = """
        SELECT type_slug
        FROM android_malware_type
        WHERE type_slug IS NOT NULL AND TRIM(type_slug) <> ''
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
