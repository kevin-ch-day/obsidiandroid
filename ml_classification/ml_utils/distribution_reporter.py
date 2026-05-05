# Filename: distribution_reporter.py
# Purpose  : Utility functions for summarizing label distribution across malware families.
#            Supports class imbalance detection and distribution evaluation.

from collections import Counter
from typing import Any, List, Union
import pandas as pd

# Threshold constants
LOW_SUPPORT_THRESHOLD = 3
VERY_LOW_SUPPORT_THRESHOLD = 1

# === Helper: Validate if the label container is empty ===
def _is_empty_label_input(labels) -> bool:
    if labels is None:
        return True
    if isinstance(labels, list):
        return len(labels) == 0
    if hasattr(labels, "empty"):
        return labels.empty
    return False

# === Print label frequency and flag low-support classes (silent by default) ===
def print_family_distribution(
    labels: Union[List[str], List[int]],
    label_type: str = "",
    warn: bool = False,
    highlight: bool = False,
    *,
    verbose: bool = False,
):
    if not verbose or _is_empty_label_input(labels):
        return

    from obsidiandroid.cli.ui import display as du

    counts = Counter(labels)
    low_support = [str(fam) for fam, cnt in counts.items() if cnt <= LOW_SUPPORT_THRESHOLD]
    very_low_support = [str(fam) for fam, cnt in counts.items() if cnt <= VERY_LOW_SUPPORT_THRESHOLD]

    du.print_info(f"[DISTRIBUTION] {len(counts)} unique families detected.")
    du.print_info(f"[DISTRIBUTION] {len(low_support)} families flagged as LOW support (<= {LOW_SUPPORT_THRESHOLD} samples).")

    if warn and very_low_support:
        du.print_warning(f"[DISTRIBUTION] {len(very_low_support)} families have critically low support (<= {VERY_LOW_SUPPORT_THRESHOLD} sample).")

    total = sum(counts.values())
    for fam, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        percent = (count / total) * 100
        value_str = f"{count} sample{'s' if count != 1 else ''} ({percent:5.1f}%)"
        if highlight:
            if count <= VERY_LOW_SUPPORT_THRESHOLD:
                value_str += " !! CRITICAL"
            elif count <= LOW_SUPPORT_THRESHOLD:
                value_str += " * LOW"
        du.print_stat(f"{label_type} {fam:<15}".strip(), value_str)

    if warn and low_support:
        du.print_note("Consider collecting additional samples for: " + ", ".join(low_support))

# === Post-split evaluation label distribution ===
def print_split_distributions(y_test, *, verbose: bool = False):
    if verbose:
        from obsidiandroid.cli.ui import display as du
        du.print_subheader("[POST-SPLIT] Evaluation Label Distribution")
        print_family_distribution(
            y_test,
            label_type="Eval",
            warn=True,
            highlight=True,
            verbose=True,
        )

# === Return label count summary ===
def summarize_label_distribution(labels: Union[List[str], List[int]]) -> dict:
    if _is_empty_label_input(labels):
        return {}
    return dict(Counter(labels))

# === Identify low-support classes ===
def detect_low_support_families(labels: Union[List[str], List[int]], threshold: int = LOW_SUPPORT_THRESHOLD) -> List[str]:
    if _is_empty_label_input(labels):
        return []
    return [str(fam) for fam, cnt in Counter(labels).items() if cnt <= threshold]

# === Build DataFrame of label counts ===
def build_distribution_df(labels: Union[List[str], List[int]]) -> pd.DataFrame:
    if _is_empty_label_input(labels):
        return pd.DataFrame(columns=["family", "count", "percent", "support_tier"])

    counts = Counter(labels)
    total = sum(counts.values())

    rows = []
    for fam, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        percent = (count / total) * 100
        tier = (
            "critical" if count <= VERY_LOW_SUPPORT_THRESHOLD
            else "low" if count <= LOW_SUPPORT_THRESHOLD
            else "ok"
        )
        rows.append({
            "family": str(fam),
            "count": count,
            "percent": round(percent, 2),
            "support_tier": tier,
        })

    return pd.DataFrame(rows)

# === Filter families below minimum support ===
def apply_min_family_support(
    features_df: pd.DataFrame,
    labels_df: pd.Series,
    *,
    min_support: int,
    group_label: str | None = None,
) -> tuple[pd.DataFrame, pd.Series, int, int, list[dict[str, Any]]]:
    """Remove or group families with sample count below ``min_support``.

    Parameters
    ----------
    features_df : pd.DataFrame
        Feature matrix aligned with ``labels``.
    labels : pd.Series
        Series of family labels indexed by sample_id.
    min_support : int
        Minimum samples required for a family to remain independent.
    group_label : str | None, optional
        If provided, low-support families are relabeled to this value rather
        than being removed entirely.

    Returns
    -------
    tuple
        (filtered_features_df, filtered_labels, affected_samples, n_low_families,
        low_family_rows) where ``low_family_rows`` is
        ``[{"family": ..., "aligned_support": int}, ...]`` sorted by family name.
    """
    if _is_empty_label_input(labels_df):
        return features_df, labels_df, 0, 0, []

    counts = Counter(labels_df)
    low_fams = [fam for fam, cnt in counts.items() if cnt < min_support]
    if not low_fams:
        return features_df, labels_df, 0, 0, []

    affected_samples = int(labels_df.isin(low_fams).sum())
    low_family_rows = [
        {"family": str(fam), "aligned_support": int(counts[fam])}
        for fam in sorted(low_fams, key=lambda x: str(x))
    ]

    if group_label is None:
        mask = ~labels_df.isin(low_fams)
        return (
            features_df.loc[mask],
            labels_df.loc[mask],
            affected_samples,
            len(low_fams),
            low_family_rows,
        )

    new_labels = labels_df.copy()
    new_labels.loc[new_labels.isin(low_fams)] = group_label
    return features_df, new_labels, affected_samples, len(low_fams), low_family_rows
