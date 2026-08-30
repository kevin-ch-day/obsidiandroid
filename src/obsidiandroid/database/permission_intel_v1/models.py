"""Typed models for the read-only Permission Intel v1 shadow contract."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

PINNED_SHARED_COMMIT = "54b23b581939184e8dd8668e38837ca1cd15013d"
PINNED_MIGRATION_SET_DIGEST = (
    "1bec1edabf99fbebffc9737e8b5d14076d3566b963c4878c9b3361bbe269ed5c"
)
PINNED_CATALOG_DIGEST = (
    "075accc8aa2042d0d9454ba12e8625b87e76fe54366532c6bca21d56066fc334"
)
PINNED_CATALOG_PLAN_DIGEST = (
    "aae4c1b48f043e58293884183235f344d8ab0e7e18cfd2362b99725227234cca"
)
PINNED_SCHEMA_CONTRACT_ID = "org.android-permission-intel.schema-v1-draft"
PINNED_SCHEMA_CONTRACT_VERSION = "1.0.0-draft"
PINNED_CATALOG_RELEASE_ID = (
    "android-17-r1-audit-2026-08-30-source-identity-correction-1"
)

# Complete source-derived vocabularies from the pinned catalog plan. Keeping these
# small contract values local avoids a runtime Python dependency on the shared repo.
PROTECTION_BASE_VOCABULARY = frozenset(
    {"dangerous", "internal", "normal", "signature", "signatureOrSystem"}
)
PROTECTION_MODIFIER_VOCABULARY = (
    "appPredictor",
    "appop",
    "companion",
    "configurator",
    "development",
    "incidentReportApprover",
    "installer",
    "instant",
    "knownSigner",
    "module",
    "oem",
    "pre23",
    "preinstalled",
    "privileged",
    "recents",
    "retailDemo",
    "role",
    "runtime",
    "setup",
    "system",
    "textClassifier",
    "vendorPrivileged",
    "verifier",
)
PROTECTION_MODIFIER_SET = frozenset(PROTECTION_MODIFIER_VOCABULARY)
PERMISSION_FLAG_VOCABULARY = frozenset(
    {
        "allowedInPrivateComputeCore",
        "costsMoney",
        "hardRestricted",
        "immutablyRestricted",
        "removed",
        "softRestricted",
    }
)

_API_VERSION_RE = re.compile(r"^(0|[1-9]\d*)(?:\.(0|[1-9]\d*))?$")


@dataclass(frozen=True, order=True)
class ApiVersion:
    """Android full API version represented without floating-point conversion."""

    major: int
    minor: int
    full: str

    @classmethod
    def parse(cls, raw: object) -> ApiVersion:
        """Parse a full API string such as ``37.2`` without using a float."""
        if not isinstance(raw, str):
            raise TypeError("full API version must be a string")
        match = _API_VERSION_RE.fullmatch(raw)
        if match is None:
            raise ValueError(f"malformed full API version: {raw!r}")
        return cls(int(match.group(1)), int(match.group(2) or 0), raw)


class AuthorityClass(str, Enum):
    """Authority classes understood by the shadow adapter."""

    AOSP_PUBLIC = "AOSP_PUBLIC"
    AOSP_HIDDEN = "AOSP_HIDDEN"
    AOSP_INTERNAL = "AOSP_INTERNAL"
    AOSP_MODULE = "AOSP_MODULE"
    GOOGLE_OR_GMS = "GOOGLE_OR_GMS"
    OEM_OR_VENDOR = "OEM_OR_VENDOR"
    APPLICATION_DEFINED = "APPLICATION_DEFINED"
    PROVISIONAL = "PROVISIONAL"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_value(cls, raw: object) -> AuthorityClass:
        """Map only explicit authority values; never infer ownership from a prefix."""
        text = str(raw or "").strip().upper()
        aliases = {
            "AOSP": cls.AOSP_PUBLIC,
            "GOOGLE": cls.GOOGLE_OR_GMS,
            "GMS": cls.GOOGLE_OR_GMS,
            "OEM": cls.OEM_OR_VENDOR,
            "VENDOR": cls.OEM_OR_VENDOR,
            "APP_DEFINED": cls.APPLICATION_DEFINED,
        }
        if text in aliases:
            return aliases[text]
        try:
            return cls(text)
        except ValueError:
            return cls.UNKNOWN


class CatalogGateState(str, Enum):
    """Explicit outcomes for the v1 minimum-version gate."""

    COMPATIBLE_CURRENT = "COMPATIBLE_CURRENT"
    COMPATIBLE_STALE_CONTENT = "COMPATIBLE_STALE_CONTENT"
    COMPATIBLE_INCOMPLETE_SCOPE = "COMPATIBLE_INCOMPLETE_SCOPE"
    SCHEMA_TOO_OLD = "SCHEMA_TOO_OLD"
    SCHEMA_TOO_NEW = "SCHEMA_TOO_NEW"
    CATALOG_NOT_ACCEPTED = "CATALOG_NOT_ACCEPTED"
    CATALOG_MISSING = "CATALOG_MISSING"
    EXPLICIT_DEGRADED_MODE_REQUIRED = "EXPLICIT_DEGRADED_MODE_REQUIRED"


class ShadowMode(str, Enum):
    """Permitted shadow states; v1-authoritative mode intentionally does not exist."""

    LEGACY_ONLY = "LEGACY_ONLY"
    LEGACY_WITH_V1_SHADOW = "LEGACY_WITH_V1_SHADOW"
    V1_UNAVAILABLE_LEGACY_ACTIVE = "V1_UNAVAILABLE_LEGACY_ACTIVE"


class ComparisonState(str, Enum):
    """Permission parity classifications."""

    EQUIVALENT = "EQUIVALENT"
    V1_ADDS_METADATA = "V1_ADDS_METADATA"
    LEGACY_ONLY = "LEGACY_ONLY"
    V1_ONLY = "V1_ONLY"
    PROTECTION_BASE_DIFFERENCE = "PROTECTION_BASE_DIFFERENCE"
    PROTECTION_MODIFIER_DIFFERENCE = "PROTECTION_MODIFIER_DIFFERENCE"
    AUTHORITY_DIFFERENCE = "AUTHORITY_DIFFERENCE"
    LIFECYCLE_DIFFERENCE = "LIFECYCLE_DIFFERENCE"
    PROVENANCE_DIFFERENCE = "PROVENANCE_DIFFERENCE"
    LEGACY_NOT_EXPRESSIVE = "LEGACY_NOT_EXPRESSIVE"
    UNSUPPORTED_QUERY = "UNSUPPORTED_QUERY"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ProtectionSemantics:
    """Normalized protection information with every modifier preserved."""

    base: str | None
    modifiers: tuple[str, ...]
    compatibility_expression: str | None
    raw_expression: str | None
    unresolved_tokens: tuple[str, ...] = ()

    @classmethod
    def from_v1_row(cls, row: Mapping[str, Any]) -> ProtectionSemantics:
        """Build protection semantics from the pinned v1 view columns."""
        base = _optional_text(row.get("protection_base"))
        raw_modifiers = _optional_text(row.get("protection_modifiers"))
        modifiers = tuple(part for part in (raw_modifiers or "").split("|") if part)
        unresolved = tuple(
            token
            for token in ((base,) if base else ()) + modifiers
            if token not in PROTECTION_BASE_VOCABULARY
            and token not in PROTECTION_MODIFIER_SET
        )
        return cls(
            base=base,
            modifiers=modifiers,
            compatibility_expression=_optional_text(
                row.get("compatibility_protection_expression")
            ),
            raw_expression=_optional_text(row.get("raw_protection_expression")),
            unresolved_tokens=unresolved,
        )

    @classmethod
    def from_legacy_text(cls, raw: object) -> ProtectionSemantics:
        """Parse a legacy compatibility expression using the complete pinned vocabulary."""
        text = _optional_text(raw)
        if text is None:
            return cls(None, (), None, None)
        tokens = tuple(
            part.strip() for part in text.replace(",", "|").split("|") if part.strip()
        )
        bases = tuple(token for token in tokens if token in PROTECTION_BASE_VOCABULARY)
        base = bases[0] if len(bases) == 1 else None
        modifiers = tuple(token for token in tokens if token in PROTECTION_MODIFIER_SET)
        unresolved = tuple(
            token
            for token in tokens
            if token not in PROTECTION_BASE_VOCABULARY
            and token not in PROTECTION_MODIFIER_SET
        )
        return cls(base, modifiers, cls.serialize(base, modifiers), text, unresolved)

    @staticmethod
    def serialize(base: str | None, modifiers: tuple[str, ...]) -> str | None:
        """Serialize base first, retaining all modifiers in their supplied stable order."""
        tokens = ((base,) if base else ()) + modifiers
        return "|".join(tokens) if tokens else None


@dataclass(frozen=True)
class CatalogStatus:
    """One row from ``android_permission_v1_catalog_release``."""

    schema_contract_id: str
    schema_contract_version: str
    compatibility_floor: str
    schema_contract_release_status: str
    catalog_release_id: str
    catalog_digest: str
    source_set_id: str
    source_set_digest: str
    platform_release_coverage: str
    scope_completeness_statement: str
    exhaustive_scope: bool
    catalog_release_status: str
    catalog_import_status: str
    import_receipt_count: int
    parser_package_version: str
    notes_and_limitations: str

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> CatalogStatus:
        """Parse a database row without exposing connection information."""
        return cls(
            schema_contract_id=str(row.get("schema_contract_id") or ""),
            schema_contract_version=str(row.get("schema_contract_version") or ""),
            compatibility_floor=str(row.get("compatibility_floor") or ""),
            schema_contract_release_status=str(
                row.get("schema_contract_release_status") or ""
            ),
            catalog_release_id=str(row.get("catalog_release_id") or ""),
            catalog_digest=str(row.get("catalog_digest") or ""),
            source_set_id=str(row.get("source_set_id") or ""),
            source_set_digest=str(row.get("source_set_digest") or ""),
            platform_release_coverage=str(row.get("platform_release_coverage") or ""),
            scope_completeness_statement=str(
                row.get("scope_completeness_statement") or ""
            ),
            exhaustive_scope=bool(row.get("exhaustive_scope")),
            catalog_release_status=str(row.get("catalog_release_status") or ""),
            catalog_import_status=str(row.get("catalog_import_status") or ""),
            import_receipt_count=int(row.get("import_receipt_count") or 0),
            parser_package_version=str(row.get("parser_package_version") or ""),
            notes_and_limitations=str(row.get("notes_and_limitations") or ""),
        )


@dataclass(frozen=True)
class CatalogGateDecision:
    """Minimum-version decision and credential-free diagnostics."""

    state: CatalogGateState
    shadow_available: bool
    diagnostic_codes: tuple[str, ...]
    catalog_status: CatalogStatus | None


@dataclass(frozen=True)
class PlatformPermissionFact:
    """Canonical platform-reference result returned by the v1 adapter."""

    canonical_permission: str
    symbolic_name: str | None
    namespace: str | None
    defining_package: str | None
    authority_class: AuthorityClass
    lifecycle: str | None
    visibility: str | None
    platform_release: ApiVersion | None
    sdk_extension_release_id: str | None
    source_snapshot_id: str | None
    source_provenance_status: str | None
    public_manifest_exposed: bool
    public_health_exposed: bool
    health_module_declared: bool
    protection: ProtectionSemantics
    flags: tuple[str, ...]
    catalog_release_id: str
    catalog_digest: str


@dataclass(frozen=True)
class SplitPermissionFact:
    """One accepted split-permission target relation."""

    source_permission: str
    target_permission: str
    target_sdk_threshold: int
    target_ordinal: int
    platform_release_id: str
    source_snapshot_id: str


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
