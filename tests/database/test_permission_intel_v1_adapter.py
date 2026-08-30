from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from obsidiandroid.database.permission_intel_v1.adapter import (
    CATALOG_STATUS_SQL,
    PERMISSION_FLAGS_SQL,
    PERMISSION_LOOKUP_SQL,
    SOURCE_EVIDENCE_SQL,
    SPLIT_PERMISSION_SQL,
    PermissionIntelV1Adapter,
)
from obsidiandroid.database.permission_intel_v1.models import AuthorityClass


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
        if sql == PERMISSION_FLAGS_SQL:
            return [
                {"normalized_flag": "hardRestricted"},
                {"normalized_flag": "softRestricted"},
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
        "catalog_release_id": "android-17-r1-audit-2026-08-30-source-identity-correction-1",
        "catalog_digest": "a" * 64,
        "canonical_permission": "android.permission.CAMERA",
        "symbolic_name": "CAMERA",
        "namespace": "android.permission",
        "defining_package": "android",
        "authority_class": "AOSP_PUBLIC",
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
    assert query.calls[0] == (PERMISSION_LOOKUP_SQL, ("android.permission.CAMERA",))
    assert "%s" in query.calls[0][0]


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


def test_empty_permission_is_rejected_before_query() -> None:
    query = FakeQuery()
    with pytest.raises(ValueError):
        PermissionIntelV1Adapter(query).get_permission(" ")
    assert query.calls == []


def test_unknown_source_flag_fails_closed() -> None:
    def bad_flags(sql: str, params: Sequence[object]) -> Sequence[Mapping[str, Any]]:
        if sql == PERMISSION_LOOKUP_SQL:
            return [_permission_row()]
        if sql == PERMISSION_FLAGS_SQL:
            return [{"normalized_flag": "inventedFlag"}]
        return []

    with pytest.raises(ValueError, match="unrecognized v1 permission flags"):
        PermissionIntelV1Adapter(bad_flags).get_permission("android.permission.CAMERA")
