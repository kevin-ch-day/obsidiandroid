from __future__ import annotations

from obsidiandroid.database.permission_current_interpretation import (
    interpret_permission_evidence,
    interpretation_joins,
    interpretation_selects,
    is_androidx_dynamic_receiver_permission,
)


def test_androidx_dynamic_receiver_pattern_is_exact_and_package_scoped() -> None:
    assert is_androidx_dynamic_receiver_permission(
        "com.example.app.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION"
    )
    assert not is_androidx_dynamic_receiver_permission(
        "com.example.app.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSIONsuffix"
    )
    assert not is_androidx_dynamic_receiver_permission(
        " DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION"
    )
    assert not is_androidx_dynamic_receiver_permission(
        "com.example.app.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION "
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
            "permission_string": "com.android.launcher.permission.READ_SETTINGS",
            "fact_scope": "permission_definition",
            "authority_source_type": "aosp_package_manifest",
        },
    )
    provider = interpret_permission_evidence(
        token="com.android.email.permission.ACCESS_PROVIDER",
        legacy=legacy,
        fact={
            "permission_string": "com.android.email.permission.ACCESS_PROVIDER",
            "fact_scope": "provider_permission",
            "authority_source_type": "aosp_package_manifest",
        },
    )
    baidu = interpret_permission_evidence(
        token="android.permission.BAIDU_LOCATION_SERVICE",
        legacy=legacy,
        fact={
            "permission_string": "android.permission.BAIDU_LOCATION_SERVICE",
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
            "permission_string": "com.android.browser.permission.READ_HISTORY_BOOKMARKS",
            "fact_scope": "removed_api",
            "authority_source_type": "aosp_framework_manifest",
            "lifecycle_status": "legacy_removed",
        },
    )
    assert c2d.authority_scope == "UNKNOWN"
    assert c2d.declaration_state == "NO_DECLARATION"
    assert c2d.evidence_state == "INSUFFICIENT"
    assert browser.authority_scope == "AOSP_PLATFORM"
    assert browser.declaration_state == "UNCONDITIONAL"
    assert browser.platform_authority_accepted is True


def test_exact_catalog_identity_rejects_nonexact_historical_fact() -> None:
    identity = {
        "canonical_permission": "android.permission.CAMERA",
        "authority_class": "AOSP_PUBLIC",
        "lifecycle": "active",
        "compatibility_protection_expression": "dangerous",
    }
    mismatch = interpret_permission_evidence(
        token="android.permission.CAMERA",
        identity=identity,
        fact={
            "permission_string": "ANDROID.PERMISSION.CAMERA",
            "fact_scope": "removed_api",
            "authority_source_type": "aosp_framework_manifest",
            "lifecycle_status": "historical",
        },
    )
    exact = interpret_permission_evidence(
        token="android.permission.CAMERA",
        identity=identity,
        fact={
            "permission_string": "android.permission.CAMERA",
            "fact_scope": "removed_api",
            "authority_source_type": "aosp_framework_manifest",
            "lifecycle_status": "historical",
        },
    )
    assert mismatch.authority_scope == "AOSP_PLATFORM"
    assert mismatch.declaration_state == "UNCONDITIONAL"
    assert mismatch.protection_result == "dangerous"
    assert exact.authority_scope == "AOSP_PLATFORM"
    assert exact.declaration_state == "UNCONDITIONAL"
    assert exact.protection_result == "dangerous"


def test_case_only_catalog_identity_wins_over_lowercase_anomaly() -> None:
    decision = interpret_permission_evidence(
        token="android.permission.internet",
        identity={
            "canonical_permission": "android.permission.INTERNET",
            "authority_class": "AOSP_PUBLIC",
            "compatibility_protection_expression": "normal",
        },
        anomaly={
            "anomaly_class": "typo_variant",
            "token_value": "android.permission.internet",
        },
    )
    assert decision.identifier_recognition == "CASE_ONLY_CANONICAL_CANDIDATE"
    assert decision.authority_scope == "AOSP_PLATFORM"
    assert decision.evidence_state == "ACCEPTED_CANONICAL"
    assert decision.protection_result == "normal"
    assert decision.platform_authority_accepted is True


def test_catalog_historical_and_fact_only_historical_stay_split() -> None:
    retired = interpret_permission_evidence(
        token="android.permission.FLASHLIGHT",
        identity={
            "canonical_permission": "android.permission.FLASHLIGHT",
            "authority_class": "AOSP_HIDDEN",
            "identity_status": "RETIRED",
            "compatibility_protection_expression": "normal",
        },
        fact={
            "permission_string": "android.permission.FLASHLIGHT",
            "fact_scope": "permission_definition",
            "authority_source_type": "aosp_framework_manifest",
            "lifecycle_status": "current",
        },
    )
    fact_only = interpret_permission_evidence(
        token="android.permission.AUTHENTICATE_ACCOUNTS",
        fact={
            "permission_string": "android.permission.AUTHENTICATE_ACCOUNTS",
            "fact_scope": "removed_api",
            "authority_source_type": "aosp_framework_manifest",
            "lifecycle_status": "legacy_removed",
        },
    )
    assert retired.authority_scope == "HISTORICAL_PLATFORM"
    assert retired.declaration_state == "NOT_APPLICABLE"
    assert retired.protection_result is None
    assert fact_only.authority_scope == "HISTORICAL_PLATFORM"
    assert fact_only.declaration_state == "NOT_APPLICABLE"
    assert fact_only.protection_result is None


def test_sql_guard_uses_deployed_views_and_withholds_unsafe_scalars() -> None:
    joins = interpretation_joins(
        key_expr="LOWER(TRIM(ops.permission_string))",
        raw_expr="ops.permission_string",
    )
    columns = interpretation_selects(
        historical_source_expr="UPPER(ops.classification)",
        raw_expr="ops.permission_string",
    )
    sql = "\n".join([joins, *columns.values()])
    assert "android_permission_v1_current_permission" in sql
    assert "COALESCE(als.canonical_token, ops.permission_string)" in sql
    assert "BINARY als.raw_token = BINARY ops.permission_string" in sql
    assert "BINARY a.constant_value = BINARY ops.permission_string" in sql
    assert "a.lifecycle_status = 'invalid_token'" in sql
    assert "queue_apply_shell" in sql
    assert "constant_value_norm" not in sql
    assert "paf.permission_string_norm" not in sql
    assert "HAVING COUNT(*) = 1" in sql
    assert "BINARY TRIM(ops.permission_string)" not in sql
    assert "api_permission_declaration_conflict" in sql
    assert "android_permission_v1_1_" not in sql
    assert "PROVISIONAL_SEED_ONLY" in sql
    assert "unresolved_conflict_count" in columns["safe_protection_expression"]
    assert "feature_dependency IS NULL" in columns["safe_protection_expression"]
    assert "AND NOT" in columns["is_aosp_dict_match"]
    assert "NOT_APPLICABLE" in columns["current_declaration_state"]
    assert "pi.identity_status = 'RETIRED'" in columns["current_declaration_state"]
    assert "pi.lifecycle IN" in columns["current_declaration_state"]
    assert "BINARY paf.permission_string = BINARY COALESCE(als.canonical_token, ops.permission_string)" in columns["current_authority_scope"]
    assert "fact_scope IN ('permission_definition','removed_api','provider_permission')" in sql
    assert "BINARY pnf.token_value = BINARY ops.permission_string" in sql
    assert "AND pi.permission_id IS NULL" in sql
    assert sql.count("pi.permission_id IS NULL") >= 2
    assert "pi.authority_class = 'OEM_OR_VENDOR'" in columns["current_authority_scope"]
    assert "THIRD_PARTY_APPLICATION_DEFINED" in columns["current_authority_scope"]
    assert "LEFT(COALESCE(paf.authority_source_type,''), 5) = 'aosp_'" in columns["current_authority_scope"]
    assert "AND NOT" in columns["safe_protection_expression"]
    assert "paf.lifecycle_status IN ('historical','legacy_removed','removed') THEN 'HISTORICAL_PLATFORM'" not in columns["current_authority_scope"]


def test_source_type_without_permission_definition_is_not_authority() -> None:
    sdk_provider = interpret_permission_evidence(
        token="android.permission.VENDOR_PROVIDER",
        fact={
            "fact_scope": "provider_permission",
            "authority_source_type": "sdk_vendor_docs",
        },
    )
    chromium_pattern = interpret_permission_evidence(
        token="org.example.permission.CUSTOM",
        fact={
            "fact_scope": "custom_permission_pattern",
            "authority_source_type": "chromium_source",
        },
    )
    padded_definition = interpret_permission_evidence(
        token=" android.permission.VENDOR_CUSTOM",
        fact={
            "permission_string": "android.permission.VENDOR_CUSTOM",
            "fact_scope": "permission_definition",
            "authority_source_type": "sdk_vendor_docs",
        },
    )
    assert sdk_provider.authority_scope == "UNKNOWN"
    assert sdk_provider.evidence_state == "INSUFFICIENT"
    assert chromium_pattern.authority_scope == "UNKNOWN"
    assert chromium_pattern.evidence_state == "INSUFFICIENT"
    assert padded_definition.authority_scope == "UNKNOWN"
    assert padded_definition.evidence_state == "INSUFFICIENT"
