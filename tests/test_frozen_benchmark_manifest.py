import pandas as pd
import pytest

from obsidiandroid.governance.frozen_benchmark_manifest import (
    apply_sdk_imputation,
    fit_sdk_imputation_contract,
    persist_source_extract,
    snapshot_metadata,
    validate_atomic_evaluation_plan,
    validate_estimator_protocol,
)


def _plan():
    return {"arms": ["A", "B", "C"], "models": ["random_forest", "logistic_regression", "xgboost"], "sensitivity_contrasts": [("B", "detection_only"), ("B", "detection_plus_mask"), ("C", "detection_only"), ("C", "detection_plus_mask")], "paired_comparisons": ["B-A", "C-A", "C-B"], "metrics": ["macro_f1"]}


def test_sdk_imputation_is_fit_only_on_outer_train():
    contract = fit_sdk_imputation_contract(pd.DataFrame({"target_min_version": [21, None, 25], "target_sdk_version": [30, 31, None]}))
    test = apply_sdk_imputation(pd.DataFrame({"target_min_version": [None], "target_sdk_version": [99]}), contract)
    assert test.loc[0, "target_min_version"] == 23
    assert test.loc[0, "target_sdk_version"] == 99


def test_atomic_plan_and_estimator_api_are_validated():
    validate_atomic_evaluation_plan(_plan())
    assert "multiclass_resolution" in validate_estimator_protocol()["logistic_regression"]


def test_source_extract_is_content_addressed(tmp_path):
    entry = persist_source_extract("cohort_labels", pd.DataFrame({"sample_id": [1], "family": ["a"]}), tmp_path)
    assert entry["reconstructable"] and (tmp_path / "source_extracts").exists()
    assert not snapshot_metadata("permissions", {"hash": "only"}, reconstructable=False)["reconstructable"]


def test_atomic_plan_rejects_missing_sensitivity():
    plan = _plan()
    plan["sensitivity_contrasts"] = []
    with pytest.raises(ValueError, match="sensitivity"):
        validate_atomic_evaluation_plan(plan)
