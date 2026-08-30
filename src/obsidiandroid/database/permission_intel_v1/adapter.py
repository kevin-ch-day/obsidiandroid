"""Focused SELECT-only adapter for Permission Intel v1 platform facts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from .gate import CATALOG_STATUS_SQL, evaluate_catalog_gate
from .models import (
    PERMISSION_FLAG_VOCABULARY,
    ApiVersion,
    AuthorityClass,
    CatalogGateDecision,
    PlatformPermissionFact,
    ProtectionSemantics,
    SplitPermissionFact,
)


class ReadQuery(Protocol):
    """Injected read executor used by production and disposable test paths."""

    def __call__(
        self, sql: str, params: Sequence[object]
    ) -> Sequence[Mapping[str, Any]]: ...


PERMISSION_LOOKUP_SQL = """
SELECT
    p.catalog_release_id,
    p.catalog_digest,
    p.canonical_permission,
    p.symbolic_name,
    p.namespace,
    p.defining_package,
    p.authority_class,
    p.lifecycle,
    p.visibility,
    p.accepted_platform_release,
    p.sdk_extension_release_id,
    p.source_snapshot_id,
    p.source_provenance_status,
    p.public_manifest_exposed,
    p.public_health_exposed,
    p.health_module_declared,
    protection.protection_base,
    protection.protection_modifiers,
    protection.compatibility_protection_expression,
    protection.raw_protection_expression
FROM android_permission_v1_obsidiandroid_permission AS consumer
JOIN android_permission_v1_current_permission AS p
  ON p.catalog_release_id = consumer.catalog_release_id
 AND p.canonical_permission = consumer.canonical_permission
LEFT JOIN android_permission_v1_current_protection AS protection
  ON protection.catalog_release_id = p.catalog_release_id
 AND protection.permission_id = p.permission_id
WHERE BINARY p.canonical_permission = BINARY %s
ORDER BY p.declaration_revision_id DESC
LIMIT 1
""".strip()

PERMISSION_FLAGS_SQL = """
SELECT normalized_flag
FROM android_permission_v1_current_flag
WHERE BINARY canonical_permission = BINARY %s
ORDER BY normalized_flag
""".strip()

SPLIT_PERMISSION_SQL = """
SELECT
    source_permission,
    target_permission,
    target_sdk_threshold,
    target_ordinal,
    platform_release_id,
    source_snapshot_id
FROM android_permission_v1_split_permission
WHERE BINARY source_permission = BINARY %s
ORDER BY target_sdk_threshold, target_ordinal, target_permission
""".strip()

SOURCE_EVIDENCE_SQL = """
SELECT fact_type, fact_digest, source_snapshot_id, source_path, source_locator,
       parser_version, evidence_digest
FROM android_permission_v1_source_evidence
WHERE BINARY canonical_permission = BINARY %s
ORDER BY fact_type, source_snapshot_id, source_path, source_locator
""".strip()

EXECUTABLE_SELECTS = (
    CATALOG_STATUS_SQL,
    PERMISSION_LOOKUP_SQL,
    PERMISSION_FLAGS_SQL,
    SPLIT_PERMISSION_SQL,
    SOURCE_EVIDENCE_SQL,
)


class PermissionIntelV1Adapter:
    """Read catalog metadata and canonical platform facts through versioned views."""

    def __init__(self, query: ReadQuery | None = None) -> None:
        self._query = query or _default_query

    def read_catalog_gate(self) -> CatalogGateDecision:
        """Read and evaluate the pinned minimum-version gate."""
        return evaluate_catalog_gate(self._query(CATALOG_STATUS_SQL, ()))

    def get_permission(
        self, canonical_permission: str
    ) -> PlatformPermissionFact | None:
        """Look up one permission using case-sensitive, parameterized identity matching."""
        permission = _validate_permission_parameter(canonical_permission)
        rows = self._query(PERMISSION_LOOKUP_SQL, (permission,))
        if not rows:
            return None
        row = rows[0]
        flag_rows = self._query(PERMISSION_FLAGS_SQL, (permission,))
        flags = tuple(str(item.get("normalized_flag") or "") for item in flag_rows)
        unknown_flags = tuple(
            flag for flag in flags if flag not in PERMISSION_FLAG_VOCABULARY
        )
        if unknown_flags:
            raise ValueError(
                f"unrecognized v1 permission flags: {', '.join(unknown_flags)}"
            )
        platform_raw = row.get("accepted_platform_release")
        platform_release = (
            ApiVersion.parse(platform_raw) if platform_raw is not None else None
        )
        return PlatformPermissionFact(
            canonical_permission=str(row.get("canonical_permission") or ""),
            symbolic_name=_optional_text(row.get("symbolic_name")),
            namespace=_optional_text(row.get("namespace")),
            defining_package=_optional_text(row.get("defining_package")),
            authority_class=AuthorityClass.from_value(row.get("authority_class")),
            lifecycle=_optional_text(row.get("lifecycle")),
            visibility=_optional_text(row.get("visibility")),
            platform_release=platform_release,
            sdk_extension_release_id=_optional_text(
                row.get("sdk_extension_release_id")
            ),
            source_snapshot_id=_optional_text(row.get("source_snapshot_id")),
            source_provenance_status=_optional_text(
                row.get("source_provenance_status")
            ),
            public_manifest_exposed=bool(row.get("public_manifest_exposed")),
            public_health_exposed=bool(row.get("public_health_exposed")),
            health_module_declared=bool(row.get("health_module_declared")),
            protection=ProtectionSemantics.from_v1_row(row),
            flags=flags,
            catalog_release_id=str(row.get("catalog_release_id") or ""),
            catalog_digest=str(row.get("catalog_digest") or ""),
        )

    def get_split_relations(
        self, canonical_permission: str
    ) -> tuple[SplitPermissionFact, ...]:
        """Return accepted split targets for one case-sensitive source permission."""
        permission = _validate_permission_parameter(canonical_permission)
        rows = self._query(SPLIT_PERMISSION_SQL, (permission,))
        return tuple(
            SplitPermissionFact(
                source_permission=str(row["source_permission"]),
                target_permission=str(row["target_permission"]),
                target_sdk_threshold=int(row["target_sdk_threshold"]),
                target_ordinal=int(row["target_ordinal"]),
                platform_release_id=str(row["platform_release_id"]),
                source_snapshot_id=str(row["source_snapshot_id"]),
            )
            for row in rows
        )

    def get_source_evidence(
        self, canonical_permission: str
    ) -> tuple[Mapping[str, Any], ...]:
        """Return declaration provenance exposed by the versioned evidence view."""
        permission = _validate_permission_parameter(canonical_permission)
        return tuple(self._query(SOURCE_EVIDENCE_SQL, (permission,)))


def _default_query(sql: str, params: Sequence[object]) -> Sequence[Mapping[str, Any]]:
    """Execute through ObsidianDroid's existing Permission Intel reader."""
    from obsidiandroid.database import db_engine

    columns, rows = db_engine.execute_permission_query(
        sql,
        params=tuple(params),
        fetch=True,
        return_columns=True,
    )
    return tuple(dict(zip(columns, row)) for row in rows)


def _validate_permission_parameter(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("canonical permission must be non-empty")
    return text


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
