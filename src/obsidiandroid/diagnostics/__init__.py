"""Diagnostics facade: re-exports selected ``analysis.diagnostics`` modules.

Implementation remains under ``analysis/diagnostics/``. Prefer this package for new
imports that should align with the installable ``obsidiandroid`` namespace::

    from obsidiandroid.diagnostics.output_inventory import evaluate_paper_safe_status

Or use the submodule aliases attached here (same module objects as
``analysis.diagnostics.*``).
"""

from __future__ import annotations

from analysis.diagnostics import feature_lineage_report
from analysis.diagnostics import output_artifact_policy
from analysis.diagnostics import output_inventory

__all__ = [
    "feature_lineage_report",
    "output_artifact_policy",
    "output_inventory",
]
