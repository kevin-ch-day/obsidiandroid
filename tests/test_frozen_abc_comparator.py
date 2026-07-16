import pandas as pd
import pytest

from obsidiandroid.evaluation.frozen_abc_comparator import paired_lineage_component_bootstrap, validate_paired_prediction_ledger


def _predictions():
    rows = []
    for arm, predictions in {"A": [0, 1, 0, 1, 0, 1, 0, 1], "B": [0, 1, 1, 1, 0, 0, 0, 1]}.items():
        for sample_id, (component, family, truth, prediction) in enumerate(zip(["c1", "c1", "c2", "c2", "c3", "c3", "c4", "c4"], [0, 0, 0, 0, 1, 1, 1, 1], [0, 1, 0, 1, 0, 1, 0, 1], predictions), start=1):
            rows.append({"sample_id": sample_id, "lineage_component_id": component, "family_id": family, "model": "random_forest", "arm": arm, "y_true": truth, "y_pred": prediction})
    return pd.DataFrame(rows)


def test_component_bootstrap_is_paired_and_frozen():
    result = paired_lineage_component_bootstrap(_predictions(), model="random_forest", left_arm="A", right_arm="B")
    assert result["comparison"] == "B-A"
    assert result["method"].startswith("paired_family_stratified")
    assert result["draws"] == 1000 and result["seed"] == 20260716
    assert result["ci_lower"] <= result["ci_upper"]


def test_pairing_mismatch_fails_closed():
    rows = _predictions()
    rows.loc[(rows.arm == "B") & (rows.sample_id == 1), "y_true"] = 1
    with pytest.raises(ValueError, match="mismatch"):
        validate_paired_prediction_ledger(rows)


def test_nonfrozen_bootstrap_parameters_are_rejected():
    with pytest.raises(ValueError, match="requires"):
        paired_lineage_component_bootstrap(_predictions(), model="random_forest", left_arm="A", right_arm="B", draws=10)
