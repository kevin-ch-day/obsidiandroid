"""Train-partition feature selection and its reproducibility contract.

Feature selection is part of model fitting.  This module therefore fits its
decisions on a training partition only, then applies the resulting ordered
column contract unchanged to the corresponding evaluation partition.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.common.hash_utils import hash_payload


_BLOCKED_EXACT = {
    "sample_id",
    "true_family",
    "predicted_family",
    "classification_label",
    "family_name",
}
_SEMANTIC_TOKENS = (
    "parsed_family",
    "suggested_family",
    "family_token",
    "threat_class",
    "malware_type",
    "type_slug",
    "suggested_threat_label",
)
_SEMANTIC_EXACT = {
    "meta__has_vt_suggested_threat_label",
    "suggested_threat_label",
    "vt_suggested_threat_label",
}


def normalize_feature_column_names(features_df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with stable string column names and no collisions.

    Recent scikit-learn releases require feature names to be consistently
    typed.  Normalizing at the model boundary also makes the emitted contract
    match exactly what every estimator receives.
    """
    if not isinstance(features_df, pd.DataFrame):
        raise ValueError("Feature matrix must be a pandas DataFrame.")
    normalized = [str(column) for column in features_df.columns]
    duplicate_names = sorted(
        {name for name in normalized if normalized.count(name) > 1}
    )
    if duplicate_names:
        preview = ", ".join(duplicate_names[:8])
        raise ValueError(
            "Feature column names collide after string normalization: " + preview
        )
    result = features_df.copy()
    result.columns = normalized
    return result


def collect_leakage_pruning_audit(
    features_df: pd.DataFrame,
    labels: pd.Series | None,
) -> list[dict[str, str]]:
    """Return leakage-pruning reasons fitted from the supplied training rows."""
    if not isinstance(features_df, pd.DataFrame) or features_df.empty:
        return []

    audit_rows: list[dict[str, str]] = []
    # The headline benchmark is label-independent by default.  A deliberately
    # scoped ablation may retain lexical AV label fields to measure their
    # sensitivity, but must opt in through a runtime flag set only for that
    # individual experiment; it must never relax the headline contract.
    ablation_label_adjacent_allowed = bool(
        getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False)
        and getattr(app_config, "RUNTIME_ABLATION_ALLOW_LABEL_ADJACENT_FEATURES", False)
    )
    allow_av_assisted = bool(
        getattr(app_config, "ENABLE_LABEL_DERIVED_VENDOR_FEATURES", False)
    ) or ablation_label_adjacent_allowed
    aggressive = bool(getattr(app_config, "ENABLE_AGGRESSIVE_LEAKAGE_PRUNING", False))
    idx_as_str = pd.Series(features_df.index.map(str), index=features_df.index)

    for column in features_df.columns:
        column_name = str(column)
        normalized = column_name.lower()
        reason: str | None = None
        details = ""
        if normalized in _BLOCKED_EXACT:
            reason = "blocked_exact_name"
            details = "column name matches known identifier or label field"
        elif not allow_av_assisted and (
            normalized in _SEMANTIC_EXACT
            or any(token in normalized for token in _SEMANTIC_TOKENS)
        ):
            reason = "label_independent_contract_block"
            details = "direct or target-adjacent AV naming semantic prohibited in primary family benchmark"
        else:
            try:
                if features_df[column].map(str).equals(idx_as_str):
                    reason = "matches_sample_id_index"
                    details = "column values match normalized feature index exactly"
            except (TypeError, ValueError):
                pass

        if reason is None and aggressive and labels is not None:
            try:
                pairs = pd.DataFrame({"feature_value": features_df[column], "label": labels})
                mapping_conflicts = pairs.groupby("feature_value")["label"].nunique(dropna=False)
                if (
                    not mapping_conflicts.empty
                    and mapping_conflicts.max() == 1
                    and pairs["feature_value"].nunique() >= 10
                ):
                    reason = "unique_feature_to_label_mapping"
                    details = (
                        "feature values map to exactly one label within training rows "
                        f"(unique_values={int(pairs['feature_value'].nunique())})"
                    )
            except (TypeError, ValueError):
                pass

        if reason is not None:
            audit_rows.append(
                {
                    "column_name": column_name,
                    "reason_code": reason,
                    "details": details,
                }
            )
    return audit_rows


def fit_feature_selection_contract(
    X_train: pd.DataFrame,
    y_train: pd.Series | None = None,
) -> dict[str, Any]:
    """Fit no-variance and leakage guards on training rows only."""
    train = normalize_feature_column_names(X_train)
    low_information = [
        str(column)
        for column in train.columns
        if train[column].nunique(dropna=False) <= 1
    ]
    leakage_audit = collect_leakage_pruning_audit(train, y_train)
    leakage_columns = [str(row["column_name"]) for row in leakage_audit]
    dropped = set(low_information) | set(leakage_columns)
    retained = [str(column) for column in train.columns if str(column) not in dropped]
    if not retained:
        raise ValueError("Feature selection removed every training column.")
    return {
        "schema_version": "1.0",
        "selection_scope": "train_partition_only",
        "fit_sample_count": int(len(train)),
        "fit_sample_id_hash": hash_payload([str(value) for value in train.index.tolist()]),
        "input_feature_column_hash": hash_payload([str(column) for column in train.columns]),
        "retained_feature_columns": retained,
        "retained_feature_column_hash": hash_payload(retained),
        "dropped_low_information_columns": low_information,
        "dropped_leakage_columns": leakage_columns,
        "leakage_pruning_audit": leakage_audit,
        "aggressive_label_mapping_guard_enabled": bool(
            getattr(app_config, "ENABLE_AGGRESSIVE_LEAKAGE_PRUNING", False)
        ),
        "ablation_label_adjacent_features_allowed": bool(
            getattr(app_config, "RUNTIME_ABLATION_ACTIVE", False)
            and getattr(app_config, "RUNTIME_ABLATION_ALLOW_LABEL_ADJACENT_FEATURES", False)
        ),
    }


def apply_feature_selection_contract(
    features_df: pd.DataFrame,
    contract: dict[str, Any],
) -> pd.DataFrame:
    """Apply an ordered train-fitted feature contract without refitting it."""
    features = normalize_feature_column_names(features_df)
    retained = list(contract.get("retained_feature_columns") or [])
    if not retained:
        raise ValueError("Feature selection contract has no retained columns.")
    missing = [column for column in retained if column not in features.columns]
    if missing:
        raise ValueError(
            "Feature matrix does not satisfy the frozen selection contract; missing: "
            + ", ".join(missing[:8])
        )
    selected = features.loc[:, retained].copy()
    selected.attrs.update(features.attrs)
    selected.attrs["feature_selection_contract"] = dict(contract)
    return selected
