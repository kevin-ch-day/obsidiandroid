"""Authority/triage database contract helpers.

Centralizes live Android authority view, operator triage view, and generic-token
policy table contracts so diagnostics do not duplicate information_schema logic.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from . import db_engine, schema_map


LIVE_AUTHORITY_REQUIRED_COLUMNS: dict[str, list[str]] = {
    schema_map.table("android_sample_family_type_authority_view"): [
        "sample_id",
        "resolved_family_lc",
        "family_slug",
        "type_slug",
        "authority_bucket",
        "authority_gap_reason",
        "raw_vs_authority_status",
    ],
}

CURRENT_OPERATOR_VIEW_COLUMNS: dict[str, list[str]] = {
    schema_map.table("android_missing_resolution_triage_view"): [
        "sample_id",
        "authority_bucket",
        "package_cluster_key",
        "package_cluster_size",
        "review_lane",
        "recommended_action",
    ],
    schema_map.table("vt_false_positive_review_effective_view"): [
        "sample_id",
        "sample_label",
    ],
    schema_map.table("vt_false_positive_review_triage_view"): [
        "sample_id",
        "sample_label",
        "global_policy_bucket",
        "review_lane",
        "recommended_triage_action",
    ],
}

CURRENT_POLICY_TABLE_COLUMNS: dict[str, list[str]] = {
    schema_map.table("vendor_label_generic_tokens"): [
        "normalized_token",
        "token_kind",
    ],
}

AUTHORITY_MAP_COLUMNS = [
    "sample_id",
    "authority_family_slug",
    "authority_family_name",
    "authority_type_slug",
]


def fetch_columns_df() -> pd.DataFrame:
    """Return information_schema columns for the active database."""
    query = """
        SELECT
            table_name,
            column_name
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
        ORDER BY table_name, ordinal_position
    """
    return db_engine.execute_query(query, fetch=True, as_dataframe=True)


def fetch_objects_df() -> pd.DataFrame:
    """Return information_schema tables/views for the active database."""
    query = """
        SELECT table_name, table_type
        FROM information_schema.tables
        WHERE table_schema = DATABASE()
        ORDER BY table_name
    """
    return db_engine.execute_query(query, fetch=True, as_dataframe=True)


def object_presence(objects_df: pd.DataFrame, object_name: str) -> str:
    """Classify an object as ``table``, ``view``, or ``missing``."""
    if objects_df.empty:
        return "missing"
    mask = objects_df["table_name"].astype(str).str.lower() == str(object_name).lower()
    if not mask.any():
        return "missing"
    table_type = str(objects_df.loc[mask, "table_type"].iloc[0]).upper()
    if "VIEW" in table_type:
        return "view"
    return "table"


def object_exists(object_name: str, *, expected_kind: str | None = None) -> bool:
    """Return whether an object exists, optionally restricted to ``table`` or ``view``."""
    status = object_presence(fetch_objects_df(), object_name)
    if expected_kind is None:
        return status != "missing"
    return status == expected_kind


def missing_columns(columns_df: pd.DataFrame, object_name: str, required: list[str]) -> list[str]:
    """Return required columns absent from the object."""
    if columns_df.empty:
        return list(required)
    mask = columns_df["table_name"].astype(str).str.lower() == str(object_name).lower()
    present = {
        str(value).lower()
        for value in columns_df.loc[mask, "column_name"].astype(str).tolist()
    }
    return [column for column in required if column.lower() not in present]


def table_has_column(table_name: str, column_name: str) -> bool:
    """Return whether the current database object has the given column."""
    query = """
        SELECT COUNT(*) AS n
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = %s
          AND column_name = %s
    """
    df = db_engine.execute_query(query, params=(table_name, column_name), fetch=True, as_dataframe=True)
    return bool(
        isinstance(df, pd.DataFrame)
        and not df.empty
        and int(df.iloc[0]["n"]) > 0
    )


def active_column_contract(
    columns_df: pd.DataFrame,
    object_name: str,
    *,
    logical_table_name: str = "vendor_label_generic_tokens",
    logical_column_name: str = "active_flag",
) -> str:
    """Return the active-column compatibility posture for a policy/governance table."""
    if columns_df.empty:
        return "missing"
    mask = columns_df["table_name"].astype(str).str.lower() == str(object_name).lower()
    present = columns_df.loc[mask, "column_name"].astype(str).tolist()
    active_column = schema_map.resolve_existing_column(
        logical_table_name,
        logical_column_name,
        present,
    )
    if active_column == "is_active":
        return "canonical:is_active"
    if active_column == "active_flag":
        return "compat:active_flag"
    return "missing"


def authority_view_present(
    *,
    columns_df: pd.DataFrame | None = None,
    objects_df: pd.DataFrame | None = None,
) -> bool:
    """Return whether the live authority view exists and satisfies its required columns."""
    authority_view = schema_map.table("android_sample_family_type_authority_view")
    objects = objects_df if objects_df is not None else fetch_objects_df()
    if object_presence(objects, authority_view) != "view":
        return False
    columns = columns_df if columns_df is not None else fetch_columns_df()
    required = LIVE_AUTHORITY_REQUIRED_COLUMNS[authority_view]
    return not missing_columns(columns, authority_view, required)


def authority_alias_fact_present() -> bool:
    """Return whether the canonical alias fact table exists."""
    return object_exists(schema_map.table("family_alias_fact"), expected_kind="table")


def legacy_android_family_alias_present() -> bool:
    """Return whether the legacy Android alias table exists."""
    return object_exists("android_malware_family_alias", expected_kind="table")


def _fetch_canonical_alias_df() -> pd.DataFrame:
    """Load alias-token -> canonical-family-slug rows from the canonical alias fact table."""
    active_clause = "WHERE 1 = 1"
    if table_has_column(schema_map.table("family_alias_fact"), "is_active"):
        active_clause = "WHERE is_active = 1"
    return db_engine.execute_query(
        f"""
        SELECT
            LOWER(TRIM(alias_token)) AS alias_token,
            LOWER(TRIM(canonical_family_slug)) AS canonical_family_slug
        FROM {schema_map.table("family_alias_fact")}
        {active_clause}
          AND alias_token IS NOT NULL
          AND canonical_family_slug IS NOT NULL
          AND TRIM(alias_token) <> ''
          AND TRIM(canonical_family_slug) <> ''
        """,
        fetch=True,
        as_dataframe=True,
    )


def _fetch_legacy_alias_df() -> pd.DataFrame:
    """Load alias-token -> canonical-family-slug rows from the legacy Android alias table."""
    alias_active_clause = "AND a.is_active = 1" if table_has_column("android_malware_family_alias", "is_active") else ""
    alias_review_clause = (
        "AND a.review_status = 'accepted'"
        if table_has_column("android_malware_family_alias", "review_status")
        else ""
    )
    family_active_clause = "AND f.is_active = 1" if table_has_column("android_malware_family", "is_active") else ""
    return db_engine.execute_query(
        """
        SELECT
            LOWER(TRIM(a.alias_name)) AS alias_token,
            LOWER(TRIM(f.family_slug)) AS canonical_family_slug
        FROM android_malware_family_alias AS a
        JOIN android_malware_family AS f
          ON f.family_id = a.family_id
        WHERE a.alias_name IS NOT NULL
          {alias_active_clause}
          {alias_review_clause}
          AND TRIM(a.alias_name) <> ''
          AND f.family_slug IS NOT NULL
          {family_active_clause}
          AND TRIM(f.family_slug) <> ''
        """.format(
            alias_active_clause=alias_active_clause,
            alias_review_clause=alias_review_clause,
            family_active_clause=family_active_clause,
        ),
        fetch=True,
        as_dataframe=True,
    )


def load_family_alias_map() -> dict[str, str]:
    """Load alias-token -> canonical-family-slug mappings from canonical and legacy alias sources."""
    frames: list[pd.DataFrame] = []
    legacy_df = pd.DataFrame()
    if authority_alias_fact_present():
        canonical_df = _fetch_canonical_alias_df()
        if isinstance(canonical_df, pd.DataFrame) and not canonical_df.empty:
            frames.append(canonical_df)
    if legacy_android_family_alias_present():
        legacy_df = _fetch_legacy_alias_df()
        if isinstance(legacy_df, pd.DataFrame) and not legacy_df.empty:
            frames.append(legacy_df)
    if not frames:
        return {}
    merged = pd.concat(frames, ignore_index=True)
    merged["alias_token"] = merged["alias_token"].astype(str).str.strip().str.lower()
    merged["canonical_family_slug"] = merged["canonical_family_slug"].astype(str).str.strip().str.lower()
    merged = merged[(merged["alias_token"] != "") & (merged["canonical_family_slug"] != "")]
    # Keep canonical-fact mappings ahead of legacy aliases when both exist.
    merged = merged.drop_duplicates(subset=["alias_token"], keep="first")
    return dict(zip(merged["alias_token"], merged["canonical_family_slug"]))


def load_known_family_and_alias_tokens() -> tuple[set[str], set[str]]:
    """Load known family slugs/names plus alias tokens."""
    known_families = load_active_family_tokens()
    known_aliases = set(load_family_alias_map().keys())
    try:
        from obsidiandroid.labeling.malware_family_constants import FAMILY_ALIASES

        parser_aliases = {
            str(alias_token).strip().lower()
            for alias_token, canonical_family in FAMILY_ALIASES.items()
            if str(alias_token).strip()
            and str(canonical_family).strip().lower() in known_families
        }
        known_aliases |= parser_aliases
    except Exception:
        pass
    return known_families, known_aliases


def load_active_family_tokens() -> set[str]:
    """Load normalized active family slugs and names."""
    family_active_clause = "AND is_active = 1" if table_has_column("android_malware_family", "is_active") else ""
    families_df = db_engine.execute_query(
        """
        SELECT LOWER(TRIM(family_slug)) AS token
        FROM android_malware_family
        WHERE 1 = 1
        {family_active_clause}
          AND family_slug IS NOT NULL
          AND TRIM(family_slug) <> ''
        UNION
        SELECT LOWER(TRIM(family_name)) AS token
        FROM android_malware_family
        WHERE 1 = 1
        {family_active_clause}
          AND family_name IS NOT NULL
          AND TRIM(family_name) <> ''
        """.format(family_active_clause=family_active_clause),
        fetch=True,
        as_dataframe=True,
    )
    if not isinstance(families_df, pd.DataFrame) or families_df.empty:
        return set()
    return set(families_df["token"].dropna().astype(str).str.strip().str.lower())


def fetch_sample_authority_map(sample_ids: list[int]) -> pd.DataFrame:
    """Fetch per-sample authority family/type mappings from live view or SQL fallback."""
    if not sample_ids:
        return pd.DataFrame(columns=AUTHORITY_MAP_COLUMNS)

    parts: list[pd.DataFrame] = []
    use_live_view = authority_view_present()
    chunk_size = 1000
    for start in range(0, len(sample_ids), chunk_size):
        chunk = sample_ids[start : start + chunk_size]
        placeholders = ", ".join(["%s"] * len(chunk))
        if use_live_view:
            query = f"""
                SELECT
                    sample_id,
                    LOWER(TRIM(COALESCE(family_slug, ''))) AS authority_family_slug,
                    LOWER(TRIM(COALESCE(family_name, ''))) AS authority_family_name,
                    LOWER(TRIM(COALESCE(type_slug, ''))) AS authority_type_slug
                FROM {schema_map.table("android_sample_family_type_authority_view")}
                WHERE sample_id IN ({placeholders})
            """
        else:
            family_active_clause = ""
            if table_has_column("android_malware_family", "is_active"):
                family_active_clause = "AND fam.is_active = 1"
            query = f"""
                SELECT
                    msc.sample_id,
                    LOWER(TRIM(COALESCE(fam.family_slug, ''))) AS authority_family_slug,
                    LOWER(TRIM(COALESCE(fam.family_name, ''))) AS authority_family_name,
                    LOWER(TRIM(COALESCE(typ.type_slug, ''))) AS authority_type_slug
                FROM malware_sample_catalog AS msc
                LEFT JOIN (
                    SELECT sample_id, resolved_family_lc
                    FROM (
                        SELECT
                            v0.sample_id,
                            v0.resolved_family_lc,
                            ROW_NUMBER() OVER (
                                PARTITION BY v0.sample_id
                                ORDER BY COALESCE(v0.resolved_family_lc, '') ASC, v0.sample_id ASC
                            ) AS rn
                        FROM v_android_apk_family_resolved AS v0
                    ) AS ranked_family
                    WHERE rn = 1
                ) AS fam_res
                    ON fam_res.sample_id = msc.sample_id
                LEFT JOIN android_malware_family AS fam
                    ON LOWER(TRIM(fam.family_slug)) = fam_res.resolved_family_lc
                   {family_active_clause}
                LEFT JOIN android_malware_type AS typ
                    ON typ.type_id = fam.primary_type_id
                WHERE msc.sample_id IN ({placeholders})
            """
        part = db_engine.execute_query(query, params=chunk, fetch=True, as_dataframe=True)
        if isinstance(part, pd.DataFrame) and not part.empty:
            parts.append(part)
    if not parts:
        return pd.DataFrame(columns=AUTHORITY_MAP_COLUMNS)
    out = pd.concat(parts, ignore_index=True)
    out["sample_id"] = out["sample_id"].astype(int)
    return out


def evaluate_object_contracts(
    specs: Mapping[str, list[str]],
    *,
    columns_df: pd.DataFrame | None = None,
    objects_df: pd.DataFrame | None = None,
) -> dict[str, dict[str, object]]:
    """Evaluate table/view presence and required-column coverage for a set of objects."""
    columns = columns_df if columns_df is not None else fetch_columns_df()
    objects = objects_df if objects_df is not None else fetch_objects_df()
    out: dict[str, dict[str, object]] = {}
    for object_name, required_columns in specs.items():
        out[object_name] = {
            "presence": object_presence(objects, object_name),
            "missing_columns": missing_columns(columns, object_name, required_columns),
        }
    return out
