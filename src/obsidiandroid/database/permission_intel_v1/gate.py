"""Minimum-version gate for the pinned Permission Intel v1 draft."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .models import (
    PINNED_CATALOG_DIGEST,
    PINNED_CATALOG_RELEASE_ID,
    PINNED_SCHEMA_CONTRACT_ID,
    PINNED_SCHEMA_CONTRACT_VERSION,
    CatalogGateDecision,
    CatalogGateState,
    CatalogStatus,
)

CATALOG_STATUS_SQL = """
SELECT
    schema_contract_id,
    schema_contract_version,
    compatibility_floor,
    schema_contract_release_status,
    catalog_release_id,
    catalog_digest,
    source_set_id,
    source_set_digest,
    platform_release_coverage,
    scope_completeness_statement,
    exhaustive_scope,
    catalog_release_status,
    catalog_import_status,
    import_receipt_count,
    parser_package_version,
    notes_and_limitations
FROM android_permission_v1_catalog_release
""".strip()

_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?$"
)


@dataclass(frozen=True, order=True)
class _SemanticVersion:
    major: int
    minor: int
    patch: int
    prerelease_rank: int
    prerelease: str

    @classmethod
    def parse(cls, value: str) -> _SemanticVersion:
        match = _SEMVER_RE.fullmatch(value)
        if match is None:
            raise ValueError(f"malformed schema version: {value!r}")
        prerelease = match.group(4) or ""
        return cls(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            0 if prerelease else 1,
            prerelease,
        )


def evaluate_catalog_gate(rows: Sequence[Mapping[str, Any]]) -> CatalogGateDecision:
    """Evaluate one accepted-catalog metadata row against the pinned pilot contract."""
    if not rows:
        return _decision(CatalogGateState.CATALOG_MISSING, False, "catalog_row_missing")
    if len(rows) != 1:
        return _decision(
            CatalogGateState.EXPLICIT_DEGRADED_MODE_REQUIRED,
            False,
            "catalog_row_cardinality_invalid",
        )

    status = CatalogStatus.from_row(rows[0])
    if status.schema_contract_id != PINNED_SCHEMA_CONTRACT_ID:
        return _decision(
            CatalogGateState.EXPLICIT_DEGRADED_MODE_REQUIRED,
            False,
            "schema_contract_identifier_mismatch",
            status,
        )

    try:
        actual = _SemanticVersion.parse(status.schema_contract_version)
        supported = _SemanticVersion.parse(PINNED_SCHEMA_CONTRACT_VERSION)
        floor = _SemanticVersion.parse(status.compatibility_floor)
    except ValueError:
        return _decision(
            CatalogGateState.EXPLICIT_DEGRADED_MODE_REQUIRED,
            False,
            "schema_version_malformed",
            status,
        )

    if actual < floor or actual < supported:
        return _decision(
            CatalogGateState.SCHEMA_TOO_OLD, False, "schema_too_old", status
        )
    if actual > supported:
        return _decision(
            CatalogGateState.SCHEMA_TOO_NEW, False, "schema_too_new", status
        )

    if status.catalog_release_status != "ACCEPTED":
        return _decision(
            CatalogGateState.CATALOG_NOT_ACCEPTED,
            False,
            "catalog_release_not_accepted",
            status,
        )
    if status.catalog_import_status != "IMPORTED" or status.import_receipt_count < 1:
        return _decision(
            CatalogGateState.CATALOG_NOT_ACCEPTED,
            False,
            "catalog_import_not_proven",
            status,
        )

    if (
        status.catalog_release_id != PINNED_CATALOG_RELEASE_ID
        or status.catalog_digest != PINNED_CATALOG_DIGEST
    ):
        return _decision(
            CatalogGateState.COMPATIBLE_STALE_CONTENT,
            True,
            "catalog_differs_from_pinned_shadow_candidate",
            status,
        )
    if not status.exhaustive_scope:
        return _decision(
            CatalogGateState.COMPATIBLE_INCOMPLETE_SCOPE,
            True,
            "source_scope_explicitly_incomplete",
            status,
        )
    return _decision(
        CatalogGateState.COMPATIBLE_CURRENT, True, "compatible_current", status
    )


def _decision(
    state: CatalogGateState,
    available: bool,
    code: str,
    status: CatalogStatus | None = None,
) -> CatalogGateDecision:
    return CatalogGateDecision(state, available, (code,), status)
