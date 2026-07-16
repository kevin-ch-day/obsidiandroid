"""Pure family-label comparison semantics shared by SQL, pipeline, and audits.

The database retains a raw family label while the governed taxonomy has a
canonical family name.  Direct string comparison is unsafe because known
aliases (for example, ``Wroba`` and ``RoamingMantis``) identify the same
family.  This module is deliberately dependency-light so database fetchers can
use it without importing the governance package at startup.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from obsidiandroid.labeling.malware_family_constants import FAMILY_ALIASES, normalize_family_name


RAW_FAMILY_MISSING_TOKENS: frozenset[str] = frozenset(
    {"", "unknown", "generic", "unclassified", "unlabeled"}
)
CANONICAL_FAMILY_MISSING_TOKENS: frozenset[str] = frozenset(
    {"", "unknown", "other", "unmapped", "none", "null", "nan", "n/a"}
)
_FAMILY_PLACEHOLDER_PATTERN = re.compile(
    r"^(?:\d+|(?:family|unresolved(?:[\s_-]*family)?)[\s_:=#-]*(?:id[\s_:=#-]*)?\d+)$",
    flags=re.IGNORECASE,
)


def is_family_placeholder_token(value: Any) -> bool:
    """Return whether a display value is an ID-shaped, non-family placeholder."""
    return bool(_FAMILY_PLACEHOLDER_PATTERN.fullmatch(str(value or "").strip()))


def normalize_family_identity_token(value: Any) -> str:
    """Return the parser-normalized token used for family identity comparisons."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    token = str(value).strip().lower()
    if token in CANONICAL_FAMILY_MISSING_TOKENS or is_family_placeholder_token(token):
        return ""
    normalized = normalize_family_name(token)
    return "" if is_family_placeholder_token(normalized) else str(normalized).strip().lower()


def family_label_conflict_mask(
    frame: pd.DataFrame,
    *,
    raw_column: str = "family_label_raw",
    canonical_column: str = "family_canonical",
) -> pd.Series:
    """Return true only for substantive, alias-aware raw/canonical conflicts."""
    raw_source = (
        frame[raw_column]
        if raw_column in frame.columns
        else pd.Series("", index=frame.index, dtype="object")
    )
    canonical_source = (
        frame[canonical_column]
        if canonical_column in frame.columns
        else pd.Series("", index=frame.index, dtype="object")
    )
    raw = raw_source.map(normalize_family_identity_token)
    canonical = canonical_source.map(normalize_family_identity_token)
    return (
        ~raw.isin(RAW_FAMILY_MISSING_TOKENS)
        & ~canonical.isin(CANONICAL_FAMILY_MISSING_TOKENS)
        & raw.ne(canonical)
    )


def family_identity_sql(column_sql: str) -> str:
    """Return a SQL expression matching the stable parser-alias identity rule.

    ``column_sql`` is an internal query identifier, not user input. Alias
    values are application constants and escaped defensively before inclusion.
    Database-only aliases remain visible for curation rather than being silently
    treated as equivalence by a query with no frozen application contract.
    """
    raw = f"LOWER(TRIM(COALESCE({column_sql}, '')))"
    base = (
        "REPLACE(REPLACE(REPLACE(REPLACE("
        f"{raw}, '-', '_'), ' ', '_'), '.', '_'), '/', '_')"
    )
    clauses: list[str] = []
    for alias, _canonical in sorted(FAMILY_ALIASES.items()):
        alias_token = str(alias).strip().lower()
        canonical_token = normalize_family_name(str(alias))
        if not alias_token or not canonical_token or alias_token == canonical_token:
            continue
        escaped_alias = alias_token.replace("'", "''")
        escaped_canonical = canonical_token.replace("'", "''")
        clauses.append(f"WHEN '{escaped_alias}' THEN '{escaped_canonical}'")
    return "CASE " + base + " " + " ".join(clauses) + f" ELSE {base} END"


def is_family_label_conflict(raw_value: Any, canonical_value: Any) -> bool:
    """Convenience scalar form used by small validation callers and tests."""
    frame = pd.DataFrame(
        {"family_label_raw": [raw_value], "family_canonical": [canonical_value]}
    )
    return bool(family_label_conflict_mask(frame).iloc[0])


__all__ = [
    "CANONICAL_FAMILY_MISSING_TOKENS",
    "RAW_FAMILY_MISSING_TOKENS",
    "family_identity_sql",
    "family_label_conflict_mask",
    "is_family_label_conflict",
    "is_family_placeholder_token",
    "normalize_family_identity_token",
]
