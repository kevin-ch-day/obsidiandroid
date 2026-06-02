"""Canonical governance namespace.

Evidence mode, compliance, cohort reproducibility, manifest, and governance
policy helpers live under :mod:`obsidiandroid.governance`. Legacy
``analysis.pipeline.governance.*`` imports remain compatibility aliases
brokered from the protected ``analysis.pipeline`` shell.
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
    "paper_family_display_policy",
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
