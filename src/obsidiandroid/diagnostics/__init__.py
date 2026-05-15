"""Canonical diagnostics namespace.

Diagnostics implementation lives under ``obsidiandroid.diagnostics``. Prefer
``obsidiandroid.diagnostics.<module>`` for new code. Legacy
``analysis.diagnostics.<module>`` imports remain thin identity shims for
compatibility.
"""

from __future__ import annotations

import importlib

from . import ablation_cohort_diagnostics
from . import alignment_gap_diagnostics
from . import cohort_foundation_export
from . import cohort_sample_id_audit
from . import cohort_vocabulary
from . import feature_builder_drop_trace
from . import feature_build_coverage_export
from . import feature_column_survival_export
from . import feature_lineage_report
from . import feature_matrix_gap_lineage
from . import family_label_taxonomy_audit
from . import reproducibility_workbench
from . import fused_permission_matrix_audit
from . import headline_evaluation_export
from . import output_artifact_policy
from . import rf_feature_importance_export
from . import split_ledger_resolve
from . import output_inventory
from . import permission_training_survival_audit

research_validity = importlib.import_module(f"{__name__}.research_validity")
hostile_audit = importlib.import_module(f"{__name__}.hostile_audit")

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
    "family_label_taxonomy_audit",
    "reproducibility_workbench",
    "fused_permission_matrix_audit",
    "headline_evaluation_export",
    "hostile_audit",
    "output_artifact_policy",
    "split_ledger_resolve",
    "output_inventory",
    "permission_training_survival_audit",
    "rf_feature_importance_export",
    "research_validity",
]
