"""Validate strict reproducibility and publication bundle readiness for runs."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from config import app_config
from obsidiandroid.diagnostics.split_ledger_resolve import resolve_split_freeze_csv

REQUIRED_FILES = (
    "run_manifest.json",
)

# Split ledger: prefer ``split_freeze_headline_<run>.csv`` at check time (see loop below).
REQUIRED_DIAGNOSTICS_FILES = (
    "experiment_registry_{run_id}.json",
    "paper_mode_compliance_report_{run_id}.json",
    "run_paths_manifest_{run_id}.json",
    "cohort_filter_contract_{run_id}.json",
    "model_config_snapshot_{run_id}.json",
    "experiment_contract_snapshot_{run_id}.json",
    "run_summary_onepager_{run_id}.md",
)

REQUIRED_ARTIFACT_KEYS = (
    "split_audit_csv",
    "duplicate_sha_report_csv",
    "vendor_gate_debug_csv",
    "experiment_registry_json",
    "cohort_filter_contract_json",
    "model_config_snapshot_json",
    "run_summary_onepager_md",
    "experiment_contract_snapshot_json",
)

EXPECTED_MODELS = {"random_forest", "xgboost", "logistic_regression"}
EXPECTED_FIGURE_IDS = {
    "fig1_pipeline_architecture",
    "fig2_type_permission_heatmap",
    "fig3_dangerous_permission_distribution_by_type",
    "fig4_family_jsd_heatmap_top12",
    "fig5_confusion_matrix_random_forest",
}
EXPECTED_TABLE_IDS = {
    "table1_cohort_summary",
    "table2_malware_family_temporal_scope",
    "table3_model_comparison_rf_xgb_lr_fused",
    "table4_feature_ablation",
    "table5_dangerous_permission_stats_tests",
}
EXPECTED_BLOCKED_NON_PAPER_IDS = {
    "family_permission_heatmap_top12",
    "generic_consensus_vs_entropy",
    "per_family_performance_spread",
    "misclassified_samples_by_type",
}


def _exists(path: Path) -> bool:
    return path.exists() and path.is_file()


def _safe_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read CSV rows safely; return empty list on parse or file errors."""
    if not _exists(path):
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except Exception:
        return []


def _collect_registry_ids(rows: list[dict[str, str]], *, id_key: str) -> set[str]:
    """Collect canonical ids from registry rows."""
    out: set[str] = set()
    for row in rows:
        token = str(row.get(id_key, "")).strip()
        if token:
            out.add(token)
    return out


def _run_manifest_contract(path: Path) -> dict:
    """Loaded ``run_manifest.json`` at run root when present."""
    if not path.is_file():
        return {}
    return _safe_json(path)


def _paper_exports_checks_required(run_manifest_payload: dict) -> bool:
    """Paper export checks apply only when the run explicitly opted into paper_mode."""
    if not isinstance(run_manifest_payload, dict) or not run_manifest_payload:
        return True
    paper_mode = run_manifest_payload.get("paper_mode")
    if isinstance(paper_mode, dict) and "resolved_value" in paper_mode:
        return bool(paper_mode.get("resolved_value"))
    return True


def _permission_trends_bundle_required(run_manifest_payload: dict) -> bool:
    """Permission-trends bundle tables are validated only when the profile enabled them."""
    if not isinstance(run_manifest_payload, dict) or not run_manifest_payload:
        return True
    profile_params = run_manifest_payload.get("profile_params")
    if not isinstance(profile_params, dict):
        return True
    overrides = profile_params.get("runtime_overrides")
    if isinstance(overrides, dict) and "ENABLE_PERMISSION_TRENDS_REPORT" in overrides:
        return bool(overrides.get("ENABLE_PERMISSION_TRENDS_REPORT"))
    return True


def _safe_json(path: Path) -> dict:
    """Read JSON safely; return empty dict on failure."""
    if not _exists(path):
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _append_strict_paper_bundle_checks(
    checks: list[dict[str, str | bool]],
    *,
    run_root: Path,
    diagnostics: Path,
    run_id: str,
) -> None:
    """Figure/table registry and paper-facing diagnostic row-count contracts."""
    paper_dir = run_root / "paper_exports"
    figures_dir = paper_dir / "figures"
    tables_dir = paper_dir / "tables"
    docs_dir = paper_dir / "docs"
    figure_count = len(list(figures_dir.glob("*.png"))) if figures_dir.exists() else 0
    table_count = len(list(tables_dir.glob("*.csv"))) if tables_dir.exists() else 0
    checks.append(
        {
            "check": "paper_exports:figure_count_is_5",
            "pass": figure_count == 5,
            "path": str(figures_dir),
        }
    )
    checks.append(
        {
            "check": "paper_exports:table_count_is_5",
            "pass": table_count == 5,
            "path": str(tables_dir),
        }
    )
    checks.append(
        {
            "check": "paper_exports:docs_registry_present",
            "pass": _exists(docs_dir / "paper_figure_registry.csv")
            and _exists(docs_dir / "paper_table_registry.csv")
            and _exists(docs_dir / "paper_registry.json"),
            "path": str(docs_dir),
        }
    )
    figure_registry_rows = _safe_csv_rows(docs_dir / "paper_figure_registry.csv")
    table_registry_rows = _safe_csv_rows(docs_dir / "paper_table_registry.csv")
    figure_ids = _collect_registry_ids(figure_registry_rows, id_key="figure_id")
    table_ids = _collect_registry_ids(table_registry_rows, id_key="table_id")
    checks.append(
        {
            "check": "paper_exports:figure_ids_match_contract",
            "pass": figure_ids == EXPECTED_FIGURE_IDS,
            "path": str(docs_dir / "paper_figure_registry.csv"),
        }
    )
    checks.append(
        {
            "check": "paper_exports:table_ids_match_contract",
            "pass": table_ids == EXPECTED_TABLE_IDS,
            "path": str(docs_dir / "paper_table_registry.csv"),
        }
    )
    disallowed_name_tokens = ("topn", ".latest", "fallback")
    figure_names = [str(row.get("destination_filename", "")).strip().lower() for row in figure_registry_rows]
    table_names = [str(row.get("destination_filename", "")).strip().lower() for row in table_registry_rows]
    bad_names = [
        token
        for token in (figure_names + table_names)
        if token and any(mark in token for mark in disallowed_name_tokens)
    ]
    checks.append(
        {
            "check": "paper_exports:no_fallback_naming",
            "pass": len(bad_names) == 0,
            "path": ";".join(sorted(set(bad_names))),
        }
    )
    topn_table_names = [
        token for token in table_names if token and "topn" in token
    ]
    checks.append(
        {
            "check": "paper_exports:no_topN_table_filenames",
            "pass": len(topn_table_names) == 0,
            "path": ";".join(sorted(set(topn_table_names))),
        }
    )
    paper_registry_path = docs_dir / "paper_registry.json"
    paper_registry = _safe_json(paper_registry_path)
    paper_registry_rows = (
        paper_registry.get("artifacts", [])
        if isinstance(paper_registry, dict)
        else []
    )
    if not isinstance(paper_registry_rows, list):
        paper_registry_rows = []
    required_registry_fields = {
        "artifact_id",
        "run_id",
        "source_path",
        "destination_path",
        "sha256",
        "paper_allowed",
        "contract_version",
    }
    registry_fields_ok = True
    for row in paper_registry_rows:
        if not isinstance(row, dict):
            registry_fields_ok = False
            break
        missing_fields = [field for field in required_registry_fields if field not in row]
        if missing_fields:
            registry_fields_ok = False
            break
    checks.append(
        {
            "check": "paper_exports:paper_registry_schema_min_fields",
            "pass": bool(paper_registry_rows) and registry_fields_ok,
            "path": str(paper_registry_path),
        }
    )
    bad_registry_path_tokens: list[str] = []
    for row in paper_registry_rows:
        if not isinstance(row, dict):
            continue
        source_path = str(row.get("source_path", "")).strip().lower()
        destination_path = str(row.get("destination_path", "")).strip().lower()
        if any(token in destination_path for token in disallowed_name_tokens):
            bad_registry_path_tokens.append(destination_path)
        if "fallback" in source_path:
            bad_registry_path_tokens.append(source_path)
        if "__tmp__" in source_path or "__tmp__" in destination_path:
            bad_registry_path_tokens.append(f"{source_path};{destination_path}")
    checks.append(
        {
            "check": "paper_exports:paper_registry_no_fallback_paths",
            "pass": len(bad_registry_path_tokens) == 0,
            "path": ";".join(sorted(set(bad_registry_path_tokens))),
        }
    )
    allowed_rows = [
        row for row in paper_registry_rows
        if isinstance(row, dict) and bool(row.get("paper_allowed", False))
    ]
    blocked_rows = [
        row for row in paper_registry_rows
        if isinstance(row, dict) and not bool(row.get("paper_allowed", True))
    ]
    allowed_ids = {str(row.get("artifact_id", "")).strip() for row in allowed_rows if str(row.get("artifact_id", "")).strip()}
    blocked_ids = {str(row.get("artifact_id", "")).strip() for row in blocked_rows if str(row.get("artifact_id", "")).strip()}
    checks.append(
        {
            "check": "paper_exports:paper_registry_allowed_ids_match_contract",
            "pass": allowed_ids == (EXPECTED_FIGURE_IDS | EXPECTED_TABLE_IDS),
            "path": str(paper_registry_path),
        }
    )
    checks.append(
        {
            "check": "paper_exports:paper_registry_blocked_ids_present",
            "pass": EXPECTED_BLOCKED_NON_PAPER_IDS.issubset(blocked_ids),
            "path": str(paper_registry_path),
        }
    )

    model_csv = tables_dir / "model_comparison_rf_xgb_lr_fused.csv"
    model_rows = _safe_csv_rows(model_csv)
    model_set: set[str] = set()
    for row in model_rows:
        token = str(row.get("model", "")).strip().lower() or str(row.get("Model", "")).strip().lower()
        if token:
            model_set.add(token)
    checks.append(
        {
            "check": "paper_exports:model_set_rf_xgb_lr_only",
            "pass": model_set == EXPECTED_MODELS,
            "path": str(model_csv),
        }
    )

    jsd_pairs_csv = diagnostics / f"family_jsd_pairs_verification_{run_id}.csv"
    jsd_pair_rows = _safe_csv_rows(jsd_pairs_csv)
    checks.append(
        {
            "check": "diagnostics:jsd_pair_rows_66",
            "pass": len(jsd_pair_rows) == 66,
            "path": str(jsd_pairs_csv),
        }
    )

    selected_families_csv = diagnostics / f"selected_families_visual_{run_id}.csv"
    selected_rows = _safe_csv_rows(selected_families_csv)
    checks.append(
        {
            "check": "diagnostics:selected_visual_families_12",
            "pass": len(selected_rows) == 12,
            "path": str(selected_families_csv),
        }
    )

    trained_registry_csv = diagnostics / f"trained_family_registry_{run_id}.csv"
    trained_rows = _safe_csv_rows(trained_registry_csv)
    included_rows = [
        row
        for row in trained_rows
        if str(row.get("included_in_training", "")).strip() in {"1", "true", "True"}
    ]
    min_support_ok = bool(included_rows) and all(
        int(str(row.get("sample_count", "0")).strip() or "0") >= 20 for row in included_rows
    )
    checks.append(
        {
            "check": "diagnostics:trained_families_min_support_20",
            "pass": min_support_ok,
            "path": str(trained_registry_csv),
        }
    )


def _resolve_run_root(*, output_root: Path, run_id: str) -> Path:
    """Resolve and validate run root under the configured output root."""
    root = output_root.resolve()
    run_root = (root / "runs" / run_id).resolve()
    if root not in run_root.parents:
        raise ValueError(f"Run root escapes output_root: run_root={run_root} output_root={root}")
    return run_root


def check_run(
    run_id: str,
    *,
    output_root: Path | None = None,
    bundle_only: bool = False,
) -> dict:
    root = (
        Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")))
        if output_root is None
        else Path(output_root)
    )
    run_root = _resolve_run_root(output_root=root, run_id=run_id)
    diagnostics = run_root / "diagnostics"
    checks: list[dict[str, str | bool]] = []
    run_manifest_for_gates = _run_manifest_contract(run_root / "run_manifest.json")

    if not bundle_only:
        for filename in REQUIRED_FILES:
            target = run_root / filename
            checks.append({"check": f"file:{filename}", "pass": _exists(target), "path": str(target)})
        for template in REQUIRED_DIAGNOSTICS_FILES:
            filename = template.format(run_id=run_id)
            target = diagnostics / filename
            checks.append({"check": f"diag:{filename}", "pass": _exists(target), "path": str(target)})
        split_path = resolve_split_freeze_csv(diagnostics, run_id)
        checks.append(
            {
                "check": "diag:split_ledger_csv(headline_preferred_or_audit_mirror)",
                "pass": split_path is not None,
                "path": str(split_path) if split_path is not None else str(diagnostics),
            }
        )

        manifest_path = diagnostics / f"run_paths_manifest_{run_id}.json"
        manifest_payload = {}
        if manifest_path.exists():
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifacts = manifest_payload.get("artifacts", {}) if isinstance(manifest_payload, dict) else {}
        for artifact_key in REQUIRED_ARTIFACT_KEYS:
            entry = artifacts.get(artifact_key, {}) if isinstance(artifacts, dict) else {}
            sha = str(entry.get("sha256", "")) if isinstance(entry, dict) else ""
            checks.append(
                {
                    "check": f"artifact:{artifact_key}",
                    "pass": bool(entry) and bool(sha),
                    "path": str(entry.get("relpath", "")) if isinstance(entry, dict) else "",
                }
            )

        run_manifest_payload = run_manifest_for_gates
        require_paper = _paper_exports_checks_required(run_manifest_payload)
        if not require_paper:
            checks.append(
                {
                    "check": "paper_exports:skipped_non_paper_mode",
                    "pass": True,
                    "path": str(run_root / "run_manifest.json"),
                }
            )

        else:
            _append_strict_paper_bundle_checks(
                checks,
                run_root=run_root,
                diagnostics=diagnostics,
                run_id=run_id,
            )

        cm_prov_csv = diagnostics / f"confusion_matrix_provenance_{run_id}.csv"
        cm_rows = _safe_csv_rows(cm_prov_csv)
        cm_ok = (
            len(cm_rows) == 1
            and str(cm_rows[0].get("eval_source", "")).strip() == "test_set"
            and str(cm_rows[0].get("model_name", "")).strip() == "random_forest"
        )
        checks.append(
            {
                "check": "diagnostics:confusion_provenance_testset_rf",
                "pass": cm_ok,
                "path": str(cm_prov_csv),
            }
        )

        taxonomy_summary_path = diagnostics / f"taxonomy_consistency_summary_{run_id}.json"
        taxonomy_payload = {}
        if _exists(taxonomy_summary_path):
            try:
                taxonomy_payload = json.loads(taxonomy_summary_path.read_text(encoding="utf-8"))
            except Exception:
                taxonomy_payload = {}
        checks.append(
            {
                "check": "diagnostics:taxonomy_type_rows_evaluated_gt_zero",
                "pass": int(taxonomy_payload.get("type_rows_evaluated", 0) or 0) > 0,
                "path": str(taxonomy_summary_path),
            }
        )

    # Bundle governance checks (only when permission-trends stage is enabled for the profile).
    perm_bundle_required = _permission_trends_bundle_required(run_manifest_for_gates)
    if not perm_bundle_required:
        checks.append(
            {
                "check": "bundle:skipped_permission_trends_disabled",
                "pass": True,
                "path": str(run_root / "run_manifest.json"),
            }
        )
    else:
        bundle_dir = run_root / "bundles" / "permission_trends"
        contracts_dir = bundle_dir / "contracts"
        bundle_manifest_path = contracts_dir / "permission_trends_bundle_manifest.json"
        bundle_inventory_path = contracts_dir / "permission_trends_table_inventory.csv"
        bundle_manifest = _safe_json(bundle_manifest_path)
        bundle_artifacts = bundle_manifest.get("artifacts", []) if isinstance(bundle_manifest, dict) else []
        if not isinstance(bundle_artifacts, list):
            bundle_artifacts = []
        table_entries = [
            entry for entry in bundle_artifacts
            if isinstance(entry, dict) and str(entry.get("category", "")).strip() == "table"
        ]
        checks.append(
            {
                "check": "bundle:table_inventory_exists",
                "pass": _exists(bundle_inventory_path),
                "path": str(bundle_inventory_path),
            }
        )
        inventory_rows = _safe_csv_rows(bundle_inventory_path)
        checks.append(
            {
                "check": "bundle:table_inventory_non_empty",
                "pass": len(inventory_rows) > 0,
                "path": str(bundle_inventory_path),
            }
        )
        inventory_ids = {str(row.get("artifact_id", "")).strip() for row in inventory_rows if str(row.get("artifact_id", "")).strip()}
        manifest_table_ids = {str(entry.get("artifact_id", "")).strip() for entry in table_entries if str(entry.get("artifact_id", "")).strip()}
        checks.append(
            {
                "check": "bundle:table_inventory_consistent_with_manifest",
                "pass": bool(inventory_ids) and inventory_ids == manifest_table_ids,
                "path": str(bundle_manifest_path),
            }
        )
        duplicate_table_ids = sorted(
            token
            for token in manifest_table_ids
            if sum(
                1
                for entry in table_entries
                if str(entry.get("artifact_id", "")).strip() == token
            )
            > 1
        )
        checks.append(
            {
                "check": "bundle:table_artifact_ids_unique",
                "pass": len(duplicate_table_ids) == 0,
                "path": ",".join(duplicate_table_ids),
            }
        )
        diagnostic_entries = [
            entry for entry in table_entries
            if str(entry.get("role", "")).strip() == "diagnostic_table"
        ]
        checks.append(
            {
                "check": "bundle:no_diagnostic_table_roles_in_bundle_tables",
                "pass": len(diagnostic_entries) == 0,
                "path": str(bundle_manifest_path),
            }
        )
        topn_entries = [
            entry for entry in table_entries
            if "topn" in str(entry.get("filename", "")).strip().lower()
            or "topn" in str(entry.get("artifact_id", "")).strip().lower()
        ]
        checks.append(
            {
                "check": "bundle:no_topN_table_filenames",
                "pass": len(topn_entries) == 0,
                "path": str(bundle_manifest_path),
            }
        )
    
        # Hard gate: run_id must exist for run-scoped bundle table rows.
        missing_run_id_files: list[str] = []
        for entry in table_entries:
            rel = str(entry.get("relative_path", "")).strip()
            if not rel:
                continue
            path = (bundle_dir / rel).resolve()
            if not path.exists():
                continue
            rows = _safe_csv_rows(path)
            if not rows:
                continue
            first = rows[0]
            if "run_id" not in first:
                missing_run_id_files.append(str(path))
        checks.append(
            {
                "check": "bundle:table_rows_include_run_id",
                "pass": len(missing_run_id_files) == 0,
                "path": ";".join(missing_run_id_files),
            }
        )
    
    passed = all(bool(item.get("pass")) for item in checks)
    return {"run_id": run_id, "passed": passed, "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evidence bundle readiness checker")
    parser.add_argument("--run-ids", required=True, help="Comma-separated run IDs")
    parser.add_argument(
        "--output-root",
        default=str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")),
        help="Output root containing runs/ (default: DEFAULT_OUTPUT_DIR).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON report path",
    )
    parser.add_argument(
        "--bundle-only",
        action="store_true",
        help="Validate bundle governance checks only (skip publication export checks).",
    )
    args = parser.parse_args()

    run_ids = [token.strip() for token in str(args.run_ids).split(",") if token.strip()]
    if not run_ids:
        raise SystemExit("No run IDs supplied.")

    output_root = Path(str(args.output_root))
    run_reports = [
        check_run(run_id, output_root=output_root, bundle_only=bool(args.bundle_only))
        for run_id in run_ids
    ]
    overall = all(bool(report.get("passed")) for report in run_reports)
    payload = {
        "overall_status": "pass" if overall else "fail",
        "run_ids": run_ids,
        "mode": "bundle_only" if bool(args.bundle_only) else "full",
        "reports": run_reports,
    }
    out_path = (
        Path(str(args.output))
        if args.output
        else output_root / "diagnostics" / "evidence_bundle_check.latest.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote: {out_path}")
    print(f"Overall: {payload['overall_status']}")
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
