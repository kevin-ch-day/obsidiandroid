import pandas as pd

from obsidiandroid.features.permission_contract import (
    freeze_permission_knowledge_snapshot,
    fit_permission_vocabulary,
    transform_permission_features,
)


def test_permission_knowledge_snapshot_hashes_all_feature_knowledge_inputs() -> None:
    snapshot = freeze_permission_knowledge_snapshot(
        permission_dictionary=pd.DataFrame({"token": ["android.permission.INTERNET"]}),
        authority_classification=pd.DataFrame({"token": ["android.permission.INTERNET"], "authority": ["AOSP"]}),
        protection_level_classification=pd.DataFrame({"token": ["android.permission.INTERNET"], "protection": ["normal"]}),
        approved_oem_google_tokens=["com.google.android.c2dm.permission.RECEIVE"],
        alias_map={"android.permission.old": "android.permission.new"},
    )
    assert len(snapshot["permission_knowledge_snapshot_hash"]) == 64
    assert snapshot["known_missing_protection_policy"].startswith("retain_known")


def _rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sample_id": [1, 1, 1, 2, 2, 3, 4, 5, 6],
            "permission_string": [
                "android.permission.CAMERA", "android.permission.CAMERA", "com.app.permission.ID",
                "android.permission.CAMERA", "android.permission.INTERNET", "android.permission.CAMERA",
                "android.permission.INTERNET", "android.permission.INTERNET", "android.permission.SEND_SMS",
            ],
            "permission_source": ["AOSP", "AOSP", "APP_DEFINED", "AOSP", "AOSP", "AOSP", "AOSP", "AOSP", "AOSP"],
            "is_aosp_dict_match": [1, 1, 0, 1, 1, 1, 1, 1, 1],
            "protection_level": ["DANGEROUS", "DANGEROUS", "UNKNOWN", "DANGEROUS", "NORMAL", "DANGEROUS", "NORMAL", "NORMAL", "DANGEROUS"],
        }
    )


def test_known_permission_contract_deduplicates_and_excludes_custom_tokens() -> None:
    contract = fit_permission_vocabulary(_rows(), [1, 2, 3, 4, 5], min_support=2, max_tokens=10)
    assert contract.tokens == ["android.permission.camera", "android.permission.internet"]
    assert "com.app.permission.id" not in contract.tokens
    out, audit = transform_permission_features(_rows(), [1, 6], contract)
    assert out.loc[out.sample_id == 1, "perm__android_permission_camera"].item() == 1
    assert audit["unseen_token_count"] == 1


def test_permission_contract_never_adds_test_only_columns() -> None:
    contract = fit_permission_vocabulary(_rows(), [1, 2, 3, 4, 5], min_support=2, max_tokens=1)
    out, _ = transform_permission_features(_rows(), [6], contract)
    assert "perm__android_permission_send_sms" not in out.columns
