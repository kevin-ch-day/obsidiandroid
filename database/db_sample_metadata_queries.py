"""Public query facade for Android malware sample metadata loaders."""

from __future__ import annotations

import pandas as pd
import warnings
from config import app_config

from utils import display_utils as du
from database.db_sample_metadata_contracts import (
    BANKING_TROJAN_FAMILIES,
    SUPPORTED_ANDROID_TYPE_SLUGS,
    convert_to_dataframe,
    get_supported_android_type_slugs,
)
from database.db_sample_metadata_fetchers import (
    fetch_available_android_type_slugs,
    fetch_all_android_malware,
    fetch_android_malware_with_min_family_samples,
    fetch_sample_metadata,
    fetch_samples_by_type,
    get_type_cohort_gate_stats,
)


_DB_TYPE_SLUG_CACHE: tuple[str, ...] | None = None


def _allowed_type_slugs() -> tuple[str, ...]:
    """Resolve allowed type slugs from DB taxonomy with static fallback.

    Validation modes:
        - ``static``: Use hardcoded contract list only.
        - ``hybrid``: Prefer DB list; fallback to static on DB errors.
        - ``strict``: Require DB list, propagate DB errors.
    """
    mode = str(getattr(app_config, "TYPE_SLUG_VALIDATION_MODE", "hybrid")).strip().lower()
    if mode == "static":
        return SUPPORTED_ANDROID_TYPE_SLUGS

    global _DB_TYPE_SLUG_CACHE  # pylint: disable=global-statement
    if _DB_TYPE_SLUG_CACHE is not None:
        return _DB_TYPE_SLUG_CACHE

    try:
        db_slugs = tuple(fetch_available_android_type_slugs())
    except Exception:  # pylint: disable=broad-except
        if mode == "strict":
            raise
        return SUPPORTED_ANDROID_TYPE_SLUGS

    if not db_slugs:
        if mode == "strict":
            raise ValueError("DB type taxonomy returned no type slugs in strict mode.")
        return SUPPORTED_ANDROID_TYPE_SLUGS

    _DB_TYPE_SLUG_CACHE = db_slugs
    return db_slugs


def load_banking_trojan_dataframe() -> pd.DataFrame:
    """Load banker-type Android samples (legacy compatibility wrapper)."""
    warnings.warn(
        "load_banking_trojan_dataframe() is deprecated; use "
        "load_samples_by_type(type_slug='banker', ...) instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return load_banker_dataframe()


def _validate_type_slug(type_slug: str | None) -> None:
    """Validate type slug against canonical supported Android malware types."""
    if type_slug is None:
        return
    allowed_type_slugs = _allowed_type_slugs()
    if type_slug not in allowed_type_slugs:
        allowed = ", ".join(allowed_type_slugs)
        raise ValueError(f"Unsupported type_slug '{type_slug}'. Expected one of: {allowed}")


def load_samples_by_type(
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
) -> pd.DataFrame:
    """Load Android APK samples for a canonical malware type.

    Args:
        type_slug: Canonical type slug (for example: ``banker``, ``rat``).
        min_samples_per_family: Optional minimum sample support per family.
        require_mapped_family: Require canonical family mapping.
        require_sha256: Require a valid 64-character SHA-256.
        allow_missing_package_name: If False, drops rows missing package name.
        exclude_unknown_type_slug: If True and ``type_slug`` is None, excludes
            taxonomy rows mapped to ``unknown``.
        limit: Optional result cap.
        effective_time_start_utc: Inclusive lower bound for effective first-seen.
        effective_time_end_utc: Exclusive upper bound for effective first-seen.
        require_effective_first_seen: Require effective first-seen timestamp.

    Returns:
        DataFrame in the pipeline metadata contract format.
    """
    _validate_type_slug(type_slug)
    query_type = type_slug or "all"
    label = f"Type:{query_type}"
    du.print_header(f"Loading Android Samples by Type: {query_type}")
    result = fetch_samples_by_type(
        type_slug=type_slug,
        min_samples_per_family=min_samples_per_family,
        require_mapped_family=require_mapped_family,
        require_sha256=require_sha256,
        allow_missing_package_name=allow_missing_package_name,
        exclude_unknown_type_slug=exclude_unknown_type_slug,
        limit=limit,
        effective_time_start_utc=effective_time_start_utc,
        effective_time_end_utc=effective_time_end_utc,
        require_effective_first_seen=require_effective_first_seen,
        exclude_family_ids=exclude_family_ids,
        exclude_family_canonical=exclude_family_canonical,
        as_dataframe=False,
    )
    return convert_to_dataframe(result, label)


def get_type_slug_alignment_report() -> dict[str, list[str]]:
    """Compare hardcoded supported type slugs against database taxonomy values."""
    configured = set(get_supported_android_type_slugs())
    observed = set(fetch_available_android_type_slugs())
    return {
        "configured_only": sorted(configured - observed),
        "db_only": sorted(observed - configured),
        "intersection": sorted(configured & observed),
    }


def load_banker_dataframe(**kwargs) -> pd.DataFrame:
    """Load banker samples using the canonical type-aware query path."""
    return load_samples_by_type(type_slug="banker", **kwargs)


def load_dropper_dataframe(**kwargs) -> pd.DataFrame:
    """Load dropper samples using the canonical type-aware query path."""
    return load_samples_by_type(type_slug="dropper", **kwargs)


def load_adware_dataframe(**kwargs) -> pd.DataFrame:
    """Load adware samples using the canonical type-aware query path."""
    return load_samples_by_type(type_slug="adware", **kwargs)


def load_stealer_dataframe(**kwargs) -> pd.DataFrame:
    """Load stealer samples using the canonical type-aware query path."""
    return load_samples_by_type(type_slug="stealer", **kwargs)


def load_sms_trojan_dataframe(**kwargs) -> pd.DataFrame:
    """Load SMS-trojan samples using the canonical type-aware query path."""
    return load_samples_by_type(type_slug="sms-trojan", **kwargs)


def load_rat_dataframe(**kwargs) -> pd.DataFrame:
    """Load RAT samples using the canonical type-aware query path."""
    return load_samples_by_type(type_slug="rat", **kwargs)


def load_spyware_dataframe(**kwargs) -> pd.DataFrame:
    """Load spyware samples using the canonical type-aware query path."""
    return load_samples_by_type(type_slug="spyware", **kwargs)


def load_unknown_type_dataframe(**kwargs) -> pd.DataFrame:
    """Load unknown-type samples using the canonical type-aware query path."""
    return load_samples_by_type(type_slug="unknown", **kwargs)


def load_all_android_malware_dataframe() -> pd.DataFrame:
    """Load all Android malware samples as a DataFrame (deprecated wrapper)."""
    warnings.warn(
        "load_all_android_malware_dataframe() is deprecated; use "
        "load_samples_by_type(type_slug=None, ...) instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    du.print_header("Loading All Android Malware Samples")
    result = fetch_all_android_malware(as_dataframe=False)
    return convert_to_dataframe(result, "AllAndroidMalware")


def load_android_malware_with_min_family_samples(min_count: int = 3) -> pd.DataFrame:
    """Load Android malware samples with minimum per-family support (deprecated)."""
    warnings.warn(
        "load_android_malware_with_min_family_samples() is deprecated; use "
        "load_samples_by_type(type_slug='<canonical-slug>', min_samples_per_family=...) "
        "for type-scoped cohorts.",
        DeprecationWarning,
        stacklevel=2,
    )
    du.print_header(f"Loading Android Malware with ≥{min_count} Samples per Family")
    result = fetch_android_malware_with_min_family_samples(
        min_count=min_count,
        as_dataframe=False,
    )
    return convert_to_dataframe(result, "MinFamilySamples")


def load_sample_metadata_dataframe(sample_id) -> pd.DataFrame:
    """Load metadata for an individual sample identifier."""
    du.print_header(f"Loading Metadata for Sample ID: {sample_id}")
    result = fetch_sample_metadata(sample_id=sample_id, as_dataframe=False)
    return convert_to_dataframe(result, f"SampleMetadata:{sample_id}")
