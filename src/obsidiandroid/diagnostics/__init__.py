"""Diagnostics facade: re-exports selected ``analysis.diagnostics`` modules.

Implementation remains under ``analysis/diagnostics/``. Prefer this package for new
imports that should align with the installable ``obsidiandroid`` namespace::

    from obsidiandroid.diagnostics import output_inventory
    output_inventory.evaluate_paper_safe_status(...)

Research-validity and hostile-audit *packages* (Pass 36) reuse the same
``analysis.diagnostics.*`` package objects and register
``sys.modules["obsidiandroid.diagnostics.<name>"]`` so submodule imports resolve::

    from obsidiandroid.diagnostics import research_validity
    research_validity.write_research_validity_bundle(...)
    from obsidiandroid.diagnostics.research_validity.cohort_funnel import finalize_cohort_funnel_dict

Operator scripts prepend repo ``src/`` to ``sys.path`` when needed (see Pass 34).
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
from types import ModuleType

from analysis.diagnostics import ablation_cohort_diagnostics


def _alias_analysis_diag_package(*, facade_root: str, canon_pkg: ModuleType) -> None:
    """Register ``facade_root`` and every submodule mirror on ``sys.modules``.

    Imports like ``obsidiandroid.diagnostics.research_validity.cohort_funnel`` must
    resolve to the **same** module object as ``analysis.diagnostics...`` so tests
    and tooling do not load duplicate definitions.
    """
    sys.modules.setdefault(facade_root, canon_pkg)
    base = canon_pkg.__name__ + "."
    if not hasattr(canon_pkg, "__path__"):
        return
    for _finder, modname, _ispkg in pkgutil.walk_packages(canon_pkg.__path__, base):
        alias = facade_root + "." + modname[len(base) :]
        canon_mod = importlib.import_module(modname)
        sys.modules.setdefault(alias, canon_mod)
from analysis.diagnostics import alignment_gap_diagnostics
from analysis.diagnostics import cohort_foundation_export
from analysis.diagnostics import cohort_sample_id_audit
from analysis.diagnostics import cohort_vocabulary
from analysis.diagnostics import feature_builder_drop_trace
from analysis.diagnostics import feature_build_coverage_export
from analysis.diagnostics import feature_column_survival_export
from analysis.diagnostics import feature_lineage_report
from analysis.diagnostics import feature_matrix_gap_lineage
from analysis.diagnostics import fused_permission_matrix_audit
from analysis.diagnostics import output_artifact_policy
from analysis.diagnostics import output_inventory
from analysis.diagnostics import permission_training_survival_audit

research_validity = importlib.import_module("analysis.diagnostics.research_validity")
hostile_audit = importlib.import_module("analysis.diagnostics.hostile_audit")
_alias_analysis_diag_package(facade_root="obsidiandroid.diagnostics.research_validity", canon_pkg=research_validity)
_alias_analysis_diag_package(facade_root="obsidiandroid.diagnostics.hostile_audit", canon_pkg=hostile_audit)

__all__ = [
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
    "hostile_audit",
    "output_artifact_policy",
    "output_inventory",
    "permission_training_survival_audit",
    "research_validity",
]
