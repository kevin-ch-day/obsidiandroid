from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidiandroid.database.permission_intel_v1.models import (
    AuthorityClass,
    CatalogGateDecision,
    CatalogGateState,
    ComparisonState,
    PlatformPermissionFact,
    ProtectionSemantics,
    ShadowMode,
)
from obsidiandroid.database.permission_intel_v1.parity import (
    LegacyPlatformFact,
    ParityReport,
    compare_permission,
)
from obsidiandroid.database.permission_intel_v1.shadow import (
    PermissionIntelV1Shadow,
    configured_shadow_mode,
)


def _v1_fact(**overrides: object) -> PlatformPermissionFact:
    values: dict[str, object] = {
        "canonical_permission": "android.permission.CAMERA",
        "symbolic_name": "CAMERA",
        "namespace": "android.permission",
        "defining_package": "android",
        "authority_class": AuthorityClass.AOSP_PUBLIC,
        "lifecycle": "declared_in_accepted_release",
        "visibility": "public",
        "platform_release": None,
        "sdk_extension_release_id": None,
        "source_snapshot_id": "aosp",
        "source_provenance_status": "PRESENT",
        "public_manifest_exposed": True,
        "public_health_exposed": False,
        "health_module_declared": False,
        "protection": ProtectionSemantics(
            "dangerous", ("instant",), "dangerous|instant", "dangerous|instant"
        ),
        "flags": (),
        "catalog_release_id": "android-17-r1-audit-2026-08-30-source-identity-correction-1",
        "catalog_digest": "a" * 64,
    }
    values.update(overrides)
    return PlatformPermissionFact(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("raw", "base", "modifiers"),
    [
        ("dangerous", "dangerous", ()),
        ("dangerous|instant", "dangerous", ("instant",)),
        ("dangerous|runtime|instant", "dangerous", ("runtime", "instant")),
        ("signature|module", "signature", ("module",)),
        ("signature|privileged", "signature", ("privileged",)),
        ("normal|appop", "normal", ("appop",)),
        ("internal|privileged", "internal", ("privileged",)),
    ],
)
def test_complete_protection_semantics(
    raw: str, base: str, modifiers: tuple[str, ...]
) -> None:
    parsed = ProtectionSemantics.from_legacy_text(raw)
    assert parsed.base == base
    assert parsed.modifiers == modifiers
    assert parsed.compatibility_expression == raw


def test_unknown_protection_token_remains_explicit() -> None:
    parsed = ProtectionSemantics.from_legacy_text("signature|invented")
    assert parsed.base == "signature"
    assert parsed.unresolved_tokens == ("invented",)


def test_all_modifiers_are_serialized_without_loss() -> None:
    modifiers = ("module", "privileged", "knownSigner")
    assert (
        ProtectionSemantics.serialize("signature", modifiers)
        == "signature|module|privileged|knownSigner"
    )


def test_v1_metadata_addition_is_not_regression() -> None:
    legacy = LegacyPlatformFact.from_mapping(
        {
            "constant_value": "android.permission.CAMERA",
            "classification": "AOSP",
            "protection_level": "dangerous|instant",
        }
    )
    comparison = compare_permission(legacy, _v1_fact())
    assert comparison.state is ComparisonState.V1_ADDS_METADATA
    assert comparison.field_differences == ()


def test_legacy_non_expressiveness_is_not_v1_failure() -> None:
    legacy = LegacyPlatformFact.from_mapping(
        {
            "constant_value": "android.permission.CAMERA",
            "classification": "AOSP",
            "protection_level": "dangerous|legacyUnknownToken",
        }
    )
    comparison = compare_permission(
        legacy,
        _v1_fact(
            protection=ProtectionSemantics("dangerous", (), "dangerous", "dangerous")
        ),
    )
    assert comparison.state is ComparisonState.LEGACY_NOT_EXPRESSIVE
    assert (
        comparison.field_differences[0].field == "legacy_unresolved_protection_tokens"
    )


@pytest.mark.parametrize(
    ("field", "value", "state"),
    [
        (
            "authority_class",
            AuthorityClass.OEM_OR_VENDOR,
            ComparisonState.AUTHORITY_DIFFERENCE,
        ),
        (
            "protection",
            ProtectionSemantics("signature", ("instant",), "signature|instant", None),
            ComparisonState.PROTECTION_BASE_DIFFERENCE,
        ),
        (
            "protection",
            ProtectionSemantics("dangerous", ("runtime",), "dangerous|runtime", None),
            ComparisonState.PROTECTION_MODIFIER_DIFFERENCE,
        ),
        ("lifecycle", "removed", ComparisonState.LIFECYCLE_DIFFERENCE),
    ],
)
def test_difference_classification(
    field: str, value: object, state: ComparisonState
) -> None:
    legacy = LegacyPlatformFact(
        canonical_permission="android.permission.CAMERA",
        authority_class=AuthorityClass.AOSP_PUBLIC,
        lifecycle="declared_in_accepted_release",
        visibility=None,
        defining_package=None,
        protection=ProtectionSemantics(
            "dangerous", ("instant",), "dangerous|instant", "dangerous|instant"
        ),
    )
    values = legacy.__dict__ | {field: value}
    changed = LegacyPlatformFact(**values)
    assert compare_permission(changed, _v1_fact()).state is state


class _NoCallAdapter:
    def read_catalog_gate(self) -> CatalogGateDecision:
        raise AssertionError("gate must not run")

    def get_permission(
        self, canonical_permission: str
    ) -> PlatformPermissionFact | None:
        raise AssertionError("v1 lookup must not run")


def test_shadow_disabled_by_default_and_legacy_identity_is_preserved(
    monkeypatch,
) -> None:
    monkeypatch.delenv("OBSIDIANDROID_PERMISSION_INTEL_V1_SHADOW_MODE", raising=False)
    legacy = {"constant_value": "android.permission.CAMERA", "score": 7}
    result = PermissionIntelV1Shadow(_NoCallAdapter()).lookup(
        "android.permission.CAMERA", legacy
    )
    assert result.authoritative_legacy_value is legacy
    assert result.diagnostic.mode is ShadowMode.LEGACY_ONLY


class _Adapter:
    def __init__(self, available: bool = True, fail: bool = False) -> None:
        self.available = available
        self.fail = fail

    def read_catalog_gate(self) -> CatalogGateDecision:
        if self.fail:
            raise RuntimeError("no secret detail")
        return CatalogGateDecision(
            CatalogGateState.COMPATIBLE_INCOMPLETE_SCOPE
            if self.available
            else CatalogGateState.CATALOG_MISSING,
            self.available,
            ("test_gate",),
            None,
        )

    def get_permission(
        self, canonical_permission: str
    ) -> PlatformPermissionFact | None:
        return _v1_fact(canonical_permission=canonical_permission)


def test_shadow_success_never_replaces_legacy() -> None:
    legacy = {"constant_value": "android.permission.CAMERA", "classification": "AOSP"}
    result = PermissionIntelV1Shadow(
        _Adapter(),
        mode=ShadowMode.LEGACY_WITH_V1_SHADOW,  # type: ignore[arg-type]
    ).lookup("android.permission.CAMERA", legacy)
    assert result.authoritative_legacy_value is legacy
    assert result.diagnostic.comparison is not None


@pytest.mark.parametrize("adapter", [_Adapter(available=False), _Adapter(fail=True)])
def test_shadow_gate_or_adapter_failure_never_replaces_legacy(
    adapter: _Adapter,
) -> None:
    legacy = {"constant_value": "android.permission.CAMERA"}
    result = PermissionIntelV1Shadow(
        adapter,
        mode=ShadowMode.LEGACY_WITH_V1_SHADOW,  # type: ignore[arg-type]
    ).lookup("android.permission.CAMERA", legacy)
    assert result.authoritative_legacy_value is legacy
    assert result.diagnostic.mode is ShadowMode.V1_UNAVAILABLE_LEGACY_ACTIVE


def test_diagnostic_state_cannot_be_configured() -> None:
    with pytest.raises(ValueError, match="diagnostic-only"):
        configured_shadow_mode("V1_UNAVAILABLE_LEGACY_ACTIVE")


def test_parity_output_is_deterministic_and_timestamp_free(tmp_path: Path) -> None:
    comparison = compare_permission(
        LegacyPlatformFact.from_mapping(
            {
                "constant_value": "android.permission.CAMERA",
                "classification": "AOSP",
                "protection_level": "dangerous|instant",
            }
        ),
        _v1_fact(),
    )
    report = ParityReport(
        obsidiandroid_commit="b65d78993c417d1390062098f0b4e110d65bc224",
        schema_contract_version="1.0.0-draft",
        catalog_release_id="android-17-r1-audit-2026-08-30-source-identity-correction-1",
        source_scope_status="INCOMPLETE_EXPLICIT",
        gate_state="COMPATIBLE_INCOMPLETE_SCOPE",
        test_environment_identity="rootless-network-none-mariadb-11.8",
        comparisons=(comparison,),
    )
    first_json, first_md = report.write(tmp_path / "first.json", tmp_path / "first.md")
    second_json, second_md = report.write(
        tmp_path / "second.json", tmp_path / "second.md"
    )
    assert first_json.read_bytes() == second_json.read_bytes()
    assert first_md.read_bytes() == second_md.read_bytes()
    payload = json.loads(first_json.read_text())
    assert payload["evidence_class"] == "disposable_integration_evidence"
    assert "timestamp" not in first_json.read_text().lower()
    assert len(payload["semantic_digest"]) == 64
