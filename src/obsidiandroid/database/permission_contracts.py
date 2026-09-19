"""Shared Permission Intel schema-contract helpers."""

from __future__ import annotations

from . import db_engine


_PERMISSION_OBS_NORM_AVAILABLE: bool | None = None


def reset_permission_obs_norm_cache() -> None:
    """Reset cached `permission_string_norm` availability for tests or schema refresh."""
    global _PERMISSION_OBS_NORM_AVAILABLE  # pylint: disable=global-statement
    _PERMISSION_OBS_NORM_AVAILABLE = None


def permission_obs_norm_available() -> bool:
    """Return whether `android_permission_obs_sample` exposes `permission_string_norm`."""
    global _PERMISSION_OBS_NORM_AVAILABLE  # pylint: disable=global-statement
    if _PERMISSION_OBS_NORM_AVAILABLE is None:
        columns = {
            str(col).strip().lower()
            for col in db_engine.get_table_columns("android_permission_obs_sample")
        }
        _PERMISSION_OBS_NORM_AVAILABLE = "permission_string_norm" in columns
    return bool(_PERMISSION_OBS_NORM_AVAILABLE)


def permission_obs_key_expr(*, alias: str | None = None) -> str:
    """Return the canonical SQL expression for permission observation grouping keys."""
    base = "permission_string"
    norm = "permission_string_norm"
    if alias:
        base = f"{alias}.{base}"
        norm = f"{alias}.{norm}"
    if permission_obs_norm_available():
        return f"COALESCE(NULLIF(TRIM({norm}), ''), LOWER(TRIM({base})))"
    return f"LOWER(TRIM({base}))"


AUTHORITY_FACT_SCOPES = frozenset(
    {"permission_definition", "removed_api", "provider_permission"}
)
AUTHORITY_FACT_SCOPES_SQL = (
    "'permission_definition','removed_api','provider_permission'"
)


def _sql_ident(alias: str) -> str:
    """Return a conservative SQL identifier, or raise if the alias is unsafe."""
    text = str(alias or "").strip()
    if not text.replace("_", "").isalnum() or text[0:1].isdigit():
        raise ValueError(f"invalid SQL alias: {alias!r}")
    return text


def _sql_expr(expr: str) -> str:
    """Return a conservative SQL expression, or raise if it looks unsafe."""
    text = str(expr or "").strip()
    if not text or any(character in text for character in ";\n\r") or "--" in text:
        raise ValueError(f"invalid SQL expression: {expr!r}")
    return text


def oem_dictionary_join_predicate(
    *,
    observation_alias: str,
    oem_alias: str,
) -> str:
    """Return the OEM dictionary join predicate.

    Manufacturer authority is table-independent: exact observed token bytes
    plus a resolved ``android_permission_dict_oem.vendor_id``. Observation
    ``vendor_id`` is not a join key (the live warehouse is almost entirely
    NULL), and OEM rows with a NULL vendor are not authorized matches.
    Case-folded or normalized equality over-matches tokens that differ only
    in case or padding.
    """
    obs = _sql_ident(observation_alias)
    oem = _sql_ident(oem_alias)
    return (
        f"BINARY {oem}.permission_string = BINARY {obs}.permission_string"
        f" AND {oem}.vendor_id IS NOT NULL"
    )


def aosp_dictionary_join_predicate(*, raw_expr: str, aosp_alias: str = "a") -> str:
    """Return the AOSP dictionary join predicate.

    ``android_permission_dict_aosp`` is no longer a general authority
    lookup. Interpretation only needs it for exact-byte invalid-token and
    provisional-seed guards; platform identity comes from the deployed v1
    views. Live collation is ``utf8mb4_unicode_ci``, so the token match
    must be ``BINARY``.
    """
    aosp = _sql_ident(aosp_alias)
    raw = _sql_expr(raw_expr)
    return (
        f"BINARY {aosp}.constant_value = BINARY {raw}"
        f" AND ({aosp}.lifecycle_status = 'invalid_token'"
        f" OR {aosp}.authority_source_type = 'queue_apply_shell'"
        f" OR {aosp}.source_family_key = 'aosp_sparse_queue_apply_shell')"
    )


def unknown_dictionary_join_predicate(
    *,
    observation_alias: str,
    unknown_alias: str,
) -> str:
    """Return the unknown-dictionary join predicate.

    Unknown rows are a triage ledger, not signature authority, but the
    join still has to be exact token bytes. Normalized equality attaches
    a stored unknown row to a different-cased observation.
    """
    obs = _sql_ident(observation_alias)
    unknown = _sql_ident(unknown_alias)
    return (
        f"BINARY {unknown}.permission_string = BINARY {obs}.permission_string"
    )


def token_alias_join(
    *,
    raw_expr: str,
    alias_alias: str = "als",
    table_sql: str = "android_permission_token_alias",
) -> str:
    """Return a unique exact-byte case-alias join.

    Live aliases are ``aosp_case_alias_v1``: lowercase ``raw_token`` to the
    accepted catalog ``canonical_token``. Norm equality is always true there
    and must not be used as “no alias”. Multiple rows for one exact raw token
    are a conflict: attach no alias.
    """
    als = _sql_ident(alias_alias)
    raw = _sql_expr(raw_expr)
    table = str(table_sql or "").strip()
    if not table or any(character in table for character in ";\n\r") or "--" in table:
        raise ValueError(f"invalid SQL table: {table_sql!r}")
    return f"""LEFT JOIN (
            SELECT a.*
              FROM {table} a
              INNER JOIN (
                  SELECT MIN(alias_id) AS alias_id
                    FROM {table}
                   GROUP BY BINARY raw_token
                  HAVING COUNT(*) = 1
              ) one ON one.alias_id = a.alias_id
        ) {als}
          ON BINARY {als}.raw_token = BINARY {raw}"""


def catalog_identity_expr(*, raw_expr: str, alias_alias: str = "als") -> str:
    """Return exact catalog bytes after a unique case alias, else the raw token."""
    als = _sql_ident(alias_alias)
    raw = _sql_expr(raw_expr)
    return f"COALESCE({als}.canonical_token, {raw})"


def vt_current_join(
    *,
    raw_expr: str,
    vt_alias: str = "vtc",
    table_sql: str = "android_permission_enrich_vt_current",
) -> str:
    """Return a unique casefold VirusTotal enrichment join.

    Live ``android_permission_enrich_vt_current`` has one row per lowercased
    token, but 461 of those rows differ in case from the accepted catalog.
    Exact-byte equality therefore misses catalog-cased observations.
    Multiple VT rows for one casefold are a conflict: attach none.
    """
    vt = _sql_ident(vt_alias)
    raw = _sql_expr(raw_expr)
    table = str(table_sql or "").strip()
    if not table or any(character in table for character in ";\n\r") or "--" in table:
        raise ValueError(f"invalid SQL table: {table_sql!r}")
    return f"""LEFT JOIN (
            SELECT v.*
              FROM {table} v
              INNER JOIN (
                  SELECT MIN(permission_string) AS permission_string
                    FROM {table}
                   GROUP BY LOWER(permission_string)
                  HAVING COUNT(*) = 1
              ) one ON BINARY one.permission_string = BINARY v.permission_string
        ) {vt}
          ON LOWER({vt}.permission_string) = LOWER({raw})"""


def authority_fact_join(
    *,
    raw_expr: str,
    fact_alias: str = "paf",
    table_sql: str = "android_permission_authority_fact",
) -> str:
    """Return a unique current-best authority-fact join.

    Live uniqueness is ``(permission_string_norm, authority_source_type,
    authority_url)``, not the token. Google Auth tokens currently have a
    ``permission_definition`` fact plus a non-authoritative
    ``custom_permission_pattern`` backfill. Uniqueness is therefore among
    authority-bearing scopes only; multiple definition/provider/removed facts
    are a conflict and attach no fact.
    """
    fact = _sql_ident(fact_alias)
    raw = _sql_expr(raw_expr)
    table = str(table_sql or "").strip()
    if not table or any(character in table for character in ";\n\r") or "--" in table:
        raise ValueError(f"invalid SQL table: {table_sql!r}")
    return f"""LEFT JOIN (
            SELECT f.*
              FROM {table} f
              INNER JOIN (
                  SELECT MIN(authority_fact_id) AS authority_fact_id
                    FROM {table}
                   WHERE is_current_best = 1
                     AND fact_scope IN ({AUTHORITY_FACT_SCOPES_SQL})
                   GROUP BY BINARY permission_string
                  HAVING COUNT(*) = 1
              ) one ON one.authority_fact_id = f.authority_fact_id
        ) {fact}
          ON BINARY {fact}.permission_string = BINARY {raw}"""
