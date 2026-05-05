"""Governance helpers (evidence mode, compliance contracts; incremental migration).

Concrete modules: :mod:`obsidiandroid.governance.evidence_mode_resolver`,
:mod:`obsidiandroid.governance.compliance`, :mod:`obsidiandroid.governance.cohort_readiness_report`,
:mod:`obsidiandroid.governance.cohort_reproducibility`, :mod:`obsidiandroid.governance.run_manifest`,
:mod:`obsidiandroid.governance.artifacts`.
Legacy ``utils.*`` shims are thin re-exports where present.
"""

from __future__ import annotations

import importlib
import sys

_CANONICAL_SUBMODULE_NAMES = (
    "artifacts",
    "cohort_readiness_report",
    "cohort_reproducibility",
    "compliance",
    "evidence_mode_resolver",
    "exceptions",
    "integrity",
    "run_manifest",
)
_LEGACY_BY_CANONICAL = {
    "exceptions": "analysis.pipeline.governance.exceptions",
    "integrity": "analysis.pipeline.governance.integrity",
}

for _name in _CANONICAL_SUBMODULE_NAMES:
    _canon = importlib.import_module(_LEGACY_BY_CANONICAL.get(_name, f"{__name__}.{_name}"))
    globals()[_name] = _canon
    sys.modules.setdefault(f"obsidiandroid.governance.{_name}", _canon)

__all__ = list(_CANONICAL_SUBMODULE_NAMES)

del _CANONICAL_SUBMODULE_NAMES, _LEGACY_BY_CANONICAL, _name, _canon
