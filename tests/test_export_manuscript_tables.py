"""End-to-end tests for publication table export script."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.research import export_publication_tables as export_manuscript_tables


def _write_minimum_run_sources(root: Path, run_id: str) -> None:
    run_root = root / "runs" / run_id
    diagnostics = run_root / "diagnostics"
    bundle_tables = run_root / "bundles" / "permission_trends" / "tables"
    diagnostics.mkdir(parents=True, exist_ok=True)
    bundle_tables.mkdir(parents=True, exist_ok=True)

    pd.DataFrame(
        [
            {
                "sample_id": 1,
                "family_canonical": "Irata",
                "type_slug": "banker",
                "effective_first_seen_at_utc": "2020-05-01T00:00:00Z",
            },
            {
                "sample_id": 2,
                "family_canonical": "Joker",
                "type_slug": "adware",
                "effective_first_seen_at_utc": "2026-01-03T00:00:00Z",
            },
        ]
    ).to_csv(diagnostics / "analysis_snapshot.latest.csv", index=False)

    pd.DataFrame(
        [
            {
                "Model": "random_forest",
                "Accuracy": 0.9761,
                "Precision": 0.9751,
                "Recall": 0.9761,
                "F1-Score": 0.9750,
                "Macro F1-Score": 0.9530,
                "Rank": 1,
            },
            {
                "Model": "xgboost",
                "Accuracy": 0.9681,
                "Precision": 0.9684,
                "Recall": 0.9681,
                "F1-Score": 0.9665,
                "Macro F1-Score": 0.9412,
                "Rank": 2,
            },
        ]
    ).to_csv(diagnostics / f"model_comparison_summary_{run_id}.csv", index=False)

    pd.DataFrame(
        [
            {
                "experiment": "vendor_permissions_fused",
                "model": "random_forest",
                "accuracy": 0.9761,
                "macro_precision": 0.9584,
                "macro_recall": 0.9568,
                "macro_f1_score": 0.9566,
            }
        ]
    ).to_csv(diagnostics / "ablation_summary.csv", index=False)

    pd.DataFrame(
        [
            {
                "run_id": run_id,
                "test_type": "kruskal_wallis",
                "metric": "dangerous_count_strict",
                "group_a": "all",
                "group_b": "all",
                "statistic": 149.7427,
                "p_value": 1.5e-30,
                "p_value_fdr_bh": 1.5e-30,
                "effect_size": None,
                "effect_size_name": "epsilon_squared",
                "method_notes": "global_nonparametric",
            }
        ]
    ).to_csv(bundle_tables / "dangerous_stats_tests.latest.csv", index=False)


def test_export_tables_produces_tex_with_expected_structure(tmp_path: Path) -> None:
    """Export should produce full manuscript table set and registry."""
    output_root = tmp_path / "output"
    run_id = "20260307T000000Z__abcdef"
    _write_minimum_run_sources(output_root, run_id)

    dest = output_root / "runs" / run_id / "manuscript_exports"
    payload = export_manuscript_tables.export_tables(
        run_id=run_id,
        output_root=output_root,
        destination=dest,
    )
    assert payload["run_id"] == run_id
    assert len(payload["tables"]) == 5

    model_tex = (dest / "tables_latex" / "table_model_comparison.tex").read_text(encoding="utf-8")
    assert r"\textbf{Random Forest}" in model_tex
    assert "Macro-F1" in model_tex

    ablation_tex = (dest / "tables_latex" / "table_feature_ablation.tex").read_text(encoding="utf-8")
    assert "Feature Set" in ablation_tex
    assert "Macro Precision" in ablation_tex
    assert "Random Forest" in ablation_tex

    dangerous_tex = (dest / "tables_latex" / "table_dangerous_permission_stats.tex").read_text(encoding="utf-8")
    assert "Metric" in dangerous_tex
    assert "p-value" in dangerous_tex
    assert "Effect Name" in dangerous_tex

    temporal_tex = (dest / "tables_latex" / "table_family_temporal_scope.tex").read_text(encoding="utf-8")
    assert "First Seen" in temporal_tex
    assert "2020" in temporal_tex

    cohort_tex = (dest / "tables_latex" / "table_cohort_summary.tex").read_text(encoding="utf-8")
    assert "Largest Family Share" in cohort_tex
    assert "50.0\\%" in cohort_tex

    reg = json.loads((dest / "docs" / "publication_tables_registry.json").read_text(encoding="utf-8"))
    assert reg["run_id"] == run_id
    assert len(reg["tables"]) == 5
