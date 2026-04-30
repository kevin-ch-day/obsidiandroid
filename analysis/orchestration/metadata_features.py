"""Metadata feature extraction helpers for orchestrated pipeline runs."""

from __future__ import annotations

import json
import re

import pandas as pd


def extract_vt_tag_count(value: object) -> int:
    """Count VT tags from list/JSON/string representations.

    Args:
        value: VT tag field value in list, JSON, or delimited string form.

    Returns:
        Number of parsed non-empty tags.
    """
    if value is None:
        return 0

    if isinstance(value, list):
        return len([x for x in value if str(x).strip()])

    text = str(value).strip()
    if not text:
        return 0

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return len([x for x in parsed if str(x).strip()])
        except Exception:
            pass

    parts = [p.strip() for p in re.split(r"[;,|]", text) if p.strip()]
    return len(parts)


def build_metadata_feature_frame(samples_df: pd.DataFrame) -> pd.DataFrame:
    """Construct structured metadata features from sample/VT summary columns.

    Args:
        samples_df: Sample-level dataframe containing VT and metadata columns.

    Returns:
        Dataframe keyed by ``sample_id`` with engineered metadata features.
    """
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return pd.DataFrame()
    if "sample_id" not in samples_df.columns:
        return pd.DataFrame()

    df = samples_df.copy()
    features = pd.DataFrame({"sample_id": df["sample_id"]})

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
    for col in numeric_cols:
        if col in df.columns:
            features[f"meta__{col}"] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    for col in ["android_package_name", "package_name", "vt_suggested_threat_label"]:
        if col in df.columns:
            features[f"meta__has_{col}"] = (
                df[col].fillna("").astype(str).str.strip() != ""
            ).astype(int)

    if "vt_tags" in df.columns:
        features["meta__vt_tag_count"] = df["vt_tags"].map(extract_vt_tag_count).astype(int)

    counts_cols = [
        c
        for c in [
            "meta__vt_malicious_count",
            "meta__vt_suspicious_count",
            "meta__vt_undetected_count",
            "meta__vt_harmless_count",
            "meta__vt_timeout_count",
            "meta__vt_confirmed_timeout_count",
            "meta__vt_failure_count",
            "meta__vt_type_unsupported_count",
        ]
        if c in features.columns
    ]
    if counts_cols:
        total = features[counts_cols].sum(axis=1)
        positive = 0.0
        if "meta__vt_malicious_count" in features.columns:
            positive += features["meta__vt_malicious_count"]
        if "meta__vt_suspicious_count" in features.columns:
            positive += features["meta__vt_suspicious_count"]
        features["meta__vt_positive_ratio"] = (positive / total.where(total > 0, 1)).fillna(0.0)

    return features.drop_duplicates("sample_id")

