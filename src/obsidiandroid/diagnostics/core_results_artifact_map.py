"""Map a finished run's filesystem artifacts onto Core Results v1 tables.

Read-only inventory for Phase 2D planning. Does not write Core or Erebus.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.reporting.type_permission_pattern_report import (
    detect_source_run_status,
    resolve_git_commit,
    sha256_file,
)

MAP_VERSION = "1.0.0"
SCHEMA_VERSION = "core_results_artifact_map_v1"

# Planned Core Results v1 surfaces -> candidate artifact globs relative to run_root.
CORE_RESULT_SURFACE_SPECS: list[dict[str, Any]] = [
    {
        "core_table": "run_stage",
        "status_if_missing": "missing",
        "candidates": [
            "diagnostics/run_observability_summary.json",
            "diagnostics/pipeline_events.jsonl",
            "run_manifest.json",
        ],
    },
    {
        "core_table": "feature_contract",
        "status_if_missing": "missing",
        "candidates": [
            "diagnostics/modality_method_contract_*.json",
            "diagnostics/feature_column_survival_*.csv",
            "diagnostics/permission_vocabulary_reconciliation_*.md",
        ],
    },
    {
        "core_table": "split_ledger",
        "status_if_missing": "missing",
        "candidates": [
            "diagnostics/split_freeze_headline_*.csv",
            "diagnostics/holdout_calibration/split_class_accounting_*.csv",
        ],
    },
    {
        "core_table": "model_execution",
        "status_if_missing": "missing",
        "candidates": [
            "models/*/logistic_regression_classifier_model_metadata.json",
            "models/*/*_classifier_model_metadata.json",
            "diagnostics/model_comparison_summary_*.csv",
        ],
    },
    {
        "core_table": "model_metric",
        "status_if_missing": "missing",
        "candidates": [
            "diagnostics/model_comparison_summary_*.csv",
            "diagnostics/run_observability_summary.json",
        ],
    },
    {
        "core_table": "prediction",
        "status_if_missing": "missing",
        "candidates": [
            "diagnostics/headline_test_predictions_*.csv",
            "diagnostics/prediction_errors_*.csv",
        ],
    },
    {
        "core_table": "experiment",
        "status_if_missing": "not_exercised",
        "candidates": [
            "diagnostics/feature_set_ablation_summary_*.csv",
            "diagnostics/ablation_summary_*.csv",
        ],
        "notes": "Ablation disabled on this profile (ENABLE_ABLATION_EXPERIMENTS=False).",
    },
    {
        "core_table": "experiment_metric",
        "status_if_missing": "not_exercised",
        "candidates": [
            "diagnostics/feature_set_ablation_summary_*.csv",
            "diagnostics/ablation_summary_*.csv",
        ],
        "notes": "Requires experiment rows; absent when ablations are disabled.",
    },
    {
        "core_table": "permission_measure",
        "status_if_missing": "missing",
        "candidates": [
            "bundles/permission_trends/tables/permission_prevalence_by_type_*.csv",
            "bundles/permission_trends/tables/permission_type_enrichment_*.csv",
            "diagnostics/type_permission_pattern_report/type_inventory_*.csv",
            "diagnostics/type_permission_pairwise/pairwise_headline_*.csv",
        ],
    },
    {
        "core_table": "label_contract",
        "status_if_missing": "missing",
        "candidates": [
            "diagnostics/label_contract_*.md",
            "diagnostics/label_contract_*.json",
            "diagnostics/taxonomy_target_surfaces_*.json",
        ],
    },
    {
        "core_table": "label_assignment",
        "status_if_missing": "missing",
        "candidates": [
            "obsidiandroid_outputs.xlsx",
            "diagnostics/aligned_labels_*.csv",
            "diagnostics/prediction_errors_*.csv",
            "diagnostics/type_guard_suppression_audit/type_guard_suppressions_*.csv",
        ],
    },
    {
        "core_table": "confusion_cell",
        "status_if_missing": "missing",
        "candidates": [
            "diagnostics/top_confusion_pairs.csv",
            "diagnostics/confusion_within_vs_cross_type_*.csv",
            "conf_matrices/*",
        ],
    },
]


def _expand_candidates(run_root: Path, patterns: list[str]) -> list[Path]:
    found: list[Path] = []
    for pattern in patterns:
        if any(ch in pattern for ch in "*?[]"):
            found.extend(sorted(run_root.glob(pattern)))
        else:
            path = run_root / pattern
            if path.exists():
                found.append(path)
    # Prefer files over directories; unique preserve order
    out: list[Path] = []
    seen: set[str] = set()
    for path in found:
        key = str(path.resolve())
        if key in seen:
            continue
        if path.is_file():
            seen.add(key)
            out.append(path)
    return out


def _row_bound(path: Path) -> int | None:
    try:
        if path.suffix.lower() == ".csv":
            # cheap line count minus header
            with path.open("rb") as handle:
                n = sum(1 for _ in handle)
            return max(0, n - 1)
        if path.suffix.lower() == ".json":
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                return len(payload)
            if isinstance(payload, dict):
                return 1
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    return None


def map_core_results_artifacts(run_root: Path, run_id: str) -> pd.DataFrame:
    """Return one row per Core Results v1 table with best available sources."""
    run_root = Path(run_root)
    rows: list[dict[str, Any]] = []
    for spec in CORE_RESULT_SURFACE_SPECS:
        matches = _expand_candidates(run_root, list(spec["candidates"]))
        # Prefer run-id stamped paths when present.
        stamped = [p for p in matches if run_id in p.name]
        chosen = stamped or matches
        primary = chosen[0] if chosen else None
        status = "present" if primary is not None else str(spec.get("status_if_missing") or "missing")
        rows.append(
            {
                "core_table": spec["core_table"],
                "mapping_status": status,
                "primary_artifact": str(primary.relative_to(run_root)) if primary else "",
                "primary_sha256": sha256_file(primary) if primary and primary.is_file() else "",
                "approx_row_bound": _row_bound(primary) if primary else None,
                "artifact_count": int(len(chosen)),
                "artifact_list": ";".join(str(p.relative_to(run_root)) for p in chosen[:12]),
                "notes": str(spec.get("notes") or ""),
                "mutable_slot_pointer_risk": bool(
                    primary is not None
                    and run_id not in primary.name
                    and primary.suffix.lower() in {".joblib", ".xlsx"}
                ),
            }
        )
    return pd.DataFrame(rows)


def compose_core_results_artifact_map(
    *,
    run_root: Path,
    run_id: str,
    output_dir: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Write Core Results v1 artifact map for a finished run."""
    run_root = Path(run_root)
    frame = map_core_results_artifacts(run_root, run_id)
    run_status = detect_source_run_status(run_root)
    out_dir = Path(output_dir) if output_dir else run_root / "diagnostics" / "core_results_artifact_map"
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / f"core_results_artifact_map_{run_id}.csv"
    frame.to_csv(csv_path, index=False)
    frame.to_csv(out_dir / "core_results_artifact_map.latest.csv", index=False)

    present = int((frame["mapping_status"] == "present").sum())
    missing = int((frame["mapping_status"] == "missing").sum())
    not_exercised = int((frame["mapping_status"] == "not_exercised").sum())
    mutable = int(frame["mutable_slot_pointer_risk"].astype(bool).sum())

    md = [
        f"# Core Results v1 artifact map (`{run_id}`)",
        "",
        f"- Report status: **{run_status['report_status']}**",
        f"- Map version: `{MAP_VERSION}`",
        f"- Surfaces present: **{present}** · missing: **{missing}** · not exercised: **{not_exercised}**",
        f"- Mutable slot-pointer risks (un-stamped model/xlsx paths): **{mutable}**",
        "",
        "This is a **read-only planning inventory**. It does not enable Core persistence,",
        "does not apply migration 0005, and does not write analytical results to Core.",
        "",
        "| core_table | status | primary artifact | rows | mutable? |",
        "|---|---|---|---:|---|",
    ]
    for row in frame.itertuples(index=False):
        md.append(
            f"| `{row.core_table}` | {row.mapping_status} | `{row.primary_artifact}` | "
            f"{row.approx_row_bound if row.approx_row_bound is not None else '—'} | "
            f"{'yes' if row.mutable_slot_pointer_risk else 'no'} |"
        )
    md.extend(
        [
            "",
            "## Phase 2D gate",
            "",
            "- Use this map to define natural identities, row bounds, and `core_artifact` roles.",
            "- Do **not** write this run into Core while partial `0004` remains unresolved.",
            "- `experiment` / `experiment_metric` stay `not_exercised` until an ablation run exists.",
            "",
        ]
    )
    report_path = out_dir / f"core_results_artifact_map_{run_id}.md"
    report_path.write_text("\n".join(md) + "\n", encoding="utf-8")

    manifest = {
        "map_version": MAP_VERSION,
        "report_schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": resolve_git_commit(repo_root),
        "run_id": run_id,
        "report_status": run_status["report_status"],
        "source_run_status": run_status["source_run_status"],
        "present_count": present,
        "missing_count": missing,
        "not_exercised_count": not_exercised,
        "mutable_slot_pointer_risk_count": mutable,
        "core_persistence_enabled": False,
        "writes_to_core": False,
        "writes_to_erebus": False,
        "csv": str(csv_path),
        "report_markdown": str(report_path),
        "output_dir": str(out_dir),
        "csv_sha256": sha256_file(csv_path),
        "report_sha256": sha256_file(report_path),
    }
    (out_dir / f"core_results_artifact_map_manifest_{run_id}.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


__all__ = [
    "CORE_RESULT_SURFACE_SPECS",
    "MAP_VERSION",
    "compose_core_results_artifact_map",
    "map_core_results_artifacts",
]
