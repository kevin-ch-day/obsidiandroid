"""Profile-aware dataset filtering and cohort partition diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config


def split_benign_malicious(samples_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split samples using VT-consensus signal with category fallback.

    Canonical rule:
    - Malicious: ``vt_malicious_count + vt_suspicious_count > 0``
    - Benign: ``vt_malicious_count == 0`` and ``vt_suspicious_count == 0`` and
      one of:
      - ``vt_undetected_count > 0``
      - ``vt_reputation >= 0``

    Args:
        samples_df: Input samples dataframe.

    Returns:
        Tuple of (benign_df, malicious_df).
    """
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    def _num(name: str) -> pd.Series:
        if name not in samples_df.columns:
            return pd.Series(0, index=samples_df.index, dtype="float64")
        return pd.to_numeric(samples_df[name], errors="coerce").fillna(0.0)

    vt_malicious = _num("vt_malicious_count")
    vt_suspicious = _num("vt_suspicious_count")
    vt_undetected = _num("vt_undetected_count")
    vt_reputation = _num("vt_reputation")
    vt_positive = vt_malicious + vt_suspicious

    benign_mask = (vt_positive == 0) & ((vt_undetected > 0) | (vt_reputation >= 0))
    malicious_mask = vt_positive > 0

    unresolved = ~(benign_mask | malicious_mask)
    if unresolved.any() and "category_primary" in samples_df.columns:
        primary = (
            samples_df["category_primary"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
        )
        fallback_benign = primary.str.contains("benign|clean|harmless|safe", regex=True)
        fallback_malicious = primary.str.contains(
            "malicious|trojan|threat|risk|suspicious|adware|ransomware|spyware",
            regex=True,
        )
        benign_mask = benign_mask | (unresolved & fallback_benign)
        malicious_mask = malicious_mask | (unresolved & fallback_malicious)

    benign_df = samples_df[benign_mask].copy()
    malicious_df = samples_df[malicious_mask].copy()
    return benign_df, malicious_df


def summarize_dataset_partitions(
    source_df: pd.DataFrame,
    output_df: pd.DataFrame,
    benign_df: pd.DataFrame,
    malicious_df: pd.DataFrame,
    mode: str,
    benign_ratio_target: float | None = None,
) -> dict[str, Any]:
    """Build audit summary for profile dataset filtering."""
    pre_total = int(len(source_df))
    post_total = int(len(output_df))
    benign_count = int(len(benign_df))
    malicious_count = int(len(malicious_df))
    unresolved_count = max(pre_total - benign_count - malicious_count, 0)
    benign_ratio = float(benign_count / pre_total) if pre_total else 0.0
    malicious_ratio = float(malicious_count / pre_total) if pre_total else 0.0
    return {
        "mode": mode,
        "source_total": pre_total,
        "post_filter_total": post_total,
        "benign_candidates": benign_count,
        "malicious_candidates": malicious_count,
        "unresolved_candidates": unresolved_count,
        "benign_candidate_ratio": round(benign_ratio, 6),
        "malicious_candidate_ratio": round(malicious_ratio, 6),
        "benign_ratio_target": benign_ratio_target,
    }


def export_cohort_filter_summary(
    summary: dict[str, Any],
    run_id: str,
    profile_id: str,
    output_path: Path,
) -> str:
    """Write dataset-filter summary for auditability."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    row = dict(summary)
    row["run_id"] = run_id
    row["profile_id"] = profile_id
    pd.DataFrame([row]).to_csv(output_path, index=False)
    return str(output_path)


def apply_dataset_filters(samples_df: pd.DataFrame, profile: dict) -> pd.DataFrame:
    """Apply profile dataset filters to cohort selection.

    Args:
        samples_df: Source sample dataframe.
        profile: Profile dictionary containing ``dataset_filters`` settings.

    Returns:
        Filtered dataframe with ``cohort_filter_summary`` attached in attrs.
    """
    dataset_filters = profile.get("dataset_filters", {}) if isinstance(profile, dict) else {}
    mode = str(dataset_filters.get("mode", "none") or "none").strip().lower()
    if mode in {"none", ""}:
        samples_df.attrs["cohort_filter_summary"] = summarize_dataset_partitions(
            source_df=samples_df,
            output_df=samples_df,
            benign_df=pd.DataFrame(),
            malicious_df=pd.DataFrame(),
            mode=mode,
        )
        return samples_df

    benign_df, malicious_df = split_benign_malicious(samples_df)
    min_partition_size = int(dataset_filters.get("min_partition_size", 1))

    random_state = int(getattr(app_config, "RANDOM_STATE", 42))
    if mode == "malicious_only":
        out_df = malicious_df.copy()
        out_df.attrs["cohort_filter_summary"] = summarize_dataset_partitions(
            source_df=samples_df,
            output_df=out_df,
            benign_df=benign_df,
            malicious_df=malicious_df,
            mode=mode,
        )
        return out_df

    if mode == "mixed_balanced":
        if benign_df.empty or malicious_df.empty:
            raise ValueError("[PROFILE] mixed_balanced requires non-empty benign and malicious partitions.")
        if min(len(benign_df), len(malicious_df)) < min_partition_size:
            raise ValueError(
                f"[PROFILE] mixed_balanced insufficient partition size "
                f"(benign={len(benign_df)}, malicious={len(malicious_df)}, min={min_partition_size})."
            )
        n = min(len(benign_df), len(malicious_df))
        mixed = pd.concat(
            [
                benign_df.sample(n=n, random_state=random_state),
                malicious_df.sample(n=n, random_state=random_state),
            ],
            axis=0,
        )
        out_df = mixed.sample(frac=1.0, random_state=random_state).reset_index(drop=True)
        out_df.attrs["cohort_filter_summary"] = summarize_dataset_partitions(
            source_df=samples_df,
            output_df=out_df,
            benign_df=benign_df,
            malicious_df=malicious_df,
            mode=mode,
            benign_ratio_target=float(dataset_filters.get("benign_ratio", 0.5)),
        )
        return out_df

    if mode == "benign_heavy":
        if benign_df.empty or malicious_df.empty:
            raise ValueError("[PROFILE] benign_heavy requires non-empty benign and malicious partitions.")
        if len(benign_df) < min_partition_size:
            raise ValueError(
                f"[PROFILE] benign_heavy benign partition below minimum "
                f"(benign={len(benign_df)}, min={min_partition_size})."
            )
        benign_ratio = float(dataset_filters.get("benign_ratio_min", 0.7))
        benign_ratio = min(max(benign_ratio, 0.5), 0.95)
        max_malicious = int(len(benign_df) * ((1.0 - benign_ratio) / benign_ratio))
        max_malicious = max(1, max_malicious)
        mal_subset = malicious_df.sample(
            n=min(len(malicious_df), max_malicious),
            random_state=random_state,
        )
        merged = pd.concat([benign_df, mal_subset], axis=0)
        out_df = merged.sample(frac=1.0, random_state=random_state).reset_index(drop=True)
        actual_ratio = float(len(benign_df) / len(out_df)) if len(out_df) else 0.0
        if actual_ratio < benign_ratio:
            raise ValueError(
                f"[PROFILE] benign_heavy ratio not satisfied "
                f"(actual={actual_ratio:.4f}, required={benign_ratio:.4f})."
            )
        out_df.attrs["cohort_filter_summary"] = summarize_dataset_partitions(
            source_df=samples_df,
            output_df=out_df,
            benign_df=benign_df,
            malicious_df=malicious_df,
            mode=mode,
            benign_ratio_target=benign_ratio,
        )
        return out_df

    samples_df.attrs["cohort_filter_summary"] = summarize_dataset_partitions(
        source_df=samples_df,
        output_df=samples_df,
        benign_df=benign_df,
        malicious_df=malicious_df,
        mode=mode,
    )
    return samples_df

