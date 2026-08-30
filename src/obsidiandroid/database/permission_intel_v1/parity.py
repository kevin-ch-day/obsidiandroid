"""Deterministic legacy-to-v1 platform-fact parity reporting."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .models import (
    PINNED_CATALOG_DIGEST,
    PINNED_CATALOG_PLAN_DIGEST,
    PINNED_MIGRATION_SET_DIGEST,
    PINNED_SHARED_COMMIT,
    AuthorityClass,
    ComparisonState,
    PlatformPermissionFact,
    ProtectionSemantics,
)

QUERY_INVENTORY_VERSION = "permission-intel-v1-query-inventory-1"
EVIDENCE_CLASS = "disposable_integration_evidence"


@dataclass(frozen=True)
class LegacyPlatformFact:
    """Legacy-shaped platform fact normalized only for shadow comparison."""

    canonical_permission: str
    authority_class: AuthorityClass
    lifecycle: str | None
    visibility: str | None
    defining_package: str | None
    protection: ProtectionSemantics
    flags: tuple[str, ...] = ()
    added_platform_release: str | None = None
    provenance_status: str | None = None

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> LegacyPlatformFact:
        """Normalize common legacy dictionary fields without claiming absent metadata."""
        canonical = str(
            row.get("canonical_permission")
            or row.get("constant_value")
            or row.get("permission_string")
            or ""
        ).strip()
        return cls(
            canonical_permission=canonical,
            authority_class=AuthorityClass.from_value(
                row.get("authority_class")
                or row.get("classification")
                or row.get("source_family")
            ),
            lifecycle=_optional_text(row.get("lifecycle")),
            visibility=_optional_text(row.get("visibility")),
            defining_package=_optional_text(row.get("defining_package")),
            protection=ProtectionSemantics.from_legacy_text(
                row.get("protection_level")
                or row.get("compatibility_protection_expression")
            ),
            flags=tuple(str(value) for value in (row.get("flags") or ())),
            added_platform_release=_optional_text(
                row.get("added_platform_release") or row.get("added_in_api_level")
            ),
            provenance_status=_optional_text(row.get("provenance_status")),
        )


@dataclass(frozen=True)
class FieldDifference:
    field: str
    legacy: object
    v1: object


@dataclass(frozen=True)
class PermissionComparison:
    canonical_permission: str
    state: ComparisonState
    field_differences: tuple[FieldDifference, ...]


def compare_permission(
    legacy: LegacyPlatformFact | None,
    v1: PlatformPermissionFact | None,
) -> PermissionComparison:
    """Compare expressible fields while treating v1-only metadata as an addition."""
    if legacy is None and v1 is None:
        return PermissionComparison("", ComparisonState.ERROR, ())
    if legacy is None:
        assert v1 is not None
        return PermissionComparison(
            v1.canonical_permission, ComparisonState.V1_ONLY, ()
        )
    if v1 is None:
        return PermissionComparison(
            legacy.canonical_permission, ComparisonState.LEGACY_ONLY, ()
        )

    if legacy.protection.unresolved_tokens and not v1.protection.unresolved_tokens:
        return PermissionComparison(
            legacy.canonical_permission,
            ComparisonState.LEGACY_NOT_EXPRESSIVE,
            (
                FieldDifference(
                    "legacy_unresolved_protection_tokens",
                    list(legacy.protection.unresolved_tokens),
                    [],
                ),
            ),
        )

    differences: list[FieldDifference] = []
    if legacy.authority_class != v1.authority_class:
        differences.append(
            FieldDifference(
                "authority_class",
                legacy.authority_class.value,
                v1.authority_class.value,
            )
        )
    if legacy.protection.base != v1.protection.base:
        differences.append(
            FieldDifference(
                "protection_base", legacy.protection.base, v1.protection.base
            )
        )
    if legacy.protection.modifiers != v1.protection.modifiers:
        differences.append(
            FieldDifference(
                "protection_modifiers",
                list(legacy.protection.modifiers),
                list(v1.protection.modifiers),
            )
        )
    if legacy.lifecycle is not None and legacy.lifecycle != v1.lifecycle:
        differences.append(FieldDifference("lifecycle", legacy.lifecycle, v1.lifecycle))
    if (
        legacy.provenance_status is not None
        and legacy.provenance_status != v1.source_provenance_status
    ):
        differences.append(
            FieldDifference(
                "provenance_status",
                legacy.provenance_status,
                v1.source_provenance_status,
            )
        )

    state = _comparison_state(differences)
    if not differences and _v1_adds_metadata(legacy, v1):
        state = ComparisonState.V1_ADDS_METADATA
    return PermissionComparison(legacy.canonical_permission, state, tuple(differences))


def _comparison_state(differences: Sequence[FieldDifference]) -> ComparisonState:
    fields = {difference.field for difference in differences}
    if "authority_class" in fields:
        return ComparisonState.AUTHORITY_DIFFERENCE
    if "protection_base" in fields:
        return ComparisonState.PROTECTION_BASE_DIFFERENCE
    if "protection_modifiers" in fields:
        return ComparisonState.PROTECTION_MODIFIER_DIFFERENCE
    if "lifecycle" in fields:
        return ComparisonState.LIFECYCLE_DIFFERENCE
    if "provenance_status" in fields:
        return ComparisonState.PROVENANCE_DIFFERENCE
    return ComparisonState.EQUIVALENT


def _v1_adds_metadata(legacy: LegacyPlatformFact, v1: PlatformPermissionFact) -> bool:
    return any(
        (
            legacy.visibility is None and v1.visibility is not None,
            legacy.defining_package is None and v1.defining_package is not None,
            legacy.added_platform_release is None and v1.platform_release is not None,
            legacy.provenance_status is None
            and v1.source_provenance_status is not None,
            not legacy.flags and bool(v1.flags),
            v1.sdk_extension_release_id is not None,
        )
    )


@dataclass(frozen=True)
class ParityReport:
    """Canonical, timestamp-free parity evidence."""

    obsidiandroid_commit: str
    schema_contract_version: str
    catalog_release_id: str
    source_scope_status: str
    gate_state: str
    test_environment_identity: str
    comparisons: tuple[PermissionComparison, ...]
    unsupported_queries: tuple[str, ...] = ()
    dynamic_sql_not_covered: tuple[str, ...] = ()
    adapter_errors: tuple[str, ...] = ()

    def semantic_payload(self) -> dict[str, Any]:
        """Return stable evidence with no wall-clock or connection identity."""
        ordered = sorted(self.comparisons, key=lambda item: item.canonical_permission)
        counts: dict[str, int] = {}
        for item in ordered:
            counts[item.state.value] = counts.get(item.state.value, 0) + 1
        return {
            "evidence_class": EVIDENCE_CLASS,
            "pinned_shared_commit": PINNED_SHARED_COMMIT,
            "migration_set_digest": PINNED_MIGRATION_SET_DIGEST,
            "catalog_content_digest": PINNED_CATALOG_DIGEST,
            "catalog_plan_digest": PINNED_CATALOG_PLAN_DIGEST,
            "obsidiandroid_commit": self.obsidiandroid_commit,
            "schema_contract_version": self.schema_contract_version,
            "catalog_release_id": self.catalog_release_id,
            "source_scope_status": self.source_scope_status,
            "query_inventory_version": QUERY_INVENTORY_VERSION,
            "compared_permission_count": len(ordered),
            "comparison_state_counts": dict(sorted(counts.items())),
            "comparisons": [_comparison_payload(item) for item in ordered],
            "unsupported_queries": sorted(self.unsupported_queries),
            "dynamic_sql_not_covered": sorted(self.dynamic_sql_not_covered),
            "adapter_errors": sorted(self.adapter_errors),
            "gate_state": self.gate_state,
            "test_environment_identity": self.test_environment_identity,
        }

    def semantic_digest(self) -> str:
        """Return SHA-256 over canonical semantic JSON."""
        return hashlib.sha256(
            _canonical_json(self.semantic_payload()).encode("utf-8")
        ).hexdigest()

    def write(self, json_path: Path, markdown_path: Path) -> tuple[Path, Path]:
        """Write deterministic JSON and Markdown evidence to caller-selected paths."""
        payload = self.semantic_payload()
        payload["semantic_digest"] = self.semantic_digest()
        json_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(_canonical_json(payload) + "\n", encoding="utf-8")
        markdown_path.write_text(_markdown(payload), encoding="utf-8")
        return json_path, markdown_path


def _comparison_payload(item: PermissionComparison) -> dict[str, Any]:
    return {
        "canonical_permission": item.canonical_permission,
        "state": item.state.value,
        "field_differences": [
            asdict(difference) for difference in item.field_differences
        ],
    }


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def _markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Permission Intel v1 Shadow Parity",
        "",
        f"Evidence class: `{payload['evidence_class']}`",
        f"Gate state: `{payload['gate_state']}`",
        f"Compared permissions: {payload['compared_permission_count']}",
        f"Semantic digest: `{payload['semantic_digest']}`",
        "",
        "## Classification Counts",
        "",
    ]
    counts = payload["comparison_state_counts"]
    lines.extend(f"- `{key}`: {counts[key]}" for key in sorted(counts))
    lines.extend(["", "## Permission Results", ""])
    for item in payload["comparisons"]:
        lines.append(f"- `{item['canonical_permission']}`: `{item['state']}`")
        for difference in item["field_differences"]:
            lines.append(
                f"  - `{difference['field']}`: legacy={difference['legacy']!r}; "
                f"v1={difference['v1']!r}"
            )
    lines.extend(["", "## Unsupported and Errors", ""])
    lines.append(f"- Unsupported queries: {len(payload['unsupported_queries'])}")
    lines.append(
        f"- Dynamic SQL not covered: {len(payload['dynamic_sql_not_covered'])}"
    )
    lines.append(f"- Adapter errors: {len(payload['adapter_errors'])}")
    return "\n".join(lines) + "\n"


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
