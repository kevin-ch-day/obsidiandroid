"""Paired held-out comparisons for the frozen A/B/C protocol.

The evaluator supplies predictions only after a separately authorized atomic
run.  This module verifies the pairing and computes the prespecified
lineage-component percentile bootstrap without refitting any model.
"""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score


BOOTSTRAP_DRAWS = 1000
BOOTSTRAP_SEED = 20260716
CONFIDENCE_LEVEL = 0.95
_REQUIRED = {"sample_id", "lineage_component_id", "family_id", "model", "arm", "y_true", "y_pred"}


def validate_paired_prediction_ledger(predictions: pd.DataFrame) -> None:
    """Require identical held-out sample/label assignments per model and arm."""
    missing = _REQUIRED.difference(predictions.columns)
    if missing:
        raise ValueError(f"Prediction ledger missing columns: {sorted(missing)}")
    for model, model_rows in predictions.groupby("model", sort=False):
        reference: pd.DataFrame | None = None
        for arm, arm_rows in model_rows.groupby("arm", sort=False):
            ledger = arm_rows[["sample_id", "lineage_component_id", "y_true"]].sort_values("sample_id").reset_index(drop=True)
            if ledger["sample_id"].duplicated().any():
                raise ValueError(f"Duplicate held-out prediction rows for model={model}, arm={arm}.")
            if reference is None:
                reference = ledger
            elif not ledger.equals(reference):
                raise ValueError(f"Paired split/label mismatch for model={model}, arm={arm}.")
        if reference is None or reference.empty:
            raise ValueError(f"No held-out predictions for model={model}.")
    if predictions.groupby("lineage_component_id")["family_id"].nunique().gt(1).any():
        raise ValueError("A lineage component must belong to one canonical family.")
    if not predictions["family_id"].eq(predictions["y_true"]).all():
        raise ValueError("Prediction ledger family_id must equal canonical y_true.")


def _macro_f1(rows: pd.DataFrame, labels: Iterable[Any]) -> float:
    if rows.empty:
        raise ValueError("Undefined bootstrap draw: no sampled held-out predictions.")
    return float(f1_score(rows["y_true"], rows["y_pred"], labels=list(labels), average="macro", zero_division=0))


def paired_lineage_component_bootstrap(
    predictions: pd.DataFrame,
    *,
    model: str,
    left_arm: str,
    right_arm: str,
    draws: int = BOOTSTRAP_DRAWS,
    seed: int = BOOTSTRAP_SEED,
    label_universe: Iterable[Any] | None = None,
) -> dict[str, object]:
    """Compute original point estimates and a paired component bootstrap CI.

    Every draw samples one shared sequence of lineage components for both arms.
    An undefined draw raises immediately; a partial CI is never emitted.
    """
    if draws != BOOTSTRAP_DRAWS or seed != BOOTSTRAP_SEED:
        raise ValueError("Frozen benchmark bootstrap requires 1,000 draws and seed 20260716.")
    validate_paired_prediction_ledger(predictions)
    rows = predictions[predictions["model"] == model].copy()
    arms = {left_arm, right_arm}
    rows = rows[rows["arm"].isin(arms)]
    if set(rows["arm"].unique()) != arms:
        raise ValueError("Undefined bootstrap comparison: required arm predictions are absent.")
    labels = list(label_universe) if label_universe is not None else sorted(rows["y_true"].drop_duplicates().tolist())
    left = rows[rows["arm"] == left_arm].set_index("sample_id", drop=False)
    right = rows[rows["arm"] == right_arm].set_index("sample_id", drop=False)
    components = sorted(left["lineage_component_id"].drop_duplicates().tolist())
    if not components:
        raise ValueError("Undefined bootstrap comparison: no lineage components.")
    left_groups = {component: group for component, group in left.groupby("lineage_component_id", sort=False)}
    right_groups = {component: group for component, group in right.groupby("lineage_component_id", sort=False)}
    if set(left_groups) != set(right_groups):
        raise ValueError("Paired component mismatch between compared arms.")
    point_left, point_right = _macro_f1(left, labels), _macro_f1(right, labels)
    component_families = left.drop_duplicates("lineage_component_id").set_index("lineage_component_id")["family_id"].to_dict()
    family_components: dict[Any, list[str]] = {}
    for component in components:
        family_components.setdefault(component_families[component], []).append(component)
    if any(len(items) < 2 for items in family_components.values()):
        raise ValueError("Undefined bootstrap comparison: a family has fewer than two held-out components.")
    rng = np.random.default_rng(seed)
    differences: list[float] = []
    for _ in range(draws):
        sampled = [
            component
            for family in sorted(family_components, key=str)
            for component in rng.choice(family_components[family], size=len(family_components[family]), replace=True)
        ]
        try:
            left_draw = pd.concat([left_groups[component] for component in sampled], ignore_index=True)
            right_draw = pd.concat([right_groups[component] for component in sampled], ignore_index=True)
            differences.append(_macro_f1(right_draw, labels) - _macro_f1(left_draw, labels))
        except (ValueError, KeyError) as exc:
            raise ValueError(f"Undefined bootstrap draw; fail closed: {exc}") from exc
    alpha = (1.0 - CONFIDENCE_LEVEL) / 2.0
    return {
        "method": "paired_family_stratified_lineage_component_percentile_bootstrap",
        "draws": BOOTSTRAP_DRAWS,
        "seed": BOOTSTRAP_SEED,
        "confidence_level": CONFIDENCE_LEVEL,
        "model": model,
        "comparison": f"{right_arm}-{left_arm}",
        "left_macro_f1": point_left,
        "right_macro_f1": point_right,
        "point_difference": point_right - point_left,
        "ci_lower": float(np.quantile(differences, alpha)),
        "ci_upper": float(np.quantile(differences, 1.0 - alpha)),
        "component_count": len(components),
    }
