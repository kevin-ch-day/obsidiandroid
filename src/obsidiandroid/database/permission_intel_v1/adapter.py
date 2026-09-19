"""Focused SELECT-only adapter for Permission Intel v1 platform facts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from .gate import CATALOG_STATUS_SQL, evaluate_catalog_gate
from .models import (
    PERMISSION_FLAG_VOCABULARY,
    PINNED_SCHEMA_CONTRACT_VERSION,
    ApiVersion,
    AuthorityClass,
    CatalogGateDecision,
    DeclarationAlternative,
    PlatformPermissionFact,
    ProtectionSemantics,
    SplitPermissionFact,
)


class ReadQuery(Protocol):
    """Injected read executor used by production and disposable test paths."""

    def __call__(
        self, sql: str, params: Sequence[object]
    ) -> Sequence[Mapping[str, Any]]: ...


DEPLOYED_INTERPRETATION_CONTRACT = PINNED_SCHEMA_CONTRACT_VERSION
SUPPORTED_INTERPRETATION_CONTRACTS = frozenset(
    {DEPLOYED_INTERPRETATION_CONTRACT, "1.1.0-draft"}
)
_IDENTITY_STATUS_RECOGNITION = {
    "ACCEPTED": "ACCEPTED_EXACT_IDENTITY",
    "CANDIDATE": "CANDIDATE_IDENTITY",
    "CONFLICT": "CONFLICT_IDENTITY",
    "RETIRED": "RETIRED_IDENTITY",
}
_PROTECTION_KEYS = (
    "protection_base",
    "protection_modifiers",
    "compatibility_protection_expression",
    "raw_protection_expression",
)

PERMISSION_LOOKUP_SQL = """
SELECT
    p.catalog_release_id,
    p.catalog_digest,
    p.canonical_permission,
    p.symbolic_name,
    p.namespace,
    p.defining_package,
    p.authority_class,
    p.identity_status,
    p.lifecycle,
    p.visibility,
    p.accepted_platform_release,
    p.sdk_extension_release_id,
    p.source_snapshot_id,
    p.source_provenance_status,
    p.public_manifest_exposed,
    p.public_health_exposed,
    p.health_module_declared,
    p.feature_dependency,
    COALESCE(pic.unresolved_conflict_count, 0) AS unresolved_conflict_count,
    prot.protection_base,
    prot.protection_modifiers,
    prot.compatibility_protection_expression,
    prot.raw_protection_expression
FROM android_permission_v1_current_permission AS p
LEFT JOIN (
    SELECT permission_id, COUNT(*) AS unresolved_conflict_count
      FROM api_permission_declaration_conflict
     WHERE resolution_status = 'UNRESOLVED'
     GROUP BY permission_id
) pic ON pic.permission_id = p.permission_id
LEFT JOIN (
    SELECT f.*
      FROM android_permission_v1_current_protection f
      INNER JOIN (
          SELECT MIN(declaration_revision_id) AS declaration_revision_id,
                 canonical_permission,
                 catalog_release_id
            FROM android_permission_v1_current_protection
           GROUP BY canonical_permission, catalog_release_id
          HAVING COUNT(*) = 1
      ) one
        ON one.declaration_revision_id = f.declaration_revision_id
       AND BINARY one.canonical_permission = BINARY f.canonical_permission
       AND one.catalog_release_id = f.catalog_release_id
) prot
  ON BINARY prot.canonical_permission = BINARY p.canonical_permission
 AND prot.catalog_release_id = p.catalog_release_id
WHERE BINARY p.canonical_permission = BINARY %s
""".strip()

DECLARATION_ALTERNATIVES_SQL = """
SELECT
    p.catalog_release_id,
    p.catalog_digest,
    CAST(p.declaration_revision_id AS CHAR) AS declaration_revision_id,
    p.lifecycle,
    p.accepted_platform_release,
    p.sdk_extension_release_id,
    p.feature_dependency,
    NULL AS feature_flag,
    NULL AS feature_flag_value,
    'REQUIRES_BUILD_CONFIGURATION_EVIDENCE' AS applicability_state,
    p.visibility,
    p.defining_package,
    p.permission_group,
    p.background_permission,
    p.max_sdk,
    p.source_snapshot_id,
    NULL AS declaration_locator,
    prot.protection_base,
    prot.protection_modifiers,
    prot.compatibility_protection_expression,
    prot.raw_protection_expression,
    NULL AS declaration_evidence_status
FROM android_permission_v1_current_permission AS p
LEFT JOIN android_permission_v1_current_protection AS prot
  ON BINARY prot.canonical_permission = BINARY p.canonical_permission
 AND prot.catalog_release_id = p.catalog_release_id
 AND (p.declaration_revision_id IS NULL
      OR prot.declaration_revision_id = p.declaration_revision_id)
WHERE BINARY p.canonical_permission = BINARY %s
  AND p.feature_dependency IS NOT NULL
  AND TRIM(p.feature_dependency) <> ''
ORDER BY p.declaration_revision_id
""".strip()

PERMISSION_FLAGS_SQL = """
SELECT catalog_release_id, normalized_flag
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
    DECLARATION_ALTERNATIVES_SQL,
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
        if len(rows) != 1:
            raise ValueError("Permission Intel interpretation returned duplicate identity rows")
        row = dict(rows[0])
        contract = _interpretation_contract(row)
        catalog_release_id = str(row.get("catalog_release_id") or "")
        (
            identity_recognition_state,
            declaration_state,
            applicability_state,
            protection_state,
            evidence_basis,
            scalar_projection_status,
        ) = _interpretation_fields(row)
        alternative_rows = self._query(DECLARATION_ALTERNATIVES_SQL, (permission,))
        if any(
            str(item.get("catalog_release_id") or "") != catalog_release_id
            or str(item.get("catalog_digest") or "")
            != str(row.get("catalog_digest") or "")
            for item in alternative_rows
        ):
            raise ValueError("catalog changed during v1 declaration-alternative lookup")
        alternatives = tuple(_alternative(item) for item in alternative_rows)
        scalar_safe = scalar_projection_status in {
            "DECLARED_SOURCE_SCOPED",
            "DECLARED_CONDITIONED_NOT_DEVICE_EFFECTIVE",
        }
        if not scalar_safe:
            for key in _PROTECTION_KEYS:
                row[key] = None
        flag_rows = self._query(PERMISSION_FLAGS_SQL, (permission,)) if scalar_safe else ()
        if any(
            str(item.get("catalog_release_id") or "") != catalog_release_id
            for item in flag_rows
        ):
            raise ValueError("catalog changed during v1 permission lookup")
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
            catalog_release_id=catalog_release_id,
            catalog_digest=str(row.get("catalog_digest") or ""),
            interpretation_contract_version=contract,
            identity_recognition_state=identity_recognition_state,
            declaration_state=declaration_state,
            applicability_state=applicability_state,
            protection_state=protection_state,
            evidence_basis=evidence_basis,
            scalar_projection_status=scalar_projection_status,
            alternatives=alternatives,
        )

    def get_split_relations(
        self, canonical_permission: str
    ) -> tuple[SplitPermissionFact, ...]:
        """Return accepted split targets for one case-sensitive source permission."""
        permission = _validate_permission_parameter(canonical_permission)
        rows = self._query(SPLIT_PERMISSION_SQL, (permission,))
        splits: list[SplitPermissionFact] = []
        for row in rows:
            threshold = row.get("target_sdk_threshold")
            splits.append(
                SplitPermissionFact(
                    source_permission=str(row["source_permission"]),
                    target_permission=str(row["target_permission"]),
                    target_sdk_threshold=(
                        int(threshold) if threshold is not None else None
                    ),
                    target_ordinal=int(row["target_ordinal"]),
                    platform_release_id=str(row["platform_release_id"]),
                    source_snapshot_id=str(row["source_snapshot_id"]),
                )
            )
        return tuple(splits)

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
    if not isinstance(value, str) or not value.strip():
        raise ValueError("canonical permission must be non-empty")
    if value != value.strip():
        raise ValueError("canonical permission must not contain surrounding whitespace")
    return value


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _row_text(row: Mapping[str, Any], key: str) -> str | None:
    if key not in row:
        return None
    return _optional_text(row.get(key))


def _interpretation_contract(row: Mapping[str, Any]) -> str:
    if "interpretation_contract_version" not in row:
        return DEPLOYED_INTERPRETATION_CONTRACT
    raw = row.get("interpretation_contract_version")
    if raw in (None, ""):
        return DEPLOYED_INTERPRETATION_CONTRACT
    text = str(raw)
    if text not in SUPPORTED_INTERPRETATION_CONTRACTS:
        raise ValueError("unsupported Permission Intel interpretation contract")
    return text


def _interpretation_fields(row: Mapping[str, Any]) -> tuple[str, str, str, str, str, str]:
    conflicts = int(row.get("unresolved_conflict_count") or 0)
    feature = _optional_text(row.get("feature_dependency"))
    identity_status = str(row.get("identity_status") or "").strip().upper()
    withheld = bool(conflicts or feature or identity_status == "RETIRED")
    missing_protection = not any(
        _optional_text(row.get(key)) for key in _PROTECTION_KEYS
    )
    recognition = _row_text(row, "identity_recognition_state") or (
        _IDENTITY_STATUS_RECOGNITION.get(identity_status, "ACCEPTED_EXACT_IDENTITY")
    )
    if _row_text(row, "declaration_state"):
        declaration = str(_row_text(row, "declaration_state"))
    elif conflicts:
        declaration = "MULTIPLE_FEATURE_DEPENDENT_ALTERNATIVES"
    elif feature:
        declaration = "CONDITIONED"
    else:
        declaration = "SINGLE_UNCONDITIONAL_DECLARATION"
    applicability = _row_text(row, "applicability_state") or (
        "REQUIRES_BUILD_CONFIGURATION_EVIDENCE"
        if withheld
        else "DECLARED_IN_ACCEPTED_SOURCE_SCOPE_NOT_DEVICE_GRANT"
    )
    protection_state = _row_text(row, "protection_state") or (
        "UNKNOWN_REQUIRES_BUILD_CONFIGURATION"
        if withheld
        else "DECLARED_IN_ACCEPTED_SOURCE_SCOPE"
    )
    evidence = _row_text(row, "evidence_basis") or (
        "MANIFEST_CONDITIONAL_ALTERNATIVES"
        if feature or conflicts
        else "MANIFEST_DECLARATION"
    )
    scalar = _row_text(row, "scalar_projection_status") or (
        "WITHHELD_UNRESOLVED_ALTERNATIVES"
        if withheld
        else "WITHHELD_MISSING_PROTECTION"
        if missing_protection
        else "DECLARED_SOURCE_SCOPED"
    )
    return recognition, declaration, applicability, protection_state, evidence, scalar


def _alternative(row: Mapping[str, Any]) -> DeclarationAlternative:
    platform_raw = row.get("accepted_platform_release")
    return DeclarationAlternative(
        declaration_revision_id=str(row.get("declaration_revision_id") or ""),
        feature_dependency=_optional_text(row.get("feature_dependency")),
        feature_flag=_optional_text(row.get("feature_flag")),
        feature_flag_value=(
            bool(row.get("feature_flag_value"))
            if row.get("feature_flag_value") is not None
            else None
        ),
        applicability_state=str(row.get("applicability_state") or ""),
        lifecycle=_optional_text(row.get("lifecycle")),
        platform_release=(
            ApiVersion.parse(platform_raw) if platform_raw is not None else None
        ),
        sdk_extension_release_id=_optional_text(row.get("sdk_extension_release_id")),
        source_snapshot_id=_optional_text(row.get("source_snapshot_id")),
        declaration_locator=_optional_text(row.get("declaration_locator")),
        defining_package=_optional_text(row.get("defining_package")),
        permission_group=_optional_text(row.get("permission_group")),
        background_permission=_optional_text(row.get("background_permission")),
        visibility=_optional_text(row.get("visibility")),
        max_sdk=int(row["max_sdk"]) if row.get("max_sdk") is not None else None,
        protection=ProtectionSemantics.from_v1_row(row),
        declaration_evidence_status=_optional_text(
            row.get("declaration_evidence_status")
        ),
    )
