"""Read-only family-mapping debt queries for operator triage surfaces."""

from __future__ import annotations

from typing import Any

from obsidiandroid.labeling.taxonomy import is_known_family_name

from . import db_engine
from .db_config import DB_NAME, PERMISSION_INTEL_DB_NAME

_PRIMARY_CATALOG_TABLE = "malware_sample_catalog"
_PERMISSION_OBS_TABLE = "android_permission_obs_sample"
_ANDROID_AUTHORITY_VIEW = "v_android_sample_family_type_authority"
_GENERIC_TOKEN_TABLE = "vendor_label_generic_token_fact"
_VT_CONFIDENCE_TABLE = "vt_sample_verdict_confidence_current"


def _profile_loader_parts(profile_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    from obsidiandroid.cli.profile_manager import load_profile
    from obsidiandroid.pipeline.stage_samples import _resolve_dataset_time_contract

    from .db_sample_metadata_fetchers import _cohort_loader_sql_parts

    profile = load_profile(profile_id)
    gates = profile.get("cohort_gates") or {}
    time_contract = _resolve_dataset_time_contract(gates=gates, run_id="family_mapping_debt")
    parts = _cohort_loader_sql_parts(
        type_slug=profile.get("type_slug_filter"),
        min_samples_per_family=None,
        require_mapped_family=False,
        require_sha256=bool(gates.get("require_sha256", True)),
        allow_missing_package_name=bool(gates.get("allow_missing_package_name", True)),
        exclude_unknown_type_slug=bool(gates.get("exclude_unknown_type_slug", False)),
        exclude_weak_label_kinds=bool(gates.get("exclude_weak_label_kinds", False)),
        exclude_family_label_conflicts=bool(gates.get("exclude_family_label_conflicts", False)),
        effective_time_start_utc=time_contract.get("start_utc"),
        effective_time_end_utc=time_contract.get("end_utc"),
        require_effective_first_seen=bool(time_contract.get("require_effective_first_seen", True)),
        include_family_canonical=tuple(gates.get("include_families") or ()),
        exclude_family_ids=tuple(gates.get("exclude_family_ids") or ()),
        exclude_family_canonical=tuple(gates.get("exclude_families") or ()),
    )
    return profile, parts


def _family_mapping_lane_case_sql() -> str:
    return """
        CASE
            WHEN COALESCE(TRIM(v.resolved_family_lc), '') = '' THEN 'blank_resolved_slug'
            WHEN f.family_id IS NOT NULL THEN 'mapped_family'
            WHEN gt.token_kind IS NOT NULL THEN 'policy_held_resolved_slug'
            ELSE 'true_unmapped_resolved_slug'
        END
    """


def fetch_blank_resolved_outside_missing_resolution_rows() -> list[dict[str, Any]]:
    """Return PI+Android rows with blank resolved slugs outside the missing-resolution view."""
    query = f"""
        WITH pi AS (
            SELECT DISTINCT sample_id
            FROM `{PERMISSION_INTEL_DB_NAME}`.`{_PERMISSION_OBS_TABLE}`
            WHERE sample_id IS NOT NULL
        ),
        blank AS (
            SELECT
                a.sample_id,
                a.android_package_name,
                a.authority_bucket,
                a.authority_gap_reason,
                a.raw_classification_primary,
                a.raw_classification_subtype,
                COALESCE(vs.confidence_bucket, 'none') AS confidence_bucket,
                COALESCE(vs.vt_malicious_count, 0) AS vt_malicious_count
            FROM `{DB_NAME}`.`{_ANDROID_AUTHORITY_VIEW}` AS a
            JOIN pi
              ON pi.sample_id = a.sample_id
            LEFT JOIN `{DB_NAME}`.`{_VT_CONFIDENCE_TABLE}` AS vs
              ON vs.sample_id = a.sample_id
            WHERE LOWER(TRIM(COALESCE(a.platform, ''))) = 'android'
              AND COALESCE(TRIM(a.resolved_family_lc), '') = ''
        )
        SELECT
            blank.*,
            CASE
                WHEN blank.authority_bucket = 'low_signal_singleton_provenance_review'
                    THEN 'singleton_provenance_review'
                WHEN blank.authority_bucket = 'pua_or_provenance_review'
                    THEN 'pua_provenance_review'
                WHEN blank.authority_bucket = 'typed_malware_no_family_signal_review'
                    THEN 'typed_malware_no_family_signal_review'
                WHEN blank.authority_bucket = 'vt_tail_policy_hold_review'
                    THEN 'vt_tail_policy_hold_review'
                WHEN blank.authority_bucket = 'missing_resolved_family'
                    THEN 'missing_resolved_family_outside_view'
                ELSE 'manual_blank_resolved_review'
            END AS review_lane,
            CASE
                WHEN blank.authority_bucket = 'low_signal_singleton_provenance_review'
                    THEN 'Review singleton package provenance before any family mapping.'
                WHEN blank.authority_bucket = 'pua_or_provenance_review'
                    THEN 'Review PUA/provenance posture before assigning a family slug.'
                WHEN blank.authority_bucket = 'typed_malware_no_family_signal_review'
                    THEN 'Review typed-malware evidence without inventing a family slug.'
                WHEN blank.authority_bucket = 'vt_tail_policy_hold_review'
                    THEN 'Keep under policy-held VT-tail review; do not promote to family authority.'
                WHEN blank.authority_bucket = 'missing_resolved_family'
                    THEN 'Investigate why this row is outside the missing-resolution triage view.'
                ELSE 'Manual review for blank resolved-family debt.'
            END AS recommended_triage_action
        FROM blank
        WHERE blank.sample_id NOT IN (
            SELECT sample_id
            FROM `{DB_NAME}`.v_android_missing_resolution_triage
        )
        ORDER BY
            CASE review_lane
                WHEN 'missing_resolved_family_outside_view' THEN 0
                WHEN 'typed_malware_no_family_signal_review' THEN 1
                WHEN 'pua_provenance_review' THEN 2
                WHEN 'singleton_provenance_review' THEN 3
                WHEN 'vt_tail_policy_hold_review' THEN 4
                ELSE 5
            END,
            blank.vt_malicious_count DESC,
            blank.sample_id
    """
    columns, rows = db_engine.execute_query(query, fetch=True, return_columns=True)
    return [dict(zip(columns, row)) for row in rows]


def fetch_blank_resolved_package_clusters(*, limit: int = 15) -> list[dict[str, Any]]:
    """Return top package clusters for blank-resolved rows outside missing-resolution view."""
    query = f"""
        WITH pi AS (
            SELECT DISTINCT sample_id
            FROM `{PERMISSION_INTEL_DB_NAME}`.`{_PERMISSION_OBS_TABLE}`
            WHERE sample_id IS NOT NULL
        ),
        blank AS (
            SELECT
                a.sample_id,
                COALESCE(NULLIF(TRIM(a.android_package_name), ''), '<blank>') AS android_package_name,
                a.authority_bucket
            FROM `{DB_NAME}`.`{_ANDROID_AUTHORITY_VIEW}` AS a
            JOIN pi
              ON pi.sample_id = a.sample_id
            WHERE LOWER(TRIM(COALESCE(a.platform, ''))) = 'android'
              AND COALESCE(TRIM(a.resolved_family_lc), '') = ''
              AND a.sample_id NOT IN (
                  SELECT sample_id
                  FROM `{DB_NAME}`.v_android_missing_resolution_triage
              )
        )
        SELECT
            android_package_name,
            authority_bucket,
            COUNT(*) AS sample_count
        FROM blank
        GROUP BY android_package_name, authority_bucket
        ORDER BY sample_count DESC, android_package_name
        LIMIT {int(limit)}
    """
    columns, rows = db_engine.execute_query(query, fetch=True, return_columns=True)
    return [dict(zip(columns, row)) for row in rows]


def fetch_blank_resolved_family_lane_counts() -> list[dict[str, Any]]:
    """Return authority-bucket counts for Android + PI rows with blank resolved slugs."""
    query = f"""
        WITH pi AS (
            SELECT DISTINCT sample_id
            FROM `{PERMISSION_INTEL_DB_NAME}`.`{_PERMISSION_OBS_TABLE}`
            WHERE sample_id IS NOT NULL
        )
        SELECT
            COALESCE(a.authority_bucket, '<none>') AS authority_bucket,
            COUNT(*) AS sample_count,
            SUM(
                CASE WHEN COALESCE(vs.confidence_bucket, 'none') IN ('high', 'strong') THEN 1 ELSE 0 END
            ) AS high_or_strong_sample_count
        FROM `{DB_NAME}`.`{_PRIMARY_CATALOG_TABLE}` AS msc
        JOIN pi
          ON pi.sample_id = msc.sample_id
        JOIN `{DB_NAME}`.`{_ANDROID_AUTHORITY_VIEW}` AS a
          ON a.sample_id = msc.sample_id
        LEFT JOIN `{DB_NAME}`.`{_VT_CONFIDENCE_TABLE}` AS vs
          ON vs.sample_id = msc.sample_id
        WHERE LOWER(TRIM(COALESCE(msc.platform, ''))) = 'android'
          AND COALESCE(TRIM(a.resolved_family_lc), '') = ''
        GROUP BY authority_bucket
        ORDER BY sample_count DESC, authority_bucket
    """
    columns, rows = db_engine.execute_query(query, fetch=True, return_columns=True)
    return [dict(zip(columns, row)) for row in rows]


def fetch_profile_family_mapping_debt_summary(profile_id: str) -> dict[str, Any]:
    """Summarize governed-SQL family-mapping debt for one profile."""
    profile, parts = _profile_loader_parts(profile_id)
    governed_where = " AND ".join(parts["where_clauses"])
    lane_case = _family_mapping_lane_case_sql()
    query = f"""
        SELECT
            {lane_case} AS mapping_lane,
            COUNT(*) AS sample_count,
            COUNT(DISTINCT v.resolved_family_lc) AS slug_count
        FROM `{DB_NAME}`.`{_PRIMARY_CATALOG_TABLE}` AS y
        {parts["hash_join_clause"]}
        LEFT JOIN {parts["fam_one"]} AS v
          ON v.sample_id = y.sample_id
        LEFT JOIN android_malware_family AS f
          ON LOWER(f.family_slug) = v.resolved_family_lc
        LEFT JOIN android_malware_type AS t
          ON t.type_id = f.primary_type_id
        LEFT JOIN `{DB_NAME}`.`{_GENERIC_TOKEN_TABLE}` AS gt
          ON gt.normalized_token COLLATE utf8mb4_unicode_ci = v.resolved_family_lc COLLATE utf8mb4_unicode_ci
         AND gt.is_active = 1
        WHERE {governed_where}
        GROUP BY mapping_lane
        ORDER BY sample_count DESC, mapping_lane
    """
    columns, rows = db_engine.execute_query(
        query,
        params=tuple(parts["params"]),
        fetch=True,
        return_columns=True,
    )
    lane_rows = [dict(zip(columns, row)) for row in rows]
    lane_counts = {
        str(row.get("mapping_lane", "") or ""): int(row.get("sample_count", 0) or 0)
        for row in lane_rows
    }
    governed_rows = int(sum(lane_counts.values()))
    excluded_unmapped = int(lane_counts.get("blank_resolved_slug", 0) or 0) + int(
        lane_counts.get("policy_held_resolved_slug", 0) or 0
    ) + int(lane_counts.get("true_unmapped_resolved_slug", 0) or 0)
    return {
        "profile_id": profile_id,
        "governed_sql_rows": governed_rows,
        "mapped_family_rows": int(lane_counts.get("mapped_family", 0) or 0),
        "excluded_unmapped_family_rows": excluded_unmapped,
        "blank_resolved_slug_rows": int(lane_counts.get("blank_resolved_slug", 0) or 0),
        "policy_held_resolved_slug_rows": int(lane_counts.get("policy_held_resolved_slug", 0) or 0),
        "true_unmapped_resolved_slug_rows": int(lane_counts.get("true_unmapped_resolved_slug", 0) or 0),
        "lane_counts": lane_counts,
        "lane_rows": lane_rows,
        "interpretation_note": (
            "Profile SQL excluded_unmapped_family counts blank resolved slugs, policy-held resolved slugs, "
            "and true catalog-lag slugs together. Policy-held rows are governance residue, not family authority debt."
        ),
    }


def fetch_profile_family_mapping_debt_rows(
    profile_id: str,
    *,
    include_mapped: bool = False,
) -> list[dict[str, Any]]:
    """Return slug-cluster rows explaining profile-level family-mapping debt."""
    _profile, parts = _profile_loader_parts(profile_id)
    governed_where = " AND ".join(parts["where_clauses"])
    lane_case = _family_mapping_lane_case_sql()
    mapped_filter = "" if include_mapped else f"AND {lane_case.strip()} <> 'mapped_family'"
    query = f"""
        SELECT
            {lane_case} AS mapping_lane,
            COALESCE(NULLIF(TRIM(v.resolved_family_lc), ''), '<blank>') AS resolved_family_lc,
            gt.token_kind,
            COUNT(*) AS sample_count,
            SUM(
                CASE WHEN COALESCE(vs.confidence_bucket, 'none') IN ('high', 'strong') THEN 1 ELSE 0 END
            ) AS high_or_strong_sample_count
        FROM `{DB_NAME}`.`{_PRIMARY_CATALOG_TABLE}` AS y
        {parts["hash_join_clause"]}
        LEFT JOIN {parts["fam_one"]} AS v
          ON v.sample_id = y.sample_id
        LEFT JOIN android_malware_family AS f
          ON LOWER(f.family_slug) = v.resolved_family_lc
        LEFT JOIN android_malware_type AS t
          ON t.type_id = f.primary_type_id
        LEFT JOIN `{DB_NAME}`.`{_GENERIC_TOKEN_TABLE}` AS gt
          ON gt.normalized_token COLLATE utf8mb4_unicode_ci = v.resolved_family_lc COLLATE utf8mb4_unicode_ci
         AND gt.is_active = 1
        LEFT JOIN `{DB_NAME}`.`{_VT_CONFIDENCE_TABLE}` AS vs
          ON vs.sample_id = y.sample_id
        WHERE {governed_where}
        {mapped_filter}
        GROUP BY mapping_lane, resolved_family_lc, token_kind
        ORDER BY
            CASE mapping_lane
                WHEN 'true_unmapped_resolved_slug' THEN 0
                WHEN 'blank_resolved_slug' THEN 1
                WHEN 'policy_held_resolved_slug' THEN 2
                ELSE 3
            END,
            sample_count DESC,
            resolved_family_lc
    """
    columns, rows = db_engine.execute_query(
        query,
        params=tuple(parts["params"]),
        fetch=True,
        return_columns=True,
    )
    out: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(zip(columns, row))
        slug = str(payload.get("resolved_family_lc", "") or "").strip().lower()
        if slug and slug != "<blank>":
            payload["known_locally"] = bool(is_known_family_name(slug))
        else:
            payload["known_locally"] = False
        lane = str(payload.get("mapping_lane", "") or "")
        token_kind = str(payload.get("token_kind", "") or "").strip()
        if lane == "true_unmapped_resolved_slug":
            payload["recommended_next_action"] = (
                "Create or repair android_malware_family mapping for this resolved slug."
                if payload["known_locally"]
                else "Manual review before creating a governed family row for this resolved slug."
            )
        elif lane == "blank_resolved_slug":
            payload["recommended_next_action"] = (
                "Open Android missing-resolution triage and work package/VT-tail provenance lanes."
            )
        elif lane == "policy_held_resolved_slug":
            payload["recommended_next_action"] = (
                "Keep out of family authority; audit policy-held token risk export before promotion."
                if token_kind
                else "Audit policy-held token policy before promotion."
            )
        else:
            payload["recommended_next_action"] = "No mapping debt action required."
        out.append(payload)
    return out
