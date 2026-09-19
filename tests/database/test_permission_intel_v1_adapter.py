from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from obsidiandroid.database.permission_intel_v1.adapter import (
    CATALOG_STATUS_SQL,
    DECLARATION_ALTERNATIVES_SQL,
    PERMISSION_FLAGS_SQL,
    PERMISSION_LOOKUP_SQL,
    SOURCE_EVIDENCE_SQL,
    SPLIT_PERMISSION_SQL,
    PermissionIntelV1Adapter,
)
from obsidiandroid.database.permission_intel_v1.models import (
    PINNED_CATALOG_RELEASE_ID,
    AuthorityClass,
)


class FakeQuery:
    def __init__(self, permission_row: Mapping[str, Any] | None = None) -> None:
        self.permission_row = permission_row
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def __call__(
        self, sql: str, params: Sequence[object]
    ) -> Sequence[Mapping[str, Any]]:
        self.calls.append((sql, tuple(params)))
        if sql == CATALOG_STATUS_SQL:
            return []
        if sql == PERMISSION_LOOKUP_SQL:
            return [self.permission_row] if self.permission_row is not None else []
        if sql == DECLARATION_ALTERNATIVES_SQL:
            return []
        if sql == PERMISSION_FLAGS_SQL:
            return [
                {
                    "catalog_release_id": self.permission_row["catalog_release_id"],
                    "normalized_flag": "hardRestricted",
                },
                {
                    "catalog_release_id": self.permission_row["catalog_release_id"],
                    "normalized_flag": "softRestricted",
                },
            ]
        if sql == SPLIT_PERMISSION_SQL:
            return [
                {
                    "source_permission": params[0],
                    "target_permission": "android.permission.READ_CALL_LOG",
                    "target_sdk_threshold": 16,
                    "target_ordinal": 1,
                    "platform_release_id": "android-api-37",
                    "source_snapshot_id": "aosp-platform-xml",
                }
            ]
        if sql == SOURCE_EVIDENCE_SQL:
            return [{"fact_type": "DECLARATION", "source_snapshot_id": "aosp"}]
        raise AssertionError(f"unexpected SQL: {sql}")


def _permission_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "catalog_release_id": PINNED_CATALOG_RELEASE_ID,
        "catalog_digest": "a" * 64,
        "interpretation_contract_version": "1.1.0-draft",
        "canonical_permission": "android.permission.CAMERA",
        "symbolic_name": "CAMERA",
        "namespace": "android.permission",
        "defining_package": "android",
        "authority_class": "AOSP_PUBLIC",
        "identity_recognition_state": "ACCEPTED_EXACT_IDENTITY",
        "declaration_state": "SINGLE_UNCONDITIONAL_DECLARATION",
        "applicability_state": "DECLARED_IN_ACCEPTED_SOURCE_SCOPE_NOT_DEVICE_GRANT",
        "protection_state": "DECLARED_IN_ACCEPTED_SOURCE_SCOPE",
        "evidence_basis": "MANIFEST_DECLARATION",
        "scalar_projection_status": "DECLARED_SOURCE_SCOPED",
        "lifecycle": "declared_in_accepted_release",
        "visibility": "public",
        "accepted_platform_release": "37.2",
        "sdk_extension_release_id": "sdkext-u-23-api-37-1",
        "source_snapshot_id": "aosp-core-manifest",
        "source_provenance_status": "PRESENT",
        "public_manifest_exposed": 1,
        "public_health_exposed": 0,
        "health_module_declared": 0,
        "protection_base": "dangerous",
        "protection_modifiers": "instant|runtime",
        "compatibility_protection_expression": "dangerous|instant|runtime",
        "raw_protection_expression": "dangerous|instant|runtime",
    }
    row.update(overrides)
    return row


def test_parameterized_permission_lookup_and_typed_result() -> None:
    query = FakeQuery(_permission_row())
    fact = PermissionIntelV1Adapter(query).get_permission("android.permission.CAMERA")
    assert fact is not None
    assert fact.canonical_permission == "android.permission.CAMERA"
    assert fact.platform_release is not None
    assert fact.platform_release.full == "37.2"
    assert fact.sdk_extension_release_id == "sdkext-u-23-api-37-1"
    assert fact.protection.base == "dangerous"
    assert fact.protection.modifiers == ("instant", "runtime")
    assert fact.flags == ("hardRestricted", "softRestricted")
    assert fact.declaration_state == "SINGLE_UNCONDITIONAL_DECLARATION"
    assert query.calls[0] == (PERMISSION_LOOKUP_SQL, ("android.permission.CAMERA",))
    assert "%s" in query.calls[0][0]
    assert query.calls[1] == (
        DECLARATION_ALTERNATIVES_SQL,
        ("android.permission.CAMERA",),
    )


def test_unknown_permission_returns_none_without_flag_query() -> None:
    query = FakeQuery(None)
    assert (
        PermissionIntelV1Adapter(query).get_permission("android.permission.UNKNOWN")
        is None
    )
    assert [sql for sql, _ in query.calls] == [PERMISSION_LOOKUP_SQL]


def test_case_variant_is_not_normalized_before_query() -> None:
    query = FakeQuery(None)
    PermissionIntelV1Adapter(query).get_permission("android.permission.camera")
    assert query.calls[0][1] == ("android.permission.camera",)
    assert "BINARY" in query.calls[0][0]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("AOSP_PUBLIC", AuthorityClass.AOSP_PUBLIC),
        ("AOSP_HIDDEN", AuthorityClass.AOSP_HIDDEN),
        ("AOSP_INTERNAL", AuthorityClass.AOSP_INTERNAL),
        ("AOSP_MODULE", AuthorityClass.AOSP_MODULE),
        ("GOOGLE_OR_GMS", AuthorityClass.GOOGLE_OR_GMS),
        ("OEM_OR_VENDOR", AuthorityClass.OEM_OR_VENDOR),
        ("APPLICATION_DEFINED", AuthorityClass.APPLICATION_DEFINED),
        ("PROVISIONAL", AuthorityClass.PROVISIONAL),
        ("something-new", AuthorityClass.UNKNOWN),
    ],
)
def test_authority_classes(raw: str, expected: AuthorityClass) -> None:
    assert AuthorityClass.from_value(raw) is expected


def test_app_defined_is_not_manufacturer_authority() -> None:
    assert (
        AuthorityClass.from_value("APP_DEFINED") is AuthorityClass.APPLICATION_DEFINED
    )
    assert AuthorityClass.from_value("APP_DEFINED") is not AuthorityClass.OEM_OR_VENDOR


def test_hidden_internal_permission() -> None:
    query = FakeQuery(
        _permission_row(
            authority_class="AOSP_INTERNAL",
            protection_base="internal",
            protection_modifiers="privileged",
            compatibility_protection_expression="internal|privileged",
        )
    )
    fact = PermissionIntelV1Adapter(query).get_permission("android.permission.INTERNAL")
    assert fact is not None
    assert fact.authority_class is AuthorityClass.AOSP_INTERNAL
    assert fact.protection.base == "internal"
    assert fact.protection.modifiers == ("privileged",)


def test_split_and_evidence_queries_are_parameterized() -> None:
    query = FakeQuery()
    adapter = PermissionIntelV1Adapter(query)
    splits = adapter.get_split_relations("android.permission.READ_CONTACTS")
    evidence = adapter.get_source_evidence("android.permission.READ_CONTACTS")
    assert splits[0].target_permission == "android.permission.READ_CALL_LOG"
    assert evidence[0]["fact_type"] == "DECLARATION"
    assert query.calls[0][1] == ("android.permission.READ_CONTACTS",)
    assert query.calls[1][1] == ("android.permission.READ_CONTACTS",)


def test_adapter_sql_uses_deployed_v1_views() -> None:
    for sql in (
        PERMISSION_LOOKUP_SQL,
        DECLARATION_ALTERNATIVES_SQL,
        PERMISSION_FLAGS_SQL,
        SPLIT_PERMISSION_SQL,
        SOURCE_EVIDENCE_SQL,
    ):
        assert "android_permission_v1_1_" not in sql
        assert "BINARY" in sql
    assert "android_permission_v1_current_permission" in PERMISSION_LOOKUP_SQL
    assert "android_permission_v1_current_protection" in PERMISSION_LOOKUP_SQL
    assert "api_permission_declaration_conflict" in PERMISSION_LOOKUP_SQL
    assert "HAVING COUNT(*) = 1" in PERMISSION_LOOKUP_SQL
    assert "android_permission_v1_source_evidence" in SOURCE_EVIDENCE_SQL
    assert "android_permission_v1_current_flag" in PERMISSION_FLAGS_SQL
    assert "android_permission_v1_split_permission" in SPLIT_PERMISSION_SQL


def test_deployed_v1_row_derives_interpretation_and_withholds_conditioned_scalars() -> None:
    camera = {
        "catalog_release_id": PINNED_CATALOG_RELEASE_ID,
        "catalog_digest": "a" * 64,
        "canonical_permission": "android.permission.CAMERA",
        "symbolic_name": "CAMERA",
        "namespace": "android.permission",
        "defining_package": "android",
        "authority_class": "AOSP_PUBLIC",
        "identity_status": "ACCEPTED",
        "lifecycle": "declared_in_accepted_release",
        "visibility": None,
        "accepted_platform_release": "37",
        "sdk_extension_release_id": None,
        "source_snapshot_id": "aosp-core-manifest",
        "source_provenance_status": "PRESENT",
        "public_manifest_exposed": 1,
        "public_health_exposed": 0,
        "health_module_declared": 0,
        "feature_dependency": None,
        "unresolved_conflict_count": 0,
        "protection_base": "dangerous",
        "protection_modifiers": "instant",
        "compatibility_protection_expression": "dangerous|instant",
        "raw_protection_expression": "dangerous|instant",
    }
    fact = PermissionIntelV1Adapter(FakeQuery(camera)).get_permission(
        "android.permission.CAMERA"
    )
    assert fact is not None
    assert fact.interpretation_contract_version == "1.0.0-draft"
    assert fact.identity_recognition_state == "ACCEPTED_EXACT_IDENTITY"
    assert fact.declaration_state == "SINGLE_UNCONDITIONAL_DECLARATION"
    assert fact.scalar_projection_status == "DECLARED_SOURCE_SCOPED"
    assert fact.protection.base == "dangerous"
    assert fact.flags == ("hardRestricted", "softRestricted")

    conditioned = dict(camera)
    conditioned["canonical_permission"] = "android.permission.DEVICE_POWER"
    conditioned["feature_dependency"] = "flag.device_power"
    conditioned["protection_base"] = "signature"
    conditioned["protection_modifiers"] = "role"
    conditioned["compatibility_protection_expression"] = "signature|role"
    query = FakeQuery(conditioned)
    withheld = PermissionIntelV1Adapter(query).get_permission(
        "android.permission.DEVICE_POWER"
    )
    assert withheld is not None
    assert withheld.declaration_state == "CONDITIONED"
    assert withheld.scalar_projection_status == "WITHHELD_UNRESOLVED_ALTERNATIVES"
    assert withheld.protection.base is None
    assert withheld.flags == ()
    assert [sql for sql, _ in query.calls] == [
        PERMISSION_LOOKUP_SQL,
        DECLARATION_ALTERNATIVES_SQL,
    ]


def test_null_split_threshold_is_preserved() -> None:
    def query(sql: str, params: Sequence[object]) -> Sequence[Mapping[str, Any]]:
        assert sql == SPLIT_PERMISSION_SQL
        return [
            {
                "source_permission": params[0],
                "target_permission": "android.permission.READ_EXTERNAL_STORAGE",
                "target_sdk_threshold": None,
                "target_ordinal": 1,
                "platform_release_id": "android-api-37",
                "source_snapshot_id": "aosp-platform-xml",
            }
        ]

    splits = PermissionIntelV1Adapter(query).get_split_relations(
        "android.permission.WRITE_EXTERNAL_STORAGE"
    )
    assert splits[0].target_sdk_threshold is None


def test_accepted_identity_without_protection_withholds_scalars() -> None:
    row = {
        "catalog_release_id": PINNED_CATALOG_RELEASE_ID,
        "catalog_digest": "a" * 64,
        "canonical_permission": "android.permission.MANAGE_CONTACTS",
        "symbolic_name": "MANAGE_CONTACTS",
        "namespace": "android.permission",
        "defining_package": "android",
        "authority_class": "AOSP_PUBLIC",
        "identity_status": "ACCEPTED",
        "lifecycle": None,
        "visibility": None,
        "accepted_platform_release": "37",
        "sdk_extension_release_id": None,
        "source_snapshot_id": None,
        "source_provenance_status": "PRESENT",
        "public_manifest_exposed": 1,
        "public_health_exposed": 0,
        "health_module_declared": 0,
        "feature_dependency": None,
        "unresolved_conflict_count": 0,
        "protection_base": None,
        "protection_modifiers": None,
        "compatibility_protection_expression": None,
        "raw_protection_expression": None,
    }
    query = FakeQuery(row)
    fact = PermissionIntelV1Adapter(query).get_permission(
        "android.permission.MANAGE_CONTACTS"
    )
    assert fact is not None
    assert fact.declaration_state == "SINGLE_UNCONDITIONAL_DECLARATION"
    assert fact.scalar_projection_status == "WITHHELD_MISSING_PROTECTION"
    assert fact.protection.base is None
    assert fact.flags == ()
    assert [sql for sql, _ in query.calls] == [
        PERMISSION_LOOKUP_SQL,
        DECLARATION_ALTERNATIVES_SQL,
    ]


def test_case_variant_lookup_does_not_invent_catalog_identity() -> None:
    query = FakeQuery(None)
    assert (
        PermissionIntelV1Adapter(query).get_permission("android.permission.internet")
        is None
    )
    assert query.calls[0][1] == ("android.permission.internet",)
    assert "BINARY p.canonical_permission = BINARY %s" in query.calls[0][0]


def test_empty_permission_is_rejected_before_query() -> None:
    query = FakeQuery()
    with pytest.raises(ValueError):
        PermissionIntelV1Adapter(query).get_permission(" ")
    assert query.calls == []


@pytest.mark.parametrize(
    "value", [" android.permission.CAMERA", "android.permission.CAMERA "]
)
def test_surrounding_whitespace_is_rejected_before_query(value: str) -> None:
    query = FakeQuery()
    with pytest.raises(ValueError, match="surrounding whitespace"):
        PermissionIntelV1Adapter(query).get_permission(value)
    assert query.calls == []


def test_unknown_source_flag_fails_closed() -> None:
    def bad_flags(sql: str, params: Sequence[object]) -> Sequence[Mapping[str, Any]]:
        if sql == PERMISSION_LOOKUP_SQL:
            return [_permission_row()]
        if sql == DECLARATION_ALTERNATIVES_SQL:
            return []
        if sql == PERMISSION_FLAGS_SQL:
            return [
                {
                    "catalog_release_id": _permission_row()["catalog_release_id"],
                    "normalized_flag": "inventedFlag",
                }
            ]
        return []

    with pytest.raises(ValueError, match="unrecognized v1 permission flags"):
        PermissionIntelV1Adapter(bad_flags).get_permission("android.permission.CAMERA")


def test_permission_lookup_rejects_cross_catalog_flag_rows() -> None:
    def drifted_flags(
        sql: str, params: Sequence[object]
    ) -> Sequence[Mapping[str, Any]]:
        if sql == PERMISSION_LOOKUP_SQL:
            return [_permission_row()]
        if sql == DECLARATION_ALTERNATIVES_SQL:
            return []
        if sql == PERMISSION_FLAGS_SQL:
            return [{"catalog_release_id": "different-release", "normalized_flag": "runtime"}]
        return []

    with pytest.raises(ValueError, match="catalog changed"):
        PermissionIntelV1Adapter(drifted_flags).get_permission(
            "android.permission.CAMERA"
        )


def test_conditional_alternatives_withhold_scalar_and_skip_selected_flags() -> None:
    row = _permission_row(
        canonical_permission="android.permission.DEVICE_POWER",
        declaration_state="MULTIPLE_FEATURE_DEPENDENT_ALTERNATIVES",
        applicability_state="REQUIRES_BUILD_CONFIGURATION_EVIDENCE",
        protection_state="UNKNOWN_REQUIRES_BUILD_CONFIGURATION",
        evidence_basis="MANIFEST_CONDITIONAL_ALTERNATIVES",
        scalar_projection_status="WITHHELD_UNRESOLVED_ALTERNATIVES",
        protection_base=None,
        protection_modifiers=None,
        compatibility_protection_expression=None,
        raw_protection_expression=None,
    )

    def query(sql: str, params: Sequence[object]) -> Sequence[Mapping[str, Any]]:
        if sql == PERMISSION_LOOKUP_SQL:
            return [row]
        if sql == DECLARATION_ALTERNATIVES_SQL:
            return [
                {
                    "catalog_release_id": row["catalog_release_id"],
                    "catalog_digest": row["catalog_digest"],
                    "declaration_revision_id": "decl-false",
                    "feature_dependency": "!flag.device_power",
                    "feature_flag": "flag.device_power",
                    "feature_flag_value": 0,
                    "applicability_state": "REQUIRES_BUILD_CONFIGURATION_EVIDENCE",
                    "accepted_platform_release": "37",
                    "protection_base": "signature",
                    "protection_modifiers": "role",
                    "compatibility_protection_expression": "signature|role",
                },
                {
                    "catalog_release_id": row["catalog_release_id"],
                    "catalog_digest": row["catalog_digest"],
                    "declaration_revision_id": "decl-true",
                    "feature_dependency": "flag.device_power",
                    "feature_flag": "flag.device_power",
                    "feature_flag_value": 1,
                    "applicability_state": "REQUIRES_BUILD_CONFIGURATION_EVIDENCE",
                    "accepted_platform_release": "37",
                    "protection_base": "signature",
                    "protection_modifiers": "role|module",
                    "compatibility_protection_expression": "signature|role|module",
                },
            ]
        if sql == PERMISSION_FLAGS_SQL:
            raise AssertionError("conditional branches must not use selected-scalar flags")
        return []

    fact = PermissionIntelV1Adapter(query).get_permission(
        "android.permission.DEVICE_POWER"
    )
    assert fact is not None
    assert fact.protection.compatibility_expression is None
    assert fact.flags == ()
    assert len(fact.alternatives) == 2
    assert {alternative.protection.compatibility_expression for alternative in fact.alternatives} == {
        "signature|role",
        "signature|role|module",
    }


def test_duplicate_or_unsupported_interpretation_fails_closed() -> None:
    def duplicate(sql: str, params: Sequence[object]) -> Sequence[Mapping[str, Any]]:
        if sql == PERMISSION_LOOKUP_SQL:
            return [_permission_row(), _permission_row()]
        return []

    with pytest.raises(ValueError, match="duplicate identity"):
        PermissionIntelV1Adapter(duplicate).get_permission("android.permission.CAMERA")

    def unsupported(sql: str, params: Sequence[object]) -> Sequence[Mapping[str, Any]]:
        if sql == PERMISSION_LOOKUP_SQL:
            return [_permission_row(interpretation_contract_version="2.0.0")]
        return []

    with pytest.raises(ValueError, match="interpretation contract"):
        PermissionIntelV1Adapter(unsupported).get_permission("android.permission.CAMERA")
