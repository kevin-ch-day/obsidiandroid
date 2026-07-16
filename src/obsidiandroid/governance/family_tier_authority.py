"""Curated family-tier authority for Android malware research profiles."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from obsidiandroid.common.repo_paths import repo_root
from obsidiandroid.common.family_label_semantics import (
    is_family_placeholder_token as _is_family_placeholder_token,
    normalize_family_identity_token,
)
from obsidiandroid.labeling.malware_family_constants import GENERIC_TOKENS

AUTHORITY_ARTIFACT_PATH = Path("config") / "taxonomy" / "android_family_tier_authority.yaml"
MAJOR_FAMILY_AUTHORITY_HANDLE = "android_family_tier_authority.major_families"
GENERIC_COARSE_TOKEN_POLICY_HANDLE = "android_family_tier_authority.generic_coarse_tokens"

WEAK_LABEL_KINDS: frozenset[str] = frozenset(
    {"filename", "hash_like", "opaque_string", "unclassified"}
)
EMPTY_TOKENS: frozenset[str] = frozenset({"", "unknown", "none", "null", "nan", "n/a"})
GENERIC_PRIMARY_TOKENS: frozenset[str] = EMPTY_TOKENS | {"malware"}
CANONICAL_TYPE_TOKENS: frozenset[str] = frozenset(
    {
        "adware",
        "backdoor",
        "banker",
        "cryptojacking",
        "downloader",
        "dropper",
        "miner",
        "ransomware",
        "rat",
        "riskware",
        "rootkit",
        "sms-trojan",
        "spyware",
        "stalkerware",
        "stealer",
        "subscription-fraud",
        "trojan",
    }
)

def _stable_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _artifact_path() -> Path:
    return repo_root() / AUTHORITY_ARTIFACT_PATH


def _normalized_token_list(values: Any) -> tuple[str, ...]:
    seen: set[str] = set()
    tokens: list[str] = []
    for value in values if isinstance(values, list) else []:
        token = str(value or "").strip().lower()
        if token and token not in seen:
            seen.add(token)
            tokens.append(token)
    return tuple(tokens)


def clean_tier_token(value: Any, *, generic_tokens: set[str] | None = None) -> str:
    """Normalize a token for family-tier classification."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    token = str(value).strip().lower()
    blocked = generic_tokens if generic_tokens is not None else EMPTY_TOKENS
    if token in blocked:
        return ""
    return token


def _series_from(
    df: pd.DataFrame,
    column: str,
    *,
    generic_tokens: set[str] | None = None,
) -> pd.Series:
    if column not in df.columns:
        return pd.Series([""] * len(df), index=df.index, dtype="object")
    return df[column].map(lambda value: clean_tier_token(value, generic_tokens=generic_tokens))


def _numeric_family_id_series(df: pd.DataFrame) -> pd.Series:
    if "family_id" not in df.columns:
        return pd.Series([pd.NA] * len(df), index=df.index, dtype="Float64")
    return pd.to_numeric(df["family_id"], errors="coerce")


@lru_cache(maxsize=1)
def load_family_tier_authority_artifact() -> dict[str, Any]:
    """Load the curated Android family-tier authority artifact."""
    path = _artifact_path()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Family tier authority artifact must be a mapping: {path}")
    payload["major_families"] = list(_normalized_token_list(payload.get("major_families", [])))
    payload["generic_coarse_tokens"] = list(
        _normalized_token_list(payload.get("generic_coarse_tokens", []))
    )
    payload["type_targets"] = list(_normalized_token_list(payload.get("type_targets", [])))
    return payload


def major_family_authority_payload() -> dict[str, Any]:
    """Return machine-readable curated major-family authority metadata."""
    artifact = load_family_tier_authority_artifact()
    families = list(artifact.get("major_families", []))
    payload = {
        "authority_id": str(artifact.get("authority_id", "") or "").strip(),
        "version": str(artifact.get("version", "") or "").strip(),
        "source": str(artifact.get("source", "") or "").strip(),
        "seed_source": str(artifact.get("seed_source", "") or "").strip(),
        "review_status": str(artifact.get("review_status", "") or "").strip(),
        "review_notes": list(artifact.get("review_notes", []) or []),
        "artifact_path": str(AUTHORITY_ARTIFACT_PATH.as_posix()),
        "handle": MAJOR_FAMILY_AUTHORITY_HANDLE,
        "family_names": families,
        "family_count": len(families),
    }
    payload["hash"] = _stable_hash(payload)
    return payload


def generic_coarse_token_policy_payload() -> dict[str, Any]:
    """Return generic/coarse token policy metadata used for tier reporting."""
    artifact = load_family_tier_authority_artifact()
    tokens = sorted(
        {
            *(str(token).strip().lower() for token in GENERIC_TOKENS),
            *(
                str(token).strip().lower()
                for token in artifact.get("generic_coarse_tokens", [])
            ),
        }
    )
    payload = {
        "authority_id": str(artifact.get("authority_id", "") or "").strip(),
        "version": str(artifact.get("version", "") or "").strip(),
        "source": str(artifact.get("source", "") or "").strip(),
        "artifact_path": str(AUTHORITY_ARTIFACT_PATH.as_posix()),
        "handle": GENERIC_COARSE_TOKEN_POLICY_HANDLE,
        "token_count": len(tokens),
        "tokens": tokens,
        "type_targets": list(artifact.get("type_targets", []) or []),
        "weak_label_kinds": sorted(WEAK_LABEL_KINDS),
    }
    payload["hash"] = _stable_hash(payload)
    return payload


def major_family_name_set() -> set[str]:
    """Return normalized major-family names."""
    return set(major_family_name_list())


def major_family_name_list() -> tuple[str, ...]:
    """Return normalized major-family names in artifact order."""
    artifact = load_family_tier_authority_artifact()
    return tuple(str(value).strip().lower() for value in artifact.get("major_families", []))


def generic_coarse_token_set() -> set[str]:
    """Return normalized generic/coarse-label tokens."""
    payload = generic_coarse_token_policy_payload()
    return set(str(value).strip().lower() for value in payload.get("tokens", []))


def build_family_tier_masks(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Return row-level family-tier masks aligned with the governed taxonomy contract."""
    family_canonical = _series_from(df, "family_canonical")
    family_ids = _numeric_family_id_series(df)
    type_slug = _series_from(df, "type_slug")
    category_primary = _series_from(
        df,
        "category_primary",
        generic_tokens=set(GENERIC_PRIMARY_TOKENS),
    )
    category_subtype = _series_from(df, "category_subtype")
    sample_label_kind = _series_from(df, "sample_label_kind")

    generic_tokens = generic_coarse_token_set()
    major_families = major_family_name_set()

    family_placeholder = family_canonical.map(_is_family_placeholder_token)
    mapped_family = (
        family_canonical.ne("")
        & ~family_placeholder
        & family_ids.notna()
        & (family_ids >= 0)
    )
    family_generic_token = family_canonical.isin(generic_tokens)
    primary_generic_token = category_primary.isin(generic_tokens | set(CANONICAL_TYPE_TOKENS))
    subtype_generic_token = category_subtype.isin(generic_tokens | set(CANONICAL_TYPE_TOKENS))
    weak_label = sample_label_kind.isin(set(WEAK_LABEL_KINDS))
    # A non-empty historical taxonomy label is useful audit context, but it is
    # not automatically a valid supervised type target. Keep the target mask
    # aligned with the live semantic canonical vocabulary.
    type_eligible = type_slug.isin(CANONICAL_TYPE_TOKENS)

    major_mask = mapped_family & family_canonical.isin(major_families)
    minor_mask = mapped_family & ~major_mask
    generic_coarse_mask = (
        ~mapped_family
        & (family_generic_token | primary_generic_token | subtype_generic_token | weak_label)
    )
    unresolved_mask = ~(major_mask | minor_mask | generic_coarse_mask)

    return {
        "mapped_family": mapped_family,
        "major_family": major_mask,
        "minor_family": minor_mask,
        "generic_coarse": generic_coarse_mask,
        "unresolved": unresolved_mask,
        "type_target_eligible": type_eligible,
        "family_target_eligible": major_mask | minor_mask,
    }


__all__ = [
    "AUTHORITY_ARTIFACT_PATH",
    "CANONICAL_TYPE_TOKENS",
    "EMPTY_TOKENS",
    "GENERIC_COARSE_TOKEN_POLICY_HANDLE",
    "GENERIC_PRIMARY_TOKENS",
    "MAJOR_FAMILY_AUTHORITY_HANDLE",
    "WEAK_LABEL_KINDS",
    "build_family_tier_masks",
    "clean_tier_token",
    "generic_coarse_token_policy_payload",
    "generic_coarse_token_set",
    "load_family_tier_authority_artifact",
    "major_family_authority_payload",
    "major_family_name_list",
    "major_family_name_set",
    "normalize_family_identity_token",
]
