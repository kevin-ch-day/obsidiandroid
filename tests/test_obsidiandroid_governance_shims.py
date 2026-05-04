"""Legacy ``utils.evidence_mode_resolver`` shim matches canonical governance module."""

from __future__ import annotations

import obsidiandroid.governance.evidence_mode_resolver as canon
from utils import evidence_mode_resolver as shim


def test_evidence_mode_resolver_shim_matches_canonical() -> None:
    assert shim.resolve_evidence_mode is canon.resolve_evidence_mode
    assert shim.enforce_immutable_lock is canon.enforce_immutable_lock
    assert shim.ENV_EVIDENCE_MODE == canon.ENV_EVIDENCE_MODE
    assert shim.EvidenceModeConfigError is canon.EvidenceModeConfigError
    assert shim.EvidenceModeImmutableError is canon.EvidenceModeImmutableError
    assert shim.EvidenceModeResolution is canon.EvidenceModeResolution
