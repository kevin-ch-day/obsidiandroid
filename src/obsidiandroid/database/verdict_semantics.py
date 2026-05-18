"""Shared verdict-label semantics and schema exclusions for wide AV verdict rows."""

from __future__ import annotations

NON_DETECTION_TOKENS = frozenset(
    {
        "",
        "none",
        "null",
        "n/a",
        "undetected",
        "clean",
        "benign",
        "harmless",
        "safe",
        "approved",
        "verified",
        "type-unsupported",
        "type_unsupported",
        "timeout",
        "failure",
    }
)

VERDICT_METADATA_COLUMNS = frozenset(
    {
        "record_id",
        "sample_id",
        "updated_at",
        "record_created_at",
        "timeout",
        "confirmed_timeout",
        "failure",
        "type_unsupported",
        "malicious",
        "suspicious",
        "undetected",
        "harmless",
        "total_engines",
        "malicious_pct",
        "suspicious_pct",
        "undetected_pct",
        "harmless_pct",
        "av_hits",
    }
)


def normalize_verdict_token(value: object) -> str:
    """Normalize a wide-table vendor verdict to a lowercase comparison token."""
    if value is None:
        return ""
    text = str(value).strip().lower()
    return text


def is_positive_detection_label(value: object) -> int:
    """Return ``1`` when a verdict string represents a positive detection."""
    return int(normalize_verdict_token(value) not in NON_DETECTION_TOKENS)


def sql_non_detection_predicate(column_ref: str) -> str:
    """SQL predicate for labels that should not count as positive detections."""
    token_sql = ", ".join(f"'{token}'" for token in sorted(NON_DETECTION_TOKENS))
    return (
        f"{column_ref} IS NULL OR "
        f"TRIM(LOWER({column_ref})) IN ({token_sql})"
    )
