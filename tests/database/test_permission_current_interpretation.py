from __future__ import annotations

from obsidiandroid.database.permission_current_interpretation import (
    interpret_permission_evidence,
    interpretation_joins,
    interpretation_selects,
)


def test_current_interpretation_preserves_condition_and_withholds_conflict() -> None:
    conditioned = interpret_permission_evidence(
        token="android.permission.DETECT_SCREEN_RECORDING",
        identity={
            "canonical_permission": "android.permission.DETECT_SCREEN_RECORDING",
            "authority_class": "AOSP_HIDDEN",
            "feature_dependency": "screen.recording.flag",
            "unresolved_conflict_count": 0,
            "compatibility_protection_expression": "signature|role",
        },
    )
    conflict = interpret_permission_evidence(
        token="android.permission.DEVICE_POWER",
        identity={
            "canonical_permission": "android.permission.DEVICE_POWER",
            "authority_class": "AOSP_HIDDEN",
            "feature_dependency": "bluetooth.flag",
            "unresolved_conflict_count": 1,
            "compatibility_protection_expression": "signature|module|role",
        },
    )
    assert conditioned.declaration_state == "CONDITIONED"
    assert conditioned.feature_dependency == "screen.recording.flag"
    assert conflict.identifier_recognition == "EXACT_ACCEPTED_CANONICAL"
    assert conflict.protection_result is None

    accepted_application = interpret_permission_evidence(
        token="android.permission.HOST_DEFINED_EXAMPLE",
        identity={
            "canonical_permission": "android.permission.HOST_DEFINED_EXAMPLE",
            "authority_class": "APPLICATION_DEFINED",
        },
    )
    assert accepted_application.authority_scope == "THIRD_PARTY_APPLICATION_DEFINED"
    assert accepted_application.platform_authority_accepted is False


def test_legacy_membership_never_creates_platform_authority() -> None:
    legacy = {
        "lifecycle_status": "current",
        "authority_source_type": "aosp_package_manifest",
        "source_family_key": "android_system_app_permission",
    }
    package = interpret_permission_evidence(
        token="com.android.launcher.permission.READ_SETTINGS",
        legacy=legacy,
        fact={
            "fact_scope": "permission_definition",
            "authority_source_type": "aosp_package_manifest",
        },
    )
    provider = interpret_permission_evidence(
        token="com.android.email.permission.ACCESS_PROVIDER",
        legacy=legacy,
        fact={
            "fact_scope": "provider_permission",
            "authority_source_type": "aosp_package_manifest",
        },
    )
    baidu = interpret_permission_evidence(
        token="android.permission.BAIDU_LOCATION_SERVICE",
        legacy=legacy,
        fact={
            "fact_scope": "permission_definition",
            "authority_source_type": "sdk_vendor_docs",
        },
        anomaly={"anomaly_class": "vendor_namespace_in_android"},
    )
    provisional = interpret_permission_evidence(
        token="android.permission.PREVENT_POWER_KEY",
        legacy={
            "lifecycle_status": "unvalidated",
            "authority_source_type": "queue_apply_shell",
            "source_family_key": "aosp_sparse_queue_apply_shell",
        },
    )
    assert package.authority_scope == "AOSP_PACKAGE_DEFINED"
    assert provider.authority_scope == "AOSP_PROVIDER_ACL"
    assert provider.identifier_kind == "PROVIDER_PERMISSION"
    assert baidu.authority_scope == "SDK_INTEGRATION_CUSTOM_PERMISSION"
    assert provisional.evidence_state == "PROVISIONAL_SEED_ONLY"
    assert not any(
        decision.platform_authority_accepted
        for decision in (package, provider, baidu, provisional)
    )


def test_historical_third_party_and_platform_identities_do_not_collapse() -> None:
    c2d = interpret_permission_evidence(
        token="android.permission.C2D_MESSAGE",
        fact={
            "fact_scope": "custom_permission_pattern",
            "authority_source_type": "android_public_docs",
            "lifecycle_status": "historical",
        },
    )
    browser = interpret_permission_evidence(
        token="com.android.browser.permission.READ_HISTORY_BOOKMARKS",
        identity={
            "canonical_permission": "com.android.browser.permission.READ_HISTORY_BOOKMARKS",
            "authority_class": "AOSP_INTERNAL",
            "lifecycle": "declared_in_accepted_release",
        },
        fact={
            "fact_scope": "removed_api",
            "authority_source_type": "aosp_framework_manifest",
            "lifecycle_status": "legacy_removed",
        },
    )
    assert c2d.authority_scope == "THIRD_PARTY_APPLICATION_DEFINED"
    assert browser.authority_scope == "HISTORICAL_PLATFORM"
    assert browser.declaration_state == "NOT_APPLICABLE"
    assert browser.protection_result is None


def test_sql_guard_uses_deployed_views_and_withholds_unsafe_scalars() -> None:
    joins = interpretation_joins(
        key_expr="LOWER(TRIM(ops.permission_string))",
        raw_expr="ops.permission_string",
    )
    columns = interpretation_selects(
        historical_source_expr="UPPER(ops.classification)"
    )
    sql = "\n".join([joins, *columns.values()])
    assert "android_permission_v1_current_permission" in sql
    assert "api_permission_declaration_conflict" in sql
    assert "android_permission_v1_1_" not in sql
    assert "PROVISIONAL_SEED_ONLY" in sql
    assert "unresolved_conflict_count" in columns["safe_protection_expression"]
    assert "feature_dependency IS NULL" in columns["safe_protection_expression"]
    assert "AND NOT" in columns["is_aosp_dict_match"]
    assert "NOT_APPLICABLE" in columns["current_declaration_state"]
    assert "pi.permission_id IS NOT NULL AND (paf.fact_scope = 'removed_api'" in columns["current_declaration_state"]
    assert "pi.authority_class = 'OEM_OR_VENDOR'" in columns["current_authority_scope"]
    assert "THIRD_PARTY_APPLICATION_DEFINED" in columns["current_authority_scope"]
    assert "LEFT(COALESCE(paf.authority_source_type,''), 5) = 'aosp_'" in columns["current_authority_scope"]
    assert "AND NOT" in columns["safe_protection_expression"]
    assert "paf.lifecycle_status IN ('historical','legacy_removed','removed') THEN 'HISTORICAL_PLATFORM'" not in columns["current_authority_scope"]
