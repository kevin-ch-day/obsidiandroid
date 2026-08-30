from __future__ import annotations

from copy import deepcopy

import pytest

from obsidiandroid.database.permission_intel_v1.gate import evaluate_catalog_gate
from obsidiandroid.database.permission_intel_v1.models import (
    ApiVersion,
    CatalogGateState,
)


def _catalog_row() -> dict[str, object]:
    return {
        "schema_contract_id": "org.android-permission-intel.schema-v1-draft",
        "schema_contract_version": "1.0.0-draft",
        "compatibility_floor": "1.0.0-draft",
        "schema_contract_release_status": "DRAFT",
        "catalog_release_id": "android-17-r1-audit-2026-08-30-source-identity-correction-1",
        "catalog_digest": "075accc8aa2042d0d9454ba12e8625b87e76fe54366532c6bca21d56066fc334",
        "source_set_id": "android-17-r1-audit-2026-08-30-source-identity-correction-1",
        "source_set_digest": "54105d49b7b40b0ab792976b82fe52d579da19be181dcbde369ad86c7ae8febc",
        "platform_release_coverage": "android-api-37",
        "scope_completeness_statement": "Accepted scoped union only; not exhaustive.",
        "exhaustive_scope": 0,
        "catalog_release_status": "ACCEPTED",
        "catalog_import_status": "IMPORTED",
        "import_receipt_count": 1,
        "parser_package_version": "0.2.0",
        "notes_and_limitations": "incomplete source scope",
    }


def test_pinned_catalog_is_compatible_but_explicitly_incomplete() -> None:
    decision = evaluate_catalog_gate([_catalog_row()])
    assert decision.state is CatalogGateState.COMPATIBLE_INCOMPLETE_SCOPE
    assert decision.shadow_available is True
    assert decision.catalog_status is not None
    assert decision.catalog_status.exhaustive_scope is False


def test_exhaustive_pinned_catalog_is_current() -> None:
    row = _catalog_row()
    row["exhaustive_scope"] = 1
    assert evaluate_catalog_gate([row]).state is CatalogGateState.COMPATIBLE_CURRENT


@pytest.mark.parametrize(
    ("version", "state"),
    [
        ("0.9.9", CatalogGateState.SCHEMA_TOO_OLD),
        ("1.0.1", CatalogGateState.SCHEMA_TOO_NEW),
        ("2.0.0", CatalogGateState.SCHEMA_TOO_NEW),
    ],
)
def test_schema_version_bounds(version: str, state: CatalogGateState) -> None:
    row = _catalog_row()
    row["schema_contract_version"] = version
    assert evaluate_catalog_gate([row]).state is state


def test_catalog_missing() -> None:
    assert evaluate_catalog_gate([]).state is CatalogGateState.CATALOG_MISSING


def test_candidate_catalog_is_rejected() -> None:
    row = _catalog_row()
    row["catalog_release_status"] = "CANDIDATE"
    decision = evaluate_catalog_gate([row])
    assert decision.state is CatalogGateState.CATALOG_NOT_ACCEPTED
    assert decision.shadow_available is False


def test_unreceipted_catalog_is_rejected() -> None:
    row = _catalog_row()
    row["catalog_import_status"] = "MISSING"
    row["import_receipt_count"] = 0
    assert evaluate_catalog_gate([row]).state is CatalogGateState.CATALOG_NOT_ACCEPTED


def test_compatible_different_content_is_stale() -> None:
    row = _catalog_row()
    row["catalog_release_id"] = "android-17-r2"
    row["catalog_digest"] = "b" * 64
    decision = evaluate_catalog_gate([row])
    assert decision.state is CatalogGateState.COMPATIBLE_STALE_CONTENT
    assert decision.shadow_available is True


def test_malformed_schema_version_requires_explicit_degraded_mode() -> None:
    row = _catalog_row()
    row["schema_contract_version"] = "one"
    assert (
        evaluate_catalog_gate([row]).state
        is CatalogGateState.EXPLICIT_DEGRADED_MODE_REQUIRED
    )


def test_multiple_current_catalog_rows_fail_closed() -> None:
    assert (
        evaluate_catalog_gate([_catalog_row(), deepcopy(_catalog_row())]).state
        is CatalogGateState.EXPLICIT_DEGRADED_MODE_REQUIRED
    )


@pytest.mark.parametrize("raw", ["37", "36.1", "37.1", "37.2"])
def test_full_api_version_is_string_preserving(raw: str) -> None:
    parsed = ApiVersion.parse(raw)
    assert parsed.full == raw
    assert isinstance(parsed.major, int)
    assert isinstance(parsed.minor, int)


@pytest.mark.parametrize("raw", [37.1, "37.01", "37.2.1", "unknown", ""])
def test_full_api_version_rejects_float_or_malformed_value(raw: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        ApiVersion.parse(raw)
