"""Evidence-aware interpretation over deployed Permission Intel surfaces."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from . import permission_contracts


AOSP_AUTHORITIES_SQL = "'AOSP_PUBLIC','AOSP_HIDDEN','AOSP_INTERNAL','AOSP_MODULE'"
HISTORICAL_LIFECYCLES_SQL = "'historical','legacy_removed','removed'"
ANDROIDX_DYNAMIC_RECEIVER_PERMISSION_RE = re.compile(
    r"[a-z0-9_]+(?:\.[a-z0-9_]+)+\.dynamic_receiver_not_exported_permission",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CurrentPermissionInterpretation:
    identifier_recognition: str
    authority_scope: str
    identifier_kind: str
    declaration_state: str
    evidence_state: str
    protection_result: str | None
    feature_dependency: str | None
    platform_authority_accepted: bool


def is_androidx_dynamic_receiver_permission(token: object) -> bool:
    """Recognize the exact AndroidX generated receiver-guard token shape."""
    return bool(ANDROIDX_DYNAMIC_RECEIVER_PERMISSION_RE.fullmatch(str(token or "")))


def _text(value: object) -> str:
    return str(value or "").strip()


def interpret_permission_evidence(
    *, token: str, identity: object | None = None, legacy: object | None = None,
    fact: object | None = None, non_permission: object | None = None,
    anomaly: object | None = None,
) -> CurrentPermissionInterpretation:
    """Interpret dataframe named-tuples or mappings without storage side effects."""

    def value(source: object | None, name: str) -> object:
        if isinstance(source, Mapping):
            return source.get(name)
        return getattr(source, name, None)

    canonical = _text(value(identity, "canonical_permission"))
    exact = bool(canonical and token == canonical)
    case_only = bool(canonical and not exact and token.lower() == canonical.lower())
    authority = _text(value(identity, "authority_class")).upper()
    feature = _text(value(identity, "feature_dependency")) or None
    conflicts = int(value(identity, "unresolved_conflict_count") or 0)
    fact_scope = _text(value(fact, "fact_scope")).lower()
    fact_source = _text(value(fact, "authority_source_type")).lower()
    fact_permission = _text(value(fact, "permission_string"))
    fact_exact = bool(fact_permission and token == fact_permission)
    fact_lifecycle = _text(value(fact, "lifecycle_status")).lower()
    catalog_lifecycle = _text(value(identity, "lifecycle")).lower()
    identity_status = _text(value(identity, "identity_status")).upper()
    legacy_lifecycle = _text(value(legacy, "lifecycle_status")).lower()
    protection = _text(
        value(identity, "compatibility_protection_expression")
        or value(fact, "protection_level")
    ) or None
    catalog_historical = catalog_lifecycle in {
        "historical", "legacy_removed", "removed",
    } or identity_status == "RETIRED"

    if canonical:
        platform = authority in {
            "AOSP_PUBLIC", "AOSP_HIDDEN", "AOSP_INTERNAL", "AOSP_MODULE"
        }
        return CurrentPermissionInterpretation(
            "EXACT_ACCEPTED_CANONICAL" if exact else "CASE_ONLY_CANONICAL_CANDIDATE",
            "HISTORICAL_PLATFORM"
            if catalog_historical and platform
            else "AOSP_PLATFORM"
            if platform
            else "OEM_OR_VENDOR"
            if authority == "OEM_OR_VENDOR"
            else "THIRD_PARTY_APPLICATION_DEFINED"
            if authority == "APPLICATION_DEFINED"
            else "UNKNOWN",
            "PERMISSION",
            "NOT_APPLICABLE" if catalog_historical else "MULTIPLE_FEATURE_DEPENDENT_ALTERNATIVES" if conflicts else "CONDITIONED" if feature else "UNCONDITIONAL",
            "ACCEPTED_CANONICAL",
            None if conflicts or catalog_historical else protection,
            feature,
            platform,
        )

    recognition = "CASE_ONLY_CANONICAL_CANDIDATE" if case_only else "UNRESOLVED_IDENTIFIER"
    non_permission_class = _text(value(non_permission, "token_class"))
    anomaly_class = _text(value(anomaly, "anomaly_class"))
    anomaly_blocks = bool(
        anomaly_class
        and not (
            anomaly_class.lower() == "vendor_namespace_in_android"
            and fact_source in {"sdk_vendor_docs", "sdk_inventory"}
        )
    )
    if non_permission_class or anomaly_blocks or legacy_lifecycle == "invalid_token":
        raw_kind = (non_permission_class or anomaly_class).lower()
        kind = (
            "ACTION_OR_EVENT" if "action" in raw_kind
            else "POLICY_IDENTIFIER" if "policy" in raw_kind
            else "FEATURE_OR_OTHER_IDENTIFIER" if raw_kind in {
                "hardware_feature", "permission_group", "other_android_constant", "generic_shorthand"
            }
            else "MALFORMED_OR_VARIANT"
        )
        return CurrentPermissionInterpretation(
            recognition if case_only else "NONCANONICAL_KNOWN_IDENTIFIER",
            "UNKNOWN", kind, "NOT_APPLICABLE", "SOURCE_BACKED_IDENTIFIER_KIND",
            None, None, False,
        )

    if fact_exact and (fact_scope == "removed_api" or (
        fact_lifecycle in {"historical", "legacy_removed", "removed"}
        and fact_source.startswith("aosp_")
    )):
        scope, kind = "HISTORICAL_PLATFORM", "PERMISSION"
    elif fact_exact and fact_scope == "provider_permission" and fact_source.startswith("aosp_"):
        scope, kind = "AOSP_PROVIDER_ACL", "PROVIDER_PERMISSION"
    elif fact_exact and fact_scope == "permission_definition" and fact_source == "aosp_package_manifest":
        scope, kind = "AOSP_PACKAGE_DEFINED", "PERMISSION"
    elif fact_exact and fact_scope == "permission_definition" and fact_source in {"sdk_vendor_docs", "sdk_inventory"}:
        scope, kind = "SDK_INTEGRATION_CUSTOM_PERMISSION", "PERMISSION"
    elif fact_exact and fact_scope == "permission_definition" and fact_source in {"chromium_source", "androidx_manifest"}:
        scope, kind = "THIRD_PARTY_APPLICATION_DEFINED", "PERMISSION"
    else:
        scope = kind = ""
    if scope:
        return CurrentPermissionInterpretation(
            recognition if case_only else "NONCANONICAL_KNOWN_IDENTIFIER",
            scope, kind, "NOT_APPLICABLE" if scope == "HISTORICAL_PLATFORM" else "UNCONDITIONAL",
            "SOURCE_BACKED_DEFINITION",
            None if scope == "HISTORICAL_PLATFORM" else protection,
            None,
            False,
        )

    provisional = (
        _text(value(legacy, "authority_source_type")).lower() == "queue_apply_shell"
        or _text(value(legacy, "source_family_key")).lower() == "aosp_sparse_queue_apply_shell"
    )
    return CurrentPermissionInterpretation(
        recognition, "UNKNOWN", "UNKNOWN", "NO_DECLARATION",
        "PROVISIONAL_SEED_ONLY" if provisional else "INSUFFICIENT",
        None, None, False,
    )


def interpretation_joins(*, key_expr: str, raw_expr: str) -> str:
    """Return joins for one observation alias using deployed, read-only objects."""

    aosp_join = permission_contracts.aosp_dictionary_join_predicate(
        raw_expr=raw_expr,
        aosp_alias="a",
    )
    alias_join = permission_contracts.token_alias_join(raw_expr=raw_expr)
    identity_expr = permission_contracts.catalog_identity_expr(raw_expr=raw_expr)
    fact_join = permission_contracts.authority_fact_join(raw_expr=identity_expr)
    return f"""
        LEFT JOIN android_permission_dict_aosp a
          ON {aosp_join}
        {alias_join}
        LEFT JOIN android_permission_v1_current_permission pi
          ON BINARY pi.canonical_permission = BINARY {identity_expr}
        LEFT JOIN android_permission_v1_obsidiandroid_permission piv
          ON BINARY piv.canonical_permission = BINARY pi.canonical_permission
         AND piv.catalog_release_id = pi.catalog_release_id
         AND piv.catalog_digest = pi.catalog_digest
        LEFT JOIN (
            SELECT permission_id, COUNT(*) AS unresolved_conflict_count
              FROM api_permission_declaration_conflict
             WHERE resolution_status = 'UNRESOLVED'
             GROUP BY permission_id
        ) pic ON pic.permission_id = pi.permission_id
        {fact_join}
        LEFT JOIN android_permission_non_permission_fact pnf
          ON pnf.is_active = 1
         AND pi.permission_id IS NULL
         AND (BINARY pnf.token_value = BINARY {raw_expr}
              OR pnf.token_value_norm = {key_expr})
        LEFT JOIN android_permission_token_anomaly_fact pta
          ON pta.is_active = 1
         AND pi.permission_id IS NULL
         AND (BINARY pta.token_value = BINARY {raw_expr}
              OR pta.token_value_norm = {key_expr})
    """


def interpretation_selects(
    *, historical_source_expr: str, raw_expr: str
) -> dict[str, str]:
    """Return compatible SQL projections whose certainty follows evidence."""

    platform = f"pi.authority_class IN ({AOSP_AUTHORITIES_SQL})"
    identity_expr = permission_contracts.catalog_identity_expr(raw_expr=raw_expr)
    fact_exact = f"(BINARY paf.permission_string = BINARY {identity_expr})"
    catalog_historical = (
        f"(pi.lifecycle IN ({HISTORICAL_LIFECYCLES_SQL}) OR pi.identity_status = 'RETIRED')"
    )
    invalid = """(a.lifecycle_status = 'invalid_token'
        OR pnf.non_permission_fact_id IS NOT NULL
        OR (pta.token_anomaly_fact_id IS NOT NULL
            AND NOT (pta.anomaly_class = 'vendor_namespace_in_android'
                     AND paf.authority_source_type IN ('sdk_vendor_docs','sdk_inventory'))))"""
    package = "(paf.fact_scope = 'permission_definition' AND paf.authority_source_type = 'aosp_package_manifest')"
    provider = "(paf.fact_scope = 'provider_permission' AND paf.authority_source_type IN ('aosp_package_manifest','aosp_framework_manifest'))"
    sdk_definition = "(paf.fact_scope = 'permission_definition' AND paf.authority_source_type IN ('sdk_vendor_docs','sdk_inventory'))"
    third_party = "(paf.fact_scope = 'permission_definition' AND paf.authority_source_type IN ('chromium_source','androidx_manifest'))"
    historical_fact = f"""({fact_exact} AND (paf.fact_scope = 'removed_api' OR (
        paf.lifecycle_status IN ({HISTORICAL_LIFECYCLES_SQL})
        AND LEFT(COALESCE(paf.authority_source_type,''), 5) = 'aosp_')))"""
    package = f"({fact_exact} AND {package})"
    provider = f"({fact_exact} AND {provider})"
    sdk_definition = f"({fact_exact} AND {sdk_definition})"
    third_party = f"({fact_exact} AND {third_party})"
    provisional = "(a.authority_source_type = 'queue_apply_shell' OR a.source_family_key = 'aosp_sparse_queue_apply_shell')"
    scope = f"""CASE
        WHEN pi.permission_id IS NOT NULL AND {platform} AND {catalog_historical} THEN 'HISTORICAL_PLATFORM'
        WHEN pi.permission_id IS NOT NULL AND {platform} THEN 'AOSP_PLATFORM'
        WHEN pi.permission_id IS NOT NULL AND pi.authority_class = 'OEM_OR_VENDOR' THEN 'OEM_OR_VENDOR'
        WHEN pi.permission_id IS NOT NULL AND pi.authority_class = 'APPLICATION_DEFINED' THEN 'THIRD_PARTY_APPLICATION_DEFINED'
        WHEN {invalid} THEN 'UNKNOWN'
        WHEN {historical_fact} THEN 'HISTORICAL_PLATFORM'
        WHEN {provider} THEN 'AOSP_PROVIDER_ACL'
        WHEN {package} THEN 'AOSP_PACKAGE_DEFINED'
        WHEN {sdk_definition} THEN 'SDK_INTEGRATION_CUSTOM_PERMISSION'
        WHEN {third_party} THEN 'THIRD_PARTY_APPLICATION_DEFINED'
        ELSE 'UNKNOWN' END"""
    kind = f"""CASE
        WHEN pi.permission_id IS NOT NULL THEN 'PERMISSION'
        WHEN pnf.token_class IN ('intent_action','settings_action') THEN 'ACTION_OR_EVENT'
        WHEN pnf.token_class = 'hardware_feature' THEN 'FEATURE_OR_OTHER_IDENTIFIER'
        WHEN {invalid} THEN 'MALFORMED_OR_VARIANT'
        WHEN {provider} THEN 'PROVIDER_PERMISSION'
        WHEN {package} OR {sdk_definition} OR {third_party} OR {historical_fact} THEN 'PERMISSION'
        ELSE 'UNKNOWN' END"""
    declaration = f"""CASE
        WHEN pi.permission_id IS NOT NULL AND {catalog_historical} THEN 'NOT_APPLICABLE'
        WHEN pi.permission_id IS NOT NULL AND COALESCE(pic.unresolved_conflict_count,0) > 0 THEN 'MULTIPLE_FEATURE_DEPENDENT_ALTERNATIVES'
        WHEN pi.permission_id IS NOT NULL AND pi.feature_dependency IS NOT NULL THEN 'CONDITIONED'
        WHEN pi.permission_id IS NOT NULL THEN 'UNCONDITIONAL'
        WHEN {invalid} THEN 'NOT_APPLICABLE'
        WHEN {historical_fact} THEN 'NOT_APPLICABLE'
        WHEN {provider} OR {package} OR {sdk_definition} OR {third_party} THEN 'UNCONDITIONAL'
        ELSE 'NO_DECLARATION' END"""
    evidence = f"""CASE
        WHEN pi.permission_id IS NOT NULL THEN 'ACCEPTED_CANONICAL'
        WHEN {invalid} THEN 'SOURCE_BACKED_IDENTIFIER_KIND'
        WHEN paf.authority_fact_id IS NOT NULL AND ({provider} OR {package} OR {sdk_definition} OR {third_party} OR {historical_fact}) THEN 'SOURCE_BACKED_DEFINITION'
        WHEN {provisional} THEN 'PROVISIONAL_SEED_ONLY'
        ELSE 'INSUFFICIENT' END"""
    safe_protection = f"""CASE
        WHEN pi.permission_id IS NOT NULL AND {platform}
         AND COALESCE(pic.unresolved_conflict_count,0) = 0
         AND pi.feature_dependency IS NULL AND NOT {catalog_historical}
        THEN piv.compatibility_protection_expression
        WHEN paf.authority_fact_id IS NOT NULL AND ({provider} OR {package} OR {third_party})
         AND NOT {historical_fact}
         AND LOWER(COALESCE(paf.protection_level,''))
             REGEXP '^(normal|dangerous|signature)(\\|[a-z0-9_]+)*$'
        THEN paf.protection_level
        ELSE NULL END"""
    source = f"""CASE
        WHEN ({scope}) IN ('AOSP_PLATFORM','HISTORICAL_PLATFORM') THEN 'AOSP'
        WHEN ({scope}) IN ('AOSP_PACKAGE_DEFINED','THIRD_PARTY_APPLICATION_DEFINED','SDK_INTEGRATION_CUSTOM_PERMISSION') THEN 'APP_DEFINED'
        WHEN ({scope}) = 'AOSP_PROVIDER_ACL' THEN 'PROVIDER_PERMISSION'
        WHEN ({scope}) = 'OEM_OR_VENDOR' THEN 'OEM'
        ELSE 'UNKNOWN' END"""
    return {
        "historical_permission_source": historical_source_expr,
        "current_authority_scope": scope,
        "current_identifier_kind": kind,
        "current_declaration_state": declaration,
        "current_evidence_state": evidence,
        "current_feature_dependency": "pi.feature_dependency",
        "permission_source": source,
        "safe_protection_expression": safe_protection,
        "protection_level": f"UPPER(COALESCE(({safe_protection}), 'UNKNOWN'))",
        "is_aosp_dict_match": f"CASE WHEN pi.permission_id IS NOT NULL AND {platform} AND NOT {catalog_historical} THEN 1 ELSE 0 END",
    }


__all__ = [
    "CurrentPermissionInterpretation",
    "interpret_permission_evidence",
    "interpretation_joins",
    "interpretation_selects",
]
