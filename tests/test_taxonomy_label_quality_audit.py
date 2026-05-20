"""Tests for taxonomy label quality audit path resolution."""

from __future__ import annotations

import json

from obsidiandroid.diagnostics.hostile_audit.taxonomy_label_quality_audit import (
    write_taxonomy_label_quality_audit,
)


def test_taxonomy_label_quality_audit_uses_global_latest_summary_when_run_local_latest_is_pruned(
    make_run_diagnostics_layout,
) -> None:
    """Audit markdown should resolve the global latest taxonomy summary mirror."""
    output_root, diagnostics_dir, global_diag = make_run_diagnostics_layout("run_tax")

    (global_diag / "taxonomy_consistency_summary.latest.json").write_text(
        json.dumps(
            {
                "rows_evaluated": 10,
                "type_rows_evaluated": 8,
                "family_rows_evaluated": 10,
                "type_missing_label_count": 1,
                "type_noncanonical_count": 0,
                "type_mismatch_count": 2,
                "family_label_mismatch_count": 0,
                "taxonomy_mismatch_count": 3,
                "prediction_error_count": 1,
            }
        ),
        encoding="utf-8",
    )

    out = write_taxonomy_label_quality_audit(diagnostics_dir=diagnostics_dir, run_id="run_tax")

    text = out.read_text(encoding="utf-8")
    assert "taxonomy_consistency_summary.latest.json" in text
    assert "| taxonomy_mismatch_count | 3 |" in text
