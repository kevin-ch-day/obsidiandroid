"""Helpers for preparing cohort samples and metadata features.

Canonical implementation (**Pass 70**): ``obsidiandroid.pipeline.sample_preparation``;
The supported import path is ``obsidiandroid.pipeline.sample_preparation``.

This module extracts preprocessing logic from ``main.py`` to keep pipeline
orchestration compact and easier to test in isolation.

``build_metadata_feature_frame`` and ``extract_vt_tag_count`` are the canonical
metadata-feature builders.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.common.cv_fold_config import safe_int_config_value

_TAG_SPLIT_PATTERN = re.compile(r"[;,|]")


def extract_vt_tag_count(value: object) -> int:
    """Count VT tags from list/JSON/string representations.

    Args:
        value: Raw VT tags value from source metadata.

    Returns:
        Number of non-empty tags.
    """
    if value is None:
        return 0

    if isinstance(value, list):
        return sum(1 for tag in value if str(tag).strip())

    text = str(value).strip()
    if not text:
        return 0

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return sum(1 for tag in parsed if str(tag).strip())
        except Exception:
            pass

    parts = [part for part in _TAG_SPLIT_PATTERN.split(text) if part.strip()]
    return len(parts)


def build_metadata_feature_frame(samples_df: pd.DataFrame) -> pd.DataFrame:
    """Construct metadata features from sample and VT summary columns.

    Args:
        samples_df: Input sample metadata dataframe.

    Returns:
        Dataframe keyed by ``sample_id`` with metadata feature columns.
    """
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return pd.DataFrame()
    if "sample_id" not in samples_df.columns:
        return pd.DataFrame()

    features = pd.DataFrame({"sample_id": samples_df["sample_id"]})

    numeric_cols = [
        "permissions",
        "target_min_version",
        "target_sdk_version",
        "vt_malicious_count",
        "vt_suspicious_count",
        "vt_undetected_count",
        "vt_harmless_count",
        "vt_timeout_count",
        "vt_confirmed_timeout_count",
        "vt_failure_count",
        "vt_type_unsupported_count",
        "vt_reputation",
        "vt_times_submitted",
        "vt_unique_sources",
        "vt_total_votes_harmless",
        "vt_total_votes_malicious",
    ]
    for column_name in numeric_cols:
        if column_name in samples_df.columns:
            features[f"meta__{column_name}"] = pd.to_numeric(
                samples_df[column_name], errors="coerce"
            ).fillna(0.0)

    for column_name in ["android_package_name", "package_name", "vt_suggested_threat_label"]:
        if column_name in samples_df.columns:
            features[f"meta__has_{column_name}"] = (
                samples_df[column_name].fillna("").astype(str).str.strip() != ""
            ).astype(int)

    if "vt_tags" in samples_df.columns:
        features["meta__vt_tag_count"] = samples_df["vt_tags"].map(extract_vt_tag_count).astype(int)

    count_columns = [
        column_name
        for column_name in [
            "meta__vt_malicious_count",
            "meta__vt_suspicious_count",
            "meta__vt_undetected_count",
            "meta__vt_harmless_count",
            "meta__vt_timeout_count",
            "meta__vt_confirmed_timeout_count",
            "meta__vt_failure_count",
            "meta__vt_type_unsupported_count",
        ]
        if column_name in features.columns
    ]
    if count_columns:
        total = features[count_columns].sum(axis=1)
        positive = pd.Series(0.0, index=features.index)
        if "meta__vt_malicious_count" in features.columns:
            positive = positive + features["meta__vt_malicious_count"]
        if "meta__vt_suspicious_count" in features.columns:
            positive = positive + features["meta__vt_suspicious_count"]
        features["meta__vt_positive_ratio"] = (positive / total.where(total > 0, 1)).fillna(0.0)

    return features.drop_duplicates("sample_id")


def split_benign_malicious(samples_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split samples into benign and malicious partitions.

    Args:
        samples_df: Cohort dataframe.

    Returns:
        A tuple of ``(benign_df, malicious_df)``.
    """
    if "category_primary" not in samples_df.columns:
        return pd.DataFrame(), pd.DataFrame()

    primary = samples_df["category_primary"].fillna("").astype(str).str.strip().str.lower()
    benign_mask = primary.str.contains("benign|clean|harmless|safe", regex=True)
    malicious_mask = primary.str.contains("malicious|trojan|threat|risk|suspicious", regex=True)
    benign_df = samples_df[benign_mask].copy()
    malicious_df = samples_df[malicious_mask | (~benign_mask)].copy()
    return benign_df, malicious_df


def apply_dataset_filters(samples_df: pd.DataFrame, profile: dict[str, Any]) -> pd.DataFrame:
    """Apply profile-driven sampling filters to selected cohort rows.

    Args:
        samples_df: Loaded cohort dataframe.
        profile: Loaded profile dictionary.

    Returns:
        Filtered dataframe according to configured dataset mode.
    """
    dataset_filters = profile.get("dataset_filters", {}) if isinstance(profile, dict) else {}
    mode = str(dataset_filters.get("mode", "none") or "none").strip().lower()
    if mode in {"none", ""}:
        return samples_df

    benign_df, malicious_df = split_benign_malicious(samples_df)
    if benign_df.empty and malicious_df.empty:
        return samples_df

    random_state = safe_int_config_value(getattr(app_config, "RANDOM_STATE", 42), default=42)
    if mode == "malicious_only":
        return malicious_df if not malicious_df.empty else samples_df

    if mode == "mixed_balanced":
        if benign_df.empty or malicious_df.empty:
            return samples_df
        sample_count = min(len(benign_df), len(malicious_df))
        mixed = pd.concat(
            [
                benign_df.sample(n=sample_count, random_state=random_state),
                malicious_df.sample(n=sample_count, random_state=random_state),
            ],
            axis=0,
        )
        return mixed.sample(frac=1.0, random_state=random_state).reset_index(drop=True)

    if mode == "benign_heavy":
        if benign_df.empty or malicious_df.empty:
            return samples_df
        benign_ratio = float(dataset_filters.get("benign_ratio_min", 0.7))
        benign_ratio = min(max(benign_ratio, 0.5), 0.95)
        max_malicious = max(1, int(len(benign_df) * ((1.0 - benign_ratio) / benign_ratio)))
        malicious_subset = malicious_df.sample(
            n=min(len(malicious_df), max_malicious),
            random_state=random_state,
        )
        merged = pd.concat([benign_df, malicious_subset], axis=0)
        return merged.sample(frac=1.0, random_state=random_state).reset_index(drop=True)

    return samples_df
