"""Legacy-authoritative Permission Intel v1 shadow orchestration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .adapter import PermissionIntelV1Adapter
from .models import CatalogGateDecision, ComparisonState, ShadowMode
from .parity import LegacyPlatformFact, PermissionComparison, compare_permission

SHADOW_MODE_ENV = "OBSIDIANDROID_PERMISSION_INTEL_V1_SHADOW_MODE"


def configured_shadow_mode(explicit: str | None = None) -> ShadowMode:
    """Resolve explicit shadow mode; default is always legacy-only."""
    raw = (
        explicit if explicit is not None else os.getenv(SHADOW_MODE_ENV, "LEGACY_ONLY")
    )
    text = str(raw or "LEGACY_ONLY").strip().upper()
    try:
        mode = ShadowMode(text)
    except ValueError as exc:
        raise ValueError(f"unsupported {SHADOW_MODE_ENV} value") from exc
    if mode is ShadowMode.V1_UNAVAILABLE_LEGACY_ACTIVE:
        raise ValueError(
            f"{ShadowMode.V1_UNAVAILABLE_LEGACY_ACTIVE.value} is diagnostic-only"
        )
    return mode


@dataclass(frozen=True)
class ShadowDiagnostic:
    """Credential-free result of an optional shadow lookup."""

    mode: ShadowMode
    gate: CatalogGateDecision | None
    comparison: PermissionComparison | None
    diagnostic_codes: tuple[str, ...]


@dataclass(frozen=True)
class ShadowLookupResult:
    """Legacy authoritative value plus non-authoritative diagnostic evidence."""

    authoritative_legacy_value: Mapping[str, Any]
    diagnostic: ShadowDiagnostic


class PermissionIntelV1Shadow:
    """Run optional v1 comparison without ever replacing the legacy value."""

    def __init__(
        self,
        adapter: PermissionIntelV1Adapter,
        *,
        mode: ShadowMode | None = None,
    ) -> None:
        self._adapter = adapter
        self._mode = mode or configured_shadow_mode()

    def lookup(
        self,
        canonical_permission: str,
        legacy_value: Mapping[str, Any],
    ) -> ShadowLookupResult:
        """Return the exact legacy mapping and attach optional v1 diagnostics."""
        if self._mode is ShadowMode.LEGACY_ONLY:
            return ShadowLookupResult(
                legacy_value,
                ShadowDiagnostic(self._mode, None, None, ("shadow_disabled",)),
            )

        try:
            gate = self._adapter.read_catalog_gate()
            if not gate.shadow_available:
                return ShadowLookupResult(
                    legacy_value,
                    ShadowDiagnostic(
                        ShadowMode.V1_UNAVAILABLE_LEGACY_ACTIVE,
                        gate,
                        None,
                        gate.diagnostic_codes,
                    ),
                )
            v1 = self._adapter.get_permission(canonical_permission)
            legacy = LegacyPlatformFact.from_mapping(legacy_value)
            comparison = compare_permission(legacy, v1)
            return ShadowLookupResult(
                legacy_value,
                ShadowDiagnostic(
                    self._mode, gate, comparison, (comparison.state.value,)
                ),
            )
        except Exception as exc:  # noqa: BLE001 - shadow must never fail legacy operation
            return ShadowLookupResult(
                legacy_value,
                ShadowDiagnostic(
                    ShadowMode.V1_UNAVAILABLE_LEGACY_ACTIVE,
                    None,
                    PermissionComparison(
                        canonical_permission,
                        ComparisonState.ERROR,
                        (),
                    ),
                    (f"shadow_adapter_error:{type(exc).__name__}",),
                ),
            )
