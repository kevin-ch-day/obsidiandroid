"""Permission trends bundle manifest generation and artifact directory layout."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.pipeline.permission_trends.constants import (
    ARTIFACT_GROUP_CONTRACTS,
    ARTIFACT_GROUP_DOCS,
    ARTIFACT_GROUP_FIGURES,
    ARTIFACT_GROUP_TABLES,
    BUNDLE_CONTRACT_NAME,
    BUNDLE_CONTRACT_VERSION,
)


def resolve_bundle_artifact_dir(bundle_dir: Path, artifact_group: str) -> Path:
    """Resolve/create grouped subdirectory for permission_trends artifacts."""
    out_dir = bundle_dir / str(artifact_group).strip()
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def canonical_bundle_artifact_id_from_path(path: Path, *, category: str) -> str:
    """Derive canonical artifact id from bundle path."""
    stem = str(path.stem)
    if stem.endswith(".latest"):
        stem = stem[: -len(".latest")]

    aliases = {
        "dangerous_distribution_by_type": "dangerous_permission_distribution_by_type",
        "family_jsd_matrix": "family_jsd_matrix",
        "permission_coverage_report": "permission_coverage_report",
        "permission_discriminability_rank": "permission_discriminability_rank",
        "type_permission_prevalence": "type_permission_prevalence",
        "type_permission_entropy": "type_permission_entropy",
        "type_permission_heatmap": "type_permission_heatmap",
    }
    for key, value in aliases.items():
        if stem == key:
            stem = value
            break
    if category == "contract":
        if stem == "permission_alias_map":
            suffix = str(path.suffix).lower()
            if suffix == ".csv":
                return "permission_alias_map_csv"
            if suffix == ".json":
                return "permission_alias_map_json"
    if category == "doc" and stem == "consensus_correlation_report":
        return "consensus_correlation_report_doc"
    return stem


def infer_bundle_artifact_parameters(
    artifact_id: str,
    *,
    top_families_visual: int,
    min_visual_family_support: int,
    top_permissions: int,
) -> dict[str, Any]:
    """Infer parameter payload for bundle artifact manifest entry."""
    params: dict[str, Any] = {}
    if "top" in artifact_id and "family" in artifact_id:
        params["top_families_visual"] = int(top_families_visual)
        params["min_visual_family_support"] = int(min_visual_family_support)
    if "type_permission_heatmap" in artifact_id or "discriminative" in artifact_id:
        params["top_permissions"] = int(top_permissions)
    return params


def bundle_artifact_role(artifact_id: str, category: str) -> tuple[str, bool]:
    """Classify bundle artifact role for audit/readability."""
    primary_ids = {
        "type_permission_prevalence",
        "type_permission_entropy",
        "permission_discriminability_rank",
        "dangerous_permission_distribution_by_type",
        "dangerous_stats_tests",
        "family_support_distribution",
        "permission_coverage_report",
    }
    if artifact_id.startswith("family_permission_profiles_top"):
        return "primary_structural", True
    if artifact_id.startswith("family_permission_entropy_top"):
        return "primary_structural", True
    if artifact_id.startswith("family_jsd_matrix_top"):
        return "primary_structural", True
    if artifact_id.startswith("family_jsd_pairs_top"):
        return "primary_structural", True
    if artifact_id in primary_ids:
        return "primary_structural", True
    if category == "table" and artifact_id in {
        "misclassified_samples_by_type",
        "per_family_performance_spread",
        "permission_anomaly_samples",
        "confusion_within_vs_cross_type",
    }:
        return "diagnostic_table", False
    if category == "table":
        return "auxiliary_table", False
    if category == "figure":
        return "auxiliary_figure", False
    if category == "doc":
        return "bundle_documentation", False
    return "bundle_contract", False


def bundle_table_policy(artifact_id: str) -> dict[str, Any]:
    """Return table governance metadata for bundle inventory/audit."""
    primary_structural = {
        "type_permission_prevalence",
        "type_permission_entropy",
        "permission_discriminability_rank",
        "dangerous_permission_distribution_by_type",
        "dangerous_stats_tests",
        "family_support_distribution",
        "permission_coverage_report",
    }
    auxiliary_structural = {
        "consensus_distribution",
        "consensus_correlation_report",
        "generic_definition_audit",
        "generic_vs_non_generic_summary",
    }
    diagnostic_tables = {
        "misclassified_samples_by_type",
        "per_family_performance_spread",
        "permission_anomaly_samples",
        "confusion_within_vs_cross_type",
    }
    if artifact_id.startswith("family_permission_profiles_top"):
        return {
            "used_by": "bundle_only,paper",
            "keep_in_permission_trends": "yes",
            "target_location": "bundles/permission_trends/tables",
            "needs_latex_export": "no",
            "notes": "Core family profile table.",
        }
    if artifact_id.startswith("family_permission_entropy_top"):
        return {
            "used_by": "bundle_only,paper",
            "keep_in_permission_trends": "yes",
            "target_location": "bundles/permission_trends/tables",
            "needs_latex_export": "no",
            "notes": "Core family entropy table.",
        }
    if artifact_id.startswith("family_jsd_matrix_top"):
        return {
            "used_by": "bundle_only,paper_render",
            "keep_in_permission_trends": "yes",
            "target_location": "bundles/permission_trends/tables",
            "needs_latex_export": "no",
            "notes": "Matrix-form render/input artifact.",
        }
    if artifact_id.startswith("family_jsd_pairs_top"):
        return {
            "used_by": "paper,freeze,bundle_only",
            "keep_in_permission_trends": "yes",
            "target_location": "bundles/permission_trends/tables",
            "needs_latex_export": "no",
            "notes": "Compact pair verification artifact (audit canonical).",
        }
    if artifact_id in primary_structural:
        return {
            "used_by": "paper,bundle_only,backfill",
            "keep_in_permission_trends": "yes",
            "target_location": "bundles/permission_trends/tables",
            "needs_latex_export": "yes"
            if artifact_id
            in {"dangerous_permission_distribution_by_type", "dangerous_stats_tests", "family_support_distribution"}
            else "no",
            "notes": "Primary structural table.",
        }
    if artifact_id in auxiliary_structural:
        return {
            "used_by": "bundle_only,backfill",
            "keep_in_permission_trends": "yes",
            "target_location": "bundles/permission_trends/tables",
            "needs_latex_export": "no",
            "notes": "Auxiliary/supporting analysis table.",
        }
    if artifact_id in diagnostic_tables:
        return {
            "used_by": "diagnostic_only",
            "keep_in_permission_trends": "no",
            "target_location": "diagnostics",
            "needs_latex_export": "no",
            "notes": "Diagnostic table; should not live in core bundle tables.",
        }
    return {
        "used_by": "bundle_only",
        "keep_in_permission_trends": "yes",
        "target_location": "bundles/permission_trends/tables",
        "needs_latex_export": "no",
        "notes": "Unclassified table; review needed.",
    }


def bundle_artifact_schema_version(category: str) -> str:
    """Return current schema version tag for bundle artifact categories."""
    if category == "table":
        return "table_schema_v1"
    if category == "figure":
        return "figure_schema_v1"
    if category == "doc":
        return "doc_schema_v1"
    return "contract_schema_v1"


def export_permission_trends_bundle_manifest(
    *,
    run_id: str,
    bundle_dir: Path,
    top_families_visual: int,
    min_visual_family_support: int,
    top_permissions: int,
    artifact_paths: list[str],
) -> str:
    """Export machine-readable manifest for permission_trends bundle contents."""
    entries: list[dict[str, Any]] = []
    seen_relative: set[str] = set()
    for raw_path in artifact_paths:
        if not raw_path:
            continue
        path = Path(str(raw_path))
        if not path.exists():
            continue
        try:
            rel = path.resolve().relative_to(bundle_dir.resolve())
        except Exception:
            continue
        if len(rel.parts) < 2:
            continue
        category = str(rel.parts[0]).strip().lower()
        if category not in {
            ARTIFACT_GROUP_CONTRACTS,
            ARTIFACT_GROUP_DOCS,
            ARTIFACT_GROUP_FIGURES,
            ARTIFACT_GROUP_TABLES,
        }:
            continue
        normalized_category = "contract" if category == ARTIFACT_GROUP_CONTRACTS else category[:-1]
        artifact_id = canonical_bundle_artifact_id_from_path(path, category=normalized_category)
        rel_norm = str(rel).replace("\\", "/")
        if rel_norm in seen_relative:
            continue
        seen_relative.add(rel_norm)
        role, is_primary = bundle_artifact_role(
            artifact_id=artifact_id,
            category=normalized_category,
        )
        entry = {
            "artifact_id": artifact_id,
            "category": normalized_category,
            "role": role,
            "is_primary": bool(is_primary),
            "filename": path.name,
            "relative_path": rel_norm,
            "parameters": infer_bundle_artifact_parameters(
                artifact_id,
                top_families_visual=top_families_visual,
                min_visual_family_support=min_visual_family_support,
                top_permissions=top_permissions,
            ),
            "run_id": str(run_id),
            "bundle_contract_version": BUNDLE_CONTRACT_VERSION,
            "source_stage": "permission_trends_report",
            "schema_version": bundle_artifact_schema_version(normalized_category),
            "status": "generated",
            "notes": "",
        }
        if normalized_category == "table":
            entry.update(bundle_table_policy(artifact_id))
        entries.append(dict(entry))
    entries = sorted(
        entries,
        key=lambda item: (
            str(item.get("category", "")),
            str(item.get("artifact_id", "")),
            str(item.get("filename", "")),
        ),
    )
    manifest = {
        "bundle_contract_name": BUNDLE_CONTRACT_NAME,
        "bundle_contract_version": BUNDLE_CONTRACT_VERSION,
        "run_id": str(run_id),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "bundle_root": str(bundle_dir.resolve()),
        "expected_categories": ["contracts", "docs", "figures", "tables"],
        "artifacts": entries,
    }
    contracts_dir = resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_CONTRACTS)
    path = contracts_dir / "permission_trends_bundle_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return str(path)


def export_permission_trends_table_inventory_from_manifest(
    *,
    bundle_dir: Path,
    run_id: str,
    manifest_path: str,
) -> str | None:
    """Export requested table inventory matrix derived from bundle manifest."""
    path = Path(str(manifest_path))
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    artifacts = payload.get("artifacts", []) if isinstance(payload, dict) else []
    if not isinstance(artifacts, list):
        return None
    rows: list[dict[str, Any]] = []
    for entry in artifacts:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("category", "")).strip() != "table":
            continue
        rows.append(
            {
                "run_id": str(run_id),
                "artifact_id": str(entry.get("artifact_id", "")),
                "current_filename": str(entry.get("filename", "")),
                "role": str(entry.get("role", "")),
                "is_primary": bool(entry.get("is_primary", False)),
                "used_by": str(entry.get("used_by", "")),
                "keep_in_permission_trends": str(entry.get("keep_in_permission_trends", "")),
                "target_location": str(entry.get("target_location", "")),
                "needs_latex_export": str(entry.get("needs_latex_export", "")),
                "notes": str(entry.get("notes", "")),
            }
        )
    out_df = pd.DataFrame(rows)
    if not out_df.empty:
        out_df = out_df.sort_values(["is_primary", "artifact_id"], ascending=[False, True])
    contracts_dir = resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_CONTRACTS)
    out_path = contracts_dir / "permission_trends_table_inventory.csv"
    out_df.to_csv(out_path, index=False)
    return str(out_path)
