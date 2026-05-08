"""Smoke tests for ``obsidiandroid.governance.evidence_mode_resolver`` public surface."""

from __future__ import annotations

import obsidiandroid.governance.evidence_mode_resolver as gov


def test_evidence_mode_resolver_public_symbols() -> None:
    assert callable(gov.resolve_evidence_mode)
    assert callable(gov.enforce_immutable_lock)
    assert isinstance(gov.ENV_EVIDENCE_MODE, str)
    assert gov.EvidenceModeConfigError is not None
    assert gov.EvidenceModeImmutableError is not None
    assert gov.EvidenceModeResolution is not None
