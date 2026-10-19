"""Training-only weights for exploratory family/lineage dominance sensitivity."""
from __future__ import annotations

import pandas as pd


def lineage_class_weights(training_metadata: pd.DataFrame) -> pd.Series:
    """Give each family equal mass and each lineage within it equal mass.

    Pass only the current training partition, indexed by unique sample IDs.
    These weights change the fitting objective, not cohort admission or labels.
    Mixed-label components remain intact in the upstream grouped split; their
    family-specific cells receive weights here. Do not combine these weights
    with estimator class weighting, which would count class imbalance twice.
    """
    required = ['recorded_family', 'lineage_component']
    if training_metadata.empty or not training_metadata.index.is_unique:
        raise ValueError('Training metadata must have nonempty unique sample IDs')
    if not set(required).issubset(training_metadata.columns):
        raise ValueError('Family and lineage metadata are required')
    data = training_metadata[required]
    if data.isna().any().any() or any(
        data[column].astype(str).str.strip().eq('').any() for column in required
    ):
        raise ValueError('Family and lineage identifiers must be present')
    cell_size = data.groupby(required, sort=False)['recorded_family'].transform('size')
    family_groups = data.groupby('recorded_family', sort=False)[
        'lineage_component'
    ].transform('nunique')
    weights = 1.0 / (cell_size * family_groups)
    weights = weights * (len(data) / weights.sum())
    return weights.rename('training_weight')
