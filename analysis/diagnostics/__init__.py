"""Legacy diagnostics package shim (Pass 65).

Registers ``analysis.diagnostics.<name>`` in ``sys.modules`` to point at the same
:class:`types.ModuleType` objects as ``obsidiandroid.diagnostics.<name>`` so legacy
imports and monkeypatch surfaces keep working during migration.

Implementation modules live under ``src/obsidiandroid/diagnostics/``.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys

_CANONICAL_ROOT = "obsidiandroid.diagnostics"
_LEGACY_ROOT = "analysis.diagnostics"


def _ensure_same_object(legacy_modname: str, canon_modname: str) -> None:
    canon = importlib.import_module(canon_modname)
    sys.modules.setdefault(legacy_modname, canon)


_TOP_MODULES = (
    "ablation_cohort_diagnostics",
    "alignment_gap_diagnostics",
    "cohort_foundation_export",
    "cohort_sample_id_audit",
    "cohort_vocabulary",
    "feature_builder_drop_trace",
    "feature_build_coverage_export",
    "feature_column_survival_export",
    "feature_lineage_report",
    "feature_matrix_gap_lineage",
    "fused_permission_matrix_audit",
    "output_artifact_policy",
    "output_inventory",
    "permission_training_survival_audit",
)

for _name in _TOP_MODULES:
    _ensure_same_object(f"{_LEGACY_ROOT}.{_name}", f"{_CANONICAL_ROOT}.{_name}")


for _pkg in ("research_validity", "hostile_audit"):
    _pkg_canon_name = f"{_CANONICAL_ROOT}.{_pkg}"
    canon_pkg = importlib.import_module(_pkg_canon_name)
    sys.modules.setdefault(f"{_LEGACY_ROOT}.{_pkg}", canon_pkg)

    pkg_path = canon_pkg.__name__ + "."
    if not getattr(canon_pkg, "__path__", None):
        continue
    for _finder, _modname, _ispkg in pkgutil.walk_packages(canon_pkg.__path__, pkg_path):
        canon_mod = importlib.import_module(_modname)
        suffix = _modname.removeprefix(_CANONICAL_ROOT + ".")
        sys.modules.setdefault(f"{_LEGACY_ROOT}.{suffix}", canon_mod)


__all__: list[str] = []
