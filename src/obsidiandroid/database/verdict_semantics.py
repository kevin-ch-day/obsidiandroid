"""Shared verdict-label semantics and schema exclusions for AV verdict rows."""

from __future__ import annotations

import re

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

GENERIC_SIGNAL_RE = re.compile(
    r"\b("
    r"android|androidos|andr|trojan|agent|generic|malware|dropper|downloader|"
    r"spyware|banker|riskware|pua|pup|adware|heur|heuristic|gen|variant|packed|"
    r"fakeapp|fakeav|rogue|debugkey|testkey|hidden|locker|ransom|smsspy|spy"
    r")\b"
)
PROVENANCE_NOISE_RE = re.compile(
    r"\b("
    r"apk|exe|dll|jar|zip|rar|bin|so|file|hash|unclassified|phishing|"
    r"setup|uninstall|lib[a-z0-9_]+|classes\.dex|base\.apk"
    r")\b"
)
OVERLAP_SIGNAL_RE = re.compile(
    r"\b("
    r"boogr|hqwar|bankbot|spynote|spyagent|secimage|penguin|metasploit|"
    r"cerberus|copybara|basbanke|svpeng|blacklister|kidlogger|pnsms|ftzo"
    r")\b"
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


def tokenize_verdict_label(value: object) -> list[str]:
    """Split a verdict label into lowercase alphanumeric tokens."""
    text = normalize_verdict_token(value)
    if not text:
        return []
    return [token for token in re.split(r"[^a-z0-9]+", text) if token]


def classify_verdict_noise_bucket(
    value: object,
    *,
    known_family_tokens: set[str] | None = None,
    known_alias_tokens: set[str] | None = None,
) -> str:
    """Classify a raw vendor verdict label into a debt-analysis bucket."""
    text = normalize_verdict_token(value)
    if text in NON_DETECTION_TOKENS or not text:
        return "non_detection"

    tokens = set(tokenize_verdict_label(text))
    family_hits = tokens & (known_family_tokens or set())
    alias_hits = tokens & (known_alias_tokens or set())
    if family_hits or alias_hits:
        if OVERLAP_SIGNAL_RE.search(text):
            return "family_overlap"
        return "family_ready"
    if PROVENANCE_NOISE_RE.search(text):
        return "provenance_noise"
    if GENERIC_SIGNAL_RE.search(text):
        return "generic_signal"
    return "other_signal"
