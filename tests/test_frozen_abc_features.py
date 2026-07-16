import pandas as pd
import pytest

from obsidiandroid.features.frozen_abc_features import build_abc_feature_contracts
from obsidiandroid.features.av_detection_contract import AVDetectionContract
from obsidiandroid.features.permission_contract import PermissionVocabularyContract
from obsidiandroid.features.permission_contract import group_definition_payload
from obsidiandroid.common.hash_utils import hash_payload


def _base_inputs():
    permissions = pd.DataFrame({"sample_id": [1, 2], "perm__camera": [1, 0], "perm__known_total_count": [1, 0], "perm__known_dangerous_count": [1, 0], "perm__known_normal_count": [0, 0], "perm__approved_oem_count": [0, 0]})
    for item in group_definition_payload():
        permissions[f"perm_grp__{item['name']}"] = 0
    metadata = pd.DataFrame({"sample_id": [1, 2], "meta__target_min_version": [21, 22], "meta__target_sdk_version": [30, 31], "meta__vt_ratio": [1, 2]})
    b = pd.DataFrame({"sample_id": [1, 2], "avdet__a": [1, 0], "avobs__a": [1, 1]})
    c = pd.DataFrame({"sample_id": [1, 2], "avdet__b": [0, 1], "avobs__b": [1, 1]})
    return permissions, metadata, b, c


def _contracts():
    payload = {"ordered_tokens": ["camera"], "contract_hash": "permission"}
    permission = PermissionVocabularyContract(payload)
    b = AVDetectionContract(("a",), "all_observed", "test", "b", pd.DataFrame())
    c = AVDetectionContract(("b",), "readiness_eligible", "test", "c", pd.DataFrame())
    return {"permission_contract": permission, "av_b_contract": b, "av_c_contract": c}


def test_abc_admission_keeps_only_approved_columns_and_shared_non_av_base():
    permissions, metadata, b, c = _base_inputs()
    contracts = build_abc_feature_contracts(permissions, metadata, b, c, **_contracts())
    assert "meta__vt_ratio" not in contracts.frames["A"]
    assert [x for x in contracts.frames["B"] if not x.startswith("av")] == list(contracts.frames["A"])
    assert [x for x in contracts.frames["C"] if not x.startswith("av")] == list(contracts.frames["A"])


def test_abc_admission_rejects_unregistered_permission_source_columns():
    permissions, metadata, b, c = _base_inputs()
    permissions["package_present"] = 1
    with pytest.raises(ValueError, match="unregistered"):
        build_abc_feature_contracts(permissions, metadata, b, c, **_contracts())
