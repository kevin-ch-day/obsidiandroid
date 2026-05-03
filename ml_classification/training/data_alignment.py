# Filename: data_alignment.py
# Purpose  : Align AV-derived feature vectors with ground truth family labels
#            Normalize inconsistencies, drop unsupported families, and prepare training data

from typing import Any

import pandas as pd

from ml_classification.common.malware_family_constants import canonicalize_family_label
from utils import display_utils as du


class DataAlignmentError(ValueError):
    """Base exception raised when feature/label alignment cannot be completed."""


class EmptyAlignmentInputError(DataAlignmentError):
    """Raised when one or more alignment inputs are empty."""


class MissingSampleIdColumnError(DataAlignmentError):
    """Raised when sample metadata does not expose ``sample_id``."""


class MissingLabelColumnError(DataAlignmentError):
    """Raised when sample metadata has no usable family label column."""


class SampleIdMismatchError(DataAlignmentError):
    """Raised when feature sample IDs are not present in the label set."""

    def __init__(self, missing_ids: list[str]) -> None:
        self.missing_ids = list(missing_ids)
        preview = ", ".join(self.missing_ids[:5])
        suffix = "..." if len(self.missing_ids) > 5 else ""
        super().__init__(
            "Feature/label sample IDs do not align. "
            f"missing_ids={len(self.missing_ids)} [{preview}{suffix}]"
        )


class InsufficientLabelClassesError(DataAlignmentError):
    """Raised when alignment leaves fewer than two unique classes."""


def normalize_labels(labels: pd.Series, normalization_map: dict) -> pd.Series:
    """
    Normalize family labels using a known variant map (e.g., "Flubot" -> "FluBot").
    """
    normalized = labels.astype(str).str.strip().replace(normalization_map).fillna("unknown")
    return normalized.apply(canonicalize_family_label)


def normalize_alignment_id(value: Any) -> str:
    """Convert sample IDs to a stable comparable string form."""
    try:
        numeric = float(value)
        integer = int(numeric)
        if numeric == integer:
            return str(integer)
    except (ValueError, TypeError):
        pass
    return str(value)


def extract_aligned_labels(
    features_df: pd.DataFrame,
    samples_df: pd.DataFrame,
    normalization_map: dict = None,
    drop_low_support: bool = True,
    min_samples_per_family: int = 3,
    verbose: bool = True,
    forced_label_column: str | None = None,
) -> tuple[pd.DataFrame, pd.Series]:
    """Align features with labels from sample metadata.

    Args:
        features_df: Feature matrix indexed by sample id or with sample_id column upstream.
        samples_df: Cohort dataframe with ``sample_id`` plus label columns.
        forced_label_column: When set, use this column as the supervisory label instead of the
            default ``family_id`` / ``family_canonical`` / ``family_name`` priority chain.

    Returns:
        Tuple of ``(filtered_feature_df, label_series)``.
    """
    du.print_section("[ALIGNMENT] Aligning Features with Labels")

    if features_df.empty or samples_df.empty:
        du.print_error("Input feature or sample metadata is empty.")
        raise EmptyAlignmentInputError("Input feature or sample metadata is empty.")

    if "sample_id" not in samples_df.columns:
        du.print_error("Missing required column in sample metadata: sample_id")
        raise MissingSampleIdColumnError(
            "Missing required column in sample metadata: sample_id"
        )

    forced = str(forced_label_column or "").strip() or None
    if forced:
        if forced not in samples_df.columns:
            message = f"Forced label column `{forced}` not found in sample metadata."
            du.print_error(message)
            raise MissingLabelColumnError(message)
        label_col = forced
    else:
        label_candidates = ["family_id", "family_canonical", "family_name"]
        label_col = next((column for column in label_candidates if column in samples_df.columns), None)
        if label_col is None:
            message = (
                "Missing label column in sample metadata. "
                f"Tried: {label_candidates}"
            )
            du.print_error(message)
            raise MissingLabelColumnError(message)

    if (
        not forced
        and label_col == "family_name"
        and any(column in samples_df.columns for column in ("family_id", "family_canonical"))
    ):
        du.print_warning(
            "[ALIGNMENT] Falling back to legacy family_name label source despite canonical fields."
        )

    features = features_df.copy()
    samples = samples_df.copy()
    features.index = [normalize_alignment_id(value) for value in features.index]
    samples = samples.set_index("sample_id")
    samples.index = [normalize_alignment_id(value) for value in samples.index]

    du.print_debug(f"Features shape: {features.shape}")
    du.print_debug(f"Samples shape: {samples.shape}")

    try:
        labels = samples.loc[features.index, label_col]
        du.print_debug(f"Retrieved labels: {labels.shape}")
    except KeyError as exc:
        du.print_error(f"Sample ID mismatch: {exc}")
        missing_ids = features.index.difference(samples.index)
        du.print_warning(f"{len(missing_ids)} feature IDs not found in label set.")
        raise SampleIdMismatchError(list(map(str, missing_ids.tolist()))) from exc

    missing = int(labels.isnull().sum())
    if missing > 0:
        du.print_warning(f"{missing} samples missing labels - excluded.")
        valid_idx = labels.dropna().index
        features = features.loc[valid_idx]
        labels = labels.loc[valid_idx]

    if label_col == "family_id":
        labels = labels.astype(int).astype(str)
        if "family_canonical" in samples.columns:
            family_names = (
                samples.loc[features.index, "family_canonical"]
                .astype(str)
                .str.strip()
            )
            label_map = (
                pd.DataFrame({"family_id": labels.values, "family_name": family_names.values})
                .dropna()
                .drop_duplicates(subset=["family_id"], keep="first")
            )
            labels.attrs["label_name_map"] = {
                str(row["family_id"]): str(row["family_name"])
                for _, row in label_map.iterrows()
                if str(row["family_name"]).strip()
            }
    elif label_col in {"type_slug", "family_within_type"}:
        labels = labels.astype(str).str.strip()
        labels = labels.replace({"": "unknown"})
        labels = labels.fillna("unknown")
    else:
        labels = labels.astype(str).str.strip()

    default_map = {
        "Flubot": "FluBot",
        "Flubot ": "FluBot",
        "Cabassous": "FluBot",
        "Tebot": "TeaBot",
        "teabot": "TeaBot",
        "Cerber": "Cerberus",
        "Golddigger": "GoldDigger",
    }
    normalization_map = normalization_map or default_map
    if label_col not in {"family_id", "type_slug", "family_within_type"}:
        labels = normalize_labels(labels, normalization_map)

    if labels.nunique() <= 1:
        du.print_error("[ALIGNMENT] Label integrity failure: only one class remains after filtering.")
        raise InsufficientLabelClassesError(
            "Label integrity failure: only one class remains after filtering."
        )

    if drop_low_support:
        support_counts = labels.value_counts()
        low_support = support_counts[support_counts < min_samples_per_family].index.tolist()
        if low_support:
            du.print_warning(f"Dropping {len(low_support)} low-support families: {low_support}")
            keep_idx = ~labels.isin(low_support)
            features = features[keep_idx]
            labels = labels[keep_idx]
            if labels.nunique() <= 1:
                raise InsufficientLabelClassesError(
                    "Low-support filtering left fewer than two label classes."
                )

    if verbose:
        du.print_info(f"Classification Label Summary ({label_col})")
        du.print_stat("Total Samples", len(labels))
        du.print_stat("Unique label classes", labels.nunique())
        top = labels.value_counts().head(5)
        du.print_stat("Top labels", ", ".join(f"{fam} ({cnt})" for fam, cnt in top.items()))

    return features, labels
