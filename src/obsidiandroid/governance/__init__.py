"""Governance helpers (evidence mode, compliance contracts; incremental migration).

Concrete modules live under :mod:`obsidiandroid.governance`; legacy
``analysis.pipeline.governance.*`` paths resolve to the same ``ModuleType`` objects
(**Pass 75** thin shims for exceptions, integrity, policy, readiness).
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
    "policy",
    "readiness",
    "run_manifest",
)

for _name in _CANONICAL_SUBMODULE_NAMES:
    _canon = importlib.import_module(f"{__name__}.{_name}")
    globals()[_name] = _canon
    sys.modules.setdefault(f"obsidiandroid.governance.{_name}", _canon)

__all__ = list(_CANONICAL_SUBMODULE_NAMES)

del _CANONICAL_SUBMODULE_NAMES, _name, _canon
