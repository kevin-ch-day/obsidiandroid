"""Export publication-ready CSV and LaTeX tables for a run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import scripts.runtime_bootstrap  # noqa: F401

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()

import pandas as pd

from obsidiandroid.reporting.latex_tables import (
    LatexTableSpec,
    build_cohort_summary_table,
    build_dangerous_stats_table,
    build_family_temporal_scope_table,
    build_feature_ablation_table,
    build_model_comparison_table,
    write_tabular,
)


def _resolve_run_root(*, output_root: Path, run_id: str) -> Path:
    """Resolve run root and ensure it is inside output root."""
    root = output_root.resolve()
    run_root = (root / "runs" / run_id).resolve()
    if root not in run_root.parents:
        raise ValueError(f"Run root {run_root} is outside output root {root}")
    if not run_root.exists():
        raise FileNotFoundError(f"Run root not found: {run_root}")
    return run_root


def _build_cohort_summary_from_snapshot(snapshot_df: pd.DataFrame) -> pd.DataFrame:
    """Build canonical cohort summary table from analysis snapshot."""
    family_counts = snapshot_df["family_canonical"].astype(str).value_counts()
    timestamps = pd.to_datetime(snapshot_df.get("effective_first_seen_at_utc"), errors="coerce", utc=True)
    years = timestamps.dt.year.dropna().astype(int)
    rows = [
        {"Metric": "Total Samples", "Value": len(snapshot_df)},
        {"Metric": "Unique Families", "Value": int(snapshot_df["family_canonical"].nunique())},
        {"Metric": "Malware Types", "Value": int(snapshot_df["type_slug"].nunique())},
        {
            "Metric": "Largest Family Share",
            "Value": float(family_counts.iloc[0] / max(len(snapshot_df), 1)) if len(family_counts) else 0.0,
        },
    ]
    if len(years):
        rows.append({"Metric": "Time Window Start", "Value": int(years.min())})
        rows.append({"Metric": "Time Window End", "Value": int(years.max())})
    return pd.DataFrame(rows)


def _build_family_temporal_scope_from_snapshot(snapshot_df: pd.DataFrame) -> pd.DataFrame:
    """Build family-level temporal scope table from analysis snapshot."""
    work = snapshot_df[["family_canonical", "effective_first_seen_at_utc"]].copy()
    work["ts"] = pd.to_datetime(work["effective_first_seen_at_utc"], errors="coerce", utc=True)
    work = work.dropna(subset=["ts"])
    grouped = (
        work.groupby("family_canonical", as_index=False)
        .agg(sample_count=("family_canonical", "count"), first_seen=("ts", "min"), last_seen=("ts", "max"))
        .sort_values(["sample_count", "family_canonical"], ascending=[False, True], kind="mergesort")
    )
    grouped["first_seen"] = grouped["first_seen"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    grouped["last_seen"] = grouped["last_seen"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return grouped


def export_tables(*, run_id: str, output_root: Path, destination: Path) -> dict[str, Any]:
    """Export publication-ready table artifacts for one run."""
    run_root = _resolve_run_root(output_root=output_root, run_id=run_id)
    diagnostics = run_root / "diagnostics"
    bundle_tables = run_root / "bundles" / "permission_trends" / "tables"

    table_csv_dir = destination / "tables_csv"
    table_tex_dir = destination / "tables_latex"
    docs_dir = destination / "docs"
    for path in (table_csv_dir, table_tex_dir, docs_dir):
        path.mkdir(parents=True, exist_ok=True)

    # Remove known legacy duplicate names so publication directories stay canonical-only.
    legacy_tex = [
        table_tex_dir / "table_model_comparison_cohort_summary.tex",
        table_tex_dir / "table_malware_family_temporal_scope.tex",
    ]
    for old_path in legacy_tex:
        if old_path.exists():
            old_path.unlink()

    snapshot_path = diagnostics / "analysis_snapshot.latest.csv"
    model_path = diagnostics / f"model_comparison_summary_{run_id}.csv"
    ablation_path = diagnostics / "ablation_summary.csv"
    dangerous_path = bundle_tables / "dangerous_stats_tests.latest.csv"

    missing = [path for path in (snapshot_path, model_path, ablation_path, dangerous_path) if not path.exists()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise FileNotFoundError(f"Missing required source files: {missing_text}")

    snapshot_df = pd.read_csv(snapshot_path)
    model_df = pd.read_csv(model_path)
    ablation_df = pd.read_csv(ablation_path)
    dangerous_df = pd.read_csv(dangerous_path)

    table1_df = build_cohort_summary_table(_build_cohort_summary_from_snapshot(snapshot_df))
    table2_df = build_family_temporal_scope_table(_build_family_temporal_scope_from_snapshot(snapshot_df))
    table3_df = build_model_comparison_table(model_df)
    table4_df = build_feature_ablation_table(ablation_df)
    table5_df = build_dangerous_stats_table(dangerous_df)

    csv_map: dict[str, Path] = {
        "table1_cohort_summary": table_csv_dir / "table1_cohort_summary.csv",
        "table2_malware_family_temporal_scope": table_csv_dir / "table2_malware_family_temporal_scope.csv",
        "table3_model_comparison_rf_xgb_lr_fused": table_csv_dir / "table3_model_comparison_rf_xgb_lr_fused.csv",
        "table4_feature_ablation": table_csv_dir / "table4_feature_ablation.csv",
        "table5_dangerous_permission_stats_tests": table_csv_dir / "table5_dangerous_permission_stats_tests.csv",
    }
    tex_map: dict[str, Path] = {
        "table1_cohort_summary": table_tex_dir / "table_cohort_summary.tex",
        "table2_malware_family_temporal_scope": table_tex_dir / "table_family_temporal_scope.tex",
        "table3_model_comparison_rf_xgb_lr_fused": table_tex_dir / "table_model_comparison.tex",
        "table4_feature_ablation": table_tex_dir / "table_feature_ablation.tex",
        "table5_dangerous_permission_stats_tests": table_tex_dir / "table_dangerous_permission_stats.tex",
    }
    table_frames: dict[str, pd.DataFrame] = {
        "table1_cohort_summary": table1_df,
        "table2_malware_family_temporal_scope": table2_df,
        "table3_model_comparison_rf_xgb_lr_fused": table3_df,
        "table4_feature_ablation": table4_df,
        "table5_dangerous_permission_stats_tests": table5_df,
    }

    registry_rows: list[dict[str, Any]] = []
    for artifact_id, frame in table_frames.items():
        csv_path = csv_map[artifact_id]
        tex_path = tex_map[artifact_id]
        frame.to_csv(csv_path, index=False)
        align = "l" + ("c" * (len(frame.columns) - 1))
        write_tabular(frame, output_path=tex_path, spec=LatexTableSpec(align=align, use_booktabs=True))
        registry_rows.append(
            {
                "artifact_id": artifact_id,
                "run_id": run_id,
                "csv_path": str(csv_path.resolve()),
                "tex_path": str(tex_path.resolve()),
            }
        )

    registry_payload = {
        "run_id": run_id,
        "contract": "publication_tables.v1",
        "tables": registry_rows,
    }
    registry_path = docs_dir / "publication_tables_registry.json"
    registry_path.write_text(json.dumps(registry_payload, indent=2, sort_keys=True), encoding="utf-8")
    return registry_payload


def _parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(description="Export publication-ready CSV/LaTeX tables for a run.")
    parser.add_argument("--run-id", required=True, help="Pipeline run ID.")
    parser.add_argument("--output-root", default="output", help="Output root directory. Defaults to output.")
    parser.add_argument(
        "--destination",
        default="publication_exports",
        help="Run-relative export directory name. Defaults to publication_exports.",
    )
    return parser


def main() -> int:
    """CLI entry point."""
    args = _parser().parse_args()
    run_id = str(args.run_id).strip()
    if not run_id:
        raise ValueError("run-id must be non-empty")
    output_root = Path(str(args.output_root)).resolve()
    run_root = _resolve_run_root(output_root=output_root, run_id=run_id)
    destination = run_root / str(args.destination).strip()
    payload = export_tables(run_id=run_id, output_root=output_root, destination=destination)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
