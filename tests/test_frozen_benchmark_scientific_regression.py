"""Regression tests for the frozen benchmark's scientific boundaries."""
from __future__ import annotations

import pandas as pd
import pytest

from obsidiandroid.features.av_detection_contract import fit_av_detection_contract
from obsidiandroid.features.av_readiness_contract import fit_av_readiness_contract
from obsidiandroid.features.frozen_abc_features import build_abc_feature_contracts
from obsidiandroid.features.permission_contract import PermissionVocabularyContract, group_definition_payload
from obsidiandroid.governance.frozen_benchmark_manifest import apply_sdk_imputation, fit_sdk_imputation_contract
from obsidiandroid.governance.frozen_benchmark_sources import FrozenBenchmarkSourceBundle
from obsidiandroid.governance.frozen_label_mapping import freeze_label_mapping


def _verdicts(test_positive: bool = False) -> pd.DataFrame:
    rows = []
    for sample_id in range(1, 12):
        rows.append({"sample_id": sample_id, "engine_name": "engine-a", "report_id": f"r{sample_id}", "result": "Trojan.X" if sample_id <= 5 else "undetected"})
        rows.append({"sample_id": sample_id, "engine_name": "engine-b", "report_id": f"r{sample_id}", "result": "Trojan.X" if test_positive and sample_id == 11 else "undetected"})
    return pd.DataFrame(rows)


def test_readiness_is_outer_train_fitted_and_ignores_provider_ready_flag():
    metadata = pd.DataFrame({"engine_name": ["engine-a", "engine-b"], "active": [1, 1], "readiness_eligible_flag": [0, 1]})
    left = fit_av_readiness_contract(_verdicts(False), metadata, range(1, 11))
    right = fit_av_readiness_contract(_verdicts(True), metadata, range(1, 11))
    assert left.eligible_engines == right.eligible_engines == ("engine_a",)
    assert left.policy_hash == right.policy_hash


def test_sdk_null_is_not_zero_filled_before_shared_train_median():
    contract = fit_sdk_imputation_contract(pd.DataFrame({"meta__target_min_version": [21, 25], "meta__target_sdk_version": [30, 34]}), columns=("meta__target_min_version", "meta__target_sdk_version"))
    transformed = apply_sdk_imputation(pd.DataFrame({"meta__target_min_version": [None], "meta__target_sdk_version": [None]}), contract)
    assert transformed.iloc[0].to_dict() == {"meta__target_min_version": 23.0, "meta__target_sdk_version": 32.0}


def test_noncontiguous_family_ids_use_contiguous_model_mapping():
    mapping = freeze_label_mapping(pd.DataFrame({"family_id": [47, 10, 20], "family_canonical": ["charlie", "alpha", "bravo"]}))
    assert mapping.table["class_index"].tolist() == [0, 1, 2]
    assert mapping.encode(pd.Series([10, 47, 20])).tolist() == [0, 2, 1]
    assert mapping.decode([0, 2, 1]).tolist() == [10, 47, 20]


def test_feature_admission_rejects_prefix_compatible_unregistered_permission():
    permissions = pd.DataFrame({"sample_id": [1], "perm__camera": [1], "perm__unregistered_identity_token": [1], "perm__known_dangerous_count": [1], "perm__known_normal_count": [0], "perm__known_total_count": [1], "perm__approved_oem_count": [0]})
    for item in group_definition_payload():
        permissions[f"perm_grp__{item['name']}"] = 0
    metadata = pd.DataFrame({"sample_id": [1], "meta__target_min_version": [21], "meta__target_sdk_version": [30]})
    av = pd.DataFrame({"sample_id": [1], "avdet__engine": [0], "avobs__engine": [1]})
    permission = PermissionVocabularyContract({"ordered_tokens": ["camera"], "contract_hash": "x"})
    contract = fit_av_detection_contract(pd.DataFrame([{"sample_id": 1, "engine_name": "engine", "report_id": "r", "result": "undetected"}]), [1], scope="all_observed")
    with pytest.raises(ValueError, match="unregistered"):
        build_abc_feature_contracts(permissions, metadata, av, av, permission_contract=permission, av_b_contract=contract, av_c_contract=contract)


def test_source_bundle_calls_each_provider_surface_once():
    class MutatingProvider:
        def __init__(self): self.calls: dict[str, int] = {}
        def _frame(self, name):
            self.calls[name] = self.calls.get(name, 0) + 1
            return pd.DataFrame({"value": [self.calls[name]]})
        def cohort_rows(self): return self._frame("cohort")
        def android_metadata(self): return self._frame("metadata")
        def permission_rows(self): return self._frame("permissions")
        def vt_rows(self): return self._frame("verdicts")
        def engine_metadata(self): return self._frame("engines")
        def taxonomy_aliases(self): return self._frame("taxonomy")
    provider = MutatingProvider()
    bundle = FrozenBenchmarkSourceBundle.acquire(provider)
    assert set(provider.calls.values()) == {1}
    assert bundle.cohort.iloc[0, 0] == 1
