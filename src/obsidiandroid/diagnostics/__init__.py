"""Canonical diagnostics namespace.

Diagnostics implementation lives under ``obsidiandroid.diagnostics``. Prefer
``obsidiandroid.diagnostics.<module>`` for imports and operator tooling.
"""

from __future__ import annotations

from importlib import import_module

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
    "vendor_feature_validation",
    "output_inventory",
    "permission_training_survival_audit",
    "rf_feature_importance_export",
    "research_validity",
]


def __getattr__(name: str):
    if name in __all__:
        return import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
