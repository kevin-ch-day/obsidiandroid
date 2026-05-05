"""Diagnostics facade: re-exports selected ``analysis.diagnostics`` modules.

Implementation remains under ``analysis/diagnostics/``. Prefer this package for new
imports that should align with the installable ``obsidiandroid`` namespace::

    from obsidiandroid.diagnostics import output_inventory
    output_inventory.evaluate_paper_safe_status(...)

Exposed modules match ``analysis.diagnostics.<name>`` (same module objects).
Operator scripts prepend repo ``src/`` to ``sys.path`` when needed (see Pass 34).
"""

from __future__ import annotations

from analysis.diagnostics import ablation_cohort_diagnostics
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
    "output_artifact_policy",
    "output_inventory",
    "permission_training_survival_audit",
]
