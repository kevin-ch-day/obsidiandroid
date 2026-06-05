"""Align feature vectors with ground-truth labels for ML training."""

from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.labeling.malware_family_constants import (
    GENERIC_TOKENS,
)
from obsidiandroid.labeling.taxonomy import (
    canonicalize_family_label,
    normalize_family_name,
    is_known_family_name,
)


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


def _emit_live_authority_retention_note(rescued: int) -> None:
    """Print the live-authority retention note once per ablation run."""
    if rescued <= 0:
        return
    message = (
        "Authority note: "
        f"{rescued} live-authority-backed sample(s) retained despite local registry drift."
    )
    if bool(getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False)):
        already_emitted = bool(getattr(app_config, "RUNTIME_ABLATION_AUTHORITY_NOTE_EMITTED", False))
        if already_emitted:
            return
        setattr(app_config, "RUNTIME_ABLATION_AUTHORITY_NOTE_EMITTED", True)
    du.print_info(message)


def _normalize_authority_mask(
    family_values: pd.Series,
) -> pd.Series:
    """Return rows that point to an authoritative known family token."""
    normalized = (
        family_values.astype(str)
        .str.strip()
        .apply(lambda value: str(value).strip().lower())
    )
    placeholder = {"", "unknown", "unmapped", "other", "none", "nan", "null"}
    weak_tokens = {token.lower() for token in GENERIC_TOKENS} | {
        "android",
        "malware",
        "banker",
        "ransomware",
        "trojan",
        "spyware",
    }

    # Avoid accidentally learning from AV-style pseudo labels or placeholder tokens.
    def _is_authoritative(value: str) -> bool:
        canonical = normalize_family_name(value)
        if not value or value in placeholder or value in weak_tokens:
            return False
        if "trojan." in value or value.startswith("trojan"):
            return False
        if not canonical or canonical in placeholder:
            return False
        if canonical in weak_tokens:
            return False
        # Keep only canonical family names that map to a known canonical family.
        # This is strict by design for evidence-aligned training and improves
        # consistency between family label intent and downstream authority checks.
        if canonical in {"metasploit", "unknown"}:
            return False
        return is_known_family_name(canonical)

    return normalized.apply(_is_authoritative)


def _live_authority_family_mask(
    family_values: pd.Series,
    *,
    family_ids: pd.Series | None = None,
    family_names: pd.Series | None = None,
    sample_label_kinds: pd.Series | None = None,
    type_values: pd.Series | None = None,
) -> pd.Series:
    """Allow cohort-live authoritative family rows absent from the local registry.

    This is a narrow fallback for runs where the database authority has already
    accepted a family/token pairing but the local static known-family registry has
    not been refreshed yet. It still rejects placeholder/generic/pseudo-family
    labels such as ``trojan.*`` and metasploit-like catch-alls.
    """
    normalized = family_values.astype(str).str.strip().str.lower()
    placeholder = {"", "unknown", "unmapped", "other", "none", "nan", "null"}
    weak_tokens = {token.lower() for token in GENERIC_TOKENS} | {
        "android",
        "malware",
        "banker",
        "ransomware",
        "trojan",
        "spyware",
    }
    if family_ids is None:
        family_ids = pd.Series([None] * len(normalized), index=normalized.index)
    if family_names is None:
        family_names = pd.Series([""] * len(normalized), index=normalized.index)
    if sample_label_kinds is None:
        sample_label_kinds = pd.Series([""] * len(normalized), index=normalized.index)
    if type_values is None:
        type_values = pd.Series([""] * len(normalized), index=normalized.index)

    normalized_family_names = family_names.astype(str).str.strip().str.lower().apply(normalize_family_name)
    normalized_types = type_values.astype(str).str.strip().str.lower()
    normalized_label_kinds = sample_label_kinds.astype(str).str.strip().str.lower()
    family_id_present = family_ids.notna()

    def _is_live_authority_row(value: str, family_name: str, label_kind: str, type_value: str, has_family_id: bool) -> bool:
        canonical = normalize_family_name(value)
        if not has_family_id:
            return False
        if not value or value in placeholder or value in weak_tokens:
            return False
        if "trojan." in value or value.startswith("trojan"):
            return False
        if canonical in placeholder or canonical in weak_tokens or canonical in {"metasploit", "unknown"}:
            return False
        label_kind_ok = label_kind == "family_or_common_name" or family_name == canonical
        if not label_kind_ok:
            return False
        if not type_value or type_value in placeholder or type_value == "unknown":
            return False
        if not family_name or family_name in placeholder:
            return False
        return family_name == canonical

    return pd.Series(
        [
            _is_live_authority_row(value, family_name, label_kind, type_value, bool(has_family_id))
            for value, family_name, label_kind, type_value, has_family_id in zip(
                normalized.tolist(),
                normalized_family_names.tolist(),
                normalized_label_kinds.tolist(),
                normalized_types.tolist(),
                family_id_present.tolist(),
            )
        ],
        index=normalized.index,
    )


def normalize_labels(labels: pd.Series, normalization_map: dict) -> pd.Series:
    """
    Normalize family labels using a known variant map (e.g., "Flubot" -> "FluBot").
    """
    normalized = labels.astype(str).str.strip().replace(normalization_map).fillna("unknown")
    normalized = normalized.apply(
        lambda value: "unknown" if "metasploit" in str(value).lower() else value
    )
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


def _is_default_positional_range_index(index: pd.Index, length: int) -> bool:
    """True when ``index`` is ``0..length-1`` (common after ``reset_index`` without dropping ``sample_id``)."""
    if length <= 0:
        return True
    if not isinstance(index, pd.RangeIndex):
        return False
    return index.equals(pd.RangeIndex(stop=length))


def _maybe_promote_sample_id_column_to_index(features: pd.DataFrame) -> pd.DataFrame:
    """Use ``sample_id`` as the row index when the frame still has a default positional index.

    Without this, ``extract_aligned_labels`` normalizes ``RangeIndex`` values to ``"0".."n"`` and
    label lookup against real sample ids fails or misaligns whenever ``sample_id`` only exists as
    a column (e.g. some export/reload paths).
    """
    if "sample_id" not in features.columns:
        return features
    if not _is_default_positional_range_index(features.index, len(features)):
        return features
    out = features.set_index("sample_id", drop=True)
    if out.index.name in (None, ""):
        out.index.name = "sample_id"
    return out


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
    if verbose:
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
    features = _maybe_promote_sample_id_column_to_index(features)
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
    attrition_stats: dict[str, int] = {
        "alignment_input_rows": int(len(features)),
        "alignment_missing_label_drop_count": 0,
        "alignment_non_authoritative_family_drop_count": 0,
        "alignment_live_authority_rescue_count": 0,
    }
    attrition_details: dict[str, dict[str, int]] = {
        "alignment_non_authoritative_family_drop_families": {},
        "alignment_live_authority_rescue_families": {},
    }
    if missing > 0:
        du.print_warning(f"{missing} samples missing labels - excluded.")
        valid_idx = labels.dropna().index
        features = features.loc[valid_idx]
        labels = labels.loc[valid_idx]
        attrition_stats["alignment_missing_label_drop_count"] = int(missing)

    if label_col == "family_id":
        labels = labels.astype(int).astype(str)
        if "family_canonical" in samples.columns:
            family_names = (
                samples.loc[features.index, "family_canonical"]
                .astype(str)
                .str.strip()
            )

            authority_mask = _normalize_authority_mask(family_names)
            rescued = 0
            if not authority_mask.all():
                live_authority_mask = _live_authority_family_mask(
                    family_names,
                    family_ids=labels,
                    family_names=samples.loc[features.index, "family_name"]
                    if "family_name" in samples.columns
                    else None,
                    sample_label_kinds=samples.loc[features.index, "sample_label_kind"]
                    if "sample_label_kind" in samples.columns
                    else None,
                    type_values=samples.loc[features.index, "type_slug"]
                    if "type_slug" in samples.columns
                    else None,
                )
                rescued = int(((~authority_mask) & live_authority_mask).sum())
                authority_mask = authority_mask | live_authority_mask
                dropped = int((~authority_mask).sum())
                if rescued:
                    _emit_live_authority_retention_note(rescued)
                if dropped:
                    du.print_warning(
                        f"Dropping {dropped} sample(s) with non-authoritative family_canonical labels before training alignment."
                    )
                rescued_family_counts = family_names.loc[(~_normalize_authority_mask(family_names)) & live_authority_mask]
                if not rescued_family_counts.empty:
                    attrition_details["alignment_live_authority_rescue_families"] = {
                        str(key): int(value)
                        for key, value in rescued_family_counts.value_counts().items()
                    }
                dropped_family_counts = family_names.loc[~authority_mask]
                if not dropped_family_counts.empty:
                    attrition_details["alignment_non_authoritative_family_drop_families"] = {
                        str(key): int(value)
                        for key, value in dropped_family_counts.value_counts().items()
                    }
                labels = labels.loc[authority_mask]
                features = features.loc[authority_mask]
                family_names = family_names.loc[authority_mask]
                attrition_stats["alignment_non_authoritative_family_drop_count"] = int(dropped)
                attrition_stats["alignment_live_authority_rescue_count"] = int(rescued)

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
        "Metasploit": "unknown",
        "Trojan.MetaSploit": "unknown",
        "Trojan.Metasploit": "unknown",
        "trojan metasploit": "unknown",
        "trojan metasploit android": "unknown",
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
        du.print_stat("Unique modeled label classes", labels.nunique())
        top = labels.value_counts().head(5)
        du.print_stat("Top labels", ", ".join(f"{fam} ({cnt})" for fam, cnt in top.items()))

    attrition_stats["alignment_rows_post_authority_filter"] = int(len(labels))
    labels.attrs["alignment_attrition_stats"] = attrition_stats
    labels.attrs["alignment_attrition_details"] = attrition_details
    labels.name = str(label_col)
    return features, labels
