"""Feature lineage audit for the fused ML matrix (reporting only; no training changes).

Maps column names to modality/source using naming conventions and exported contracts.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.json_io import read_json_dict

# Columns produced by ``enrich_score_features.add_derived_score_features`` (primary AV DB path).
ENRICH_SCORE_COLUMNS = frozenset(
    {
        "malicious_engines",
        "total_engines",
        "malicious_pct",
        "malicious_ratio",
        "is_high_consensus",
        "detection_band",
        "detection_flag",
        "detection_density",
        "engine_diversity",
        "risk_score",
        "risk_band",
        "risk_rank",
        "detection_confidence",
    }
)

# Known merged malicious-score table merge artifacts (optional DB snapshot columns).
COMMON_MERGE_SCORE_HINTS = frozenset(
    {
        "confidence_band",
        "detection_confidence_level",
    }
)


def classify_column_lineage(column_name: str, *, selected_vendors: frozenset[str] | None = None) -> dict[str, str]:
    """Return modality/source classification for a single feature column name."""
    name = str(column_name).strip()
    lower = name.lower()

    if lower.startswith("perm__"):
        if lower in {"perm__dangerous_count", "perm__normal_count", "perm__oem_count", "perm__total_count"}:
            return {
                "lineage_group": "permission_intel_counts",
                "modality": "permission_structural",
                "source_system": "permission_intel_db",
                "notes": "Aggregates from android_permission_obs_sample (protection/source buckets).",
            }
        return {
            "lineage_group": "permission_intel_binary",
            "modality": "permission_structural",
            "source_system": "permission_intel_db",
            "notes": "Per-permission binary indicator after min-support filtering.",
        }

    if lower.startswith("meta__"):
        return {
            "lineage_group": "catalog_metadata_vt_summary",
            "modality": "catalog_static_and_vt_aggregate",
            "source_system": "primary_db_sample_catalog_join",
            "notes": "Engineered from malware_sample_catalog / VT summary columns (meta__ prefix). Not Permission Intel.",
        }

    for prefix in ("parsed_family_", "threat_class_", "malware_type_"):
        if lower.startswith(prefix):
            return {
                "lineage_group": "vendor_parsed_av_strings",
                "modality": "av_vendor_natural_language_labels",
                "source_system": "primary_db_parsed_vendor_tables",
                "notes": "Vendor-specific Parsed Family / Threat Class / Malware Type strings "
                "(encoded to integer codes). These are AV vendor outputs, not ground-truth family_id labels.",
            }

    if lower in ENRICH_SCORE_COLUMNS or lower in COMMON_MERGE_SCORE_HINTS:
        return {
            "lineage_group": "av_derived_scores",
            "modality": "av_consensus_and_detection_shape",
            "source_system": "primary_db_verdicts_plus_enrichment",
            "notes": "Derived from binary detection matrix + malicious scoring merge + enrich_score_features.",
        }

    # Wide binary engine columns from virustotal_sample_vendor_engine_verdicts pivot (names vary by engine).
    if selected_vendors and lower in selected_vendors:
        return {
            "lineage_group": "av_engine_binary_detection",
            "modality": "vendor_detection_binary",
            "source_system": "primary_db_vendor_engine_verdicts",
            "notes": "Per-engine detection flag from wide verdict row (same column stem as vendor key when applicable).",
        }

    return {
        "lineage_group": "av_engine_binary_or_auxiliary",
        "modality": "vendor_detection_binary_or_numeric_aux",
        "source_system": "primary_db_av_pipeline",
        "notes": "Typically wide AV binary columns from verdict pivot; verify against encoder_mappings.",
    }


def load_json_if_present(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _resolve_run_id(diag: Path, run_id: str | None) -> str:
    """Resolve a run ID without consulting ambiguous ``*.latest`` artifacts."""
    if run_id:
        return str(run_id).strip()
    manifest = read_json_dict(diag.parent / "run_manifest.json")
    return str(manifest.get("run_id") or "").strip()


def build_feature_lineage_report(
    run_diagnostics_dir: Path | str,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Assemble lineage JSON + tabular rows from one run's stamped artifacts.

    A lineage report is scientific evidence, so it intentionally refuses to
    select an arbitrary local or global ``*.latest`` file. Callers either
    supply ``run_id`` or provide a run directory with ``run_manifest.json``.
    """
    diag = Path(run_diagnostics_dir)
    resolved_run_id = _resolve_run_id(diag, run_id)
    modality_path = oh.resolve_modality_method_contract_path(diag, resolved_run_id)
    contract_path = oh.resolve_feature_contract_path(diag, resolved_run_id)
    leakage_txt = oh.resolve_leakage_assessment_path(diag, resolved_run_id)
    leakage_audit_path = diag / f"leakage_pruning_audit_{resolved_run_id}.csv"

    modality = load_json_if_present(modality_path) or {}
    contract = load_json_if_present(contract_path) or {}

    feature_columns: list[str] = list(contract.get("feature_columns") or [])
    selected = contract.get("selected_vendors") or []
    vendor_set = frozenset(str(v).strip().lower().replace("-", "").replace("_", "") for v in selected)

    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for col in feature_columns:
        meta = classify_column_lineage(col, selected_vendors=vendor_set)
        group = meta["lineage_group"]
        counts[group] = counts.get(group, 0) + 1
        rows.append({"column_name": col, **meta})

    prefix_counts_training = {
        "perm__": sum(1 for c in feature_columns if str(c).startswith("perm__")),
        "meta__": sum(1 for c in feature_columns if str(c).startswith("meta__")),
        "parsed_family_": sum(1 for c in feature_columns if str(c).startswith("parsed_family_")),
        "threat_class_": sum(1 for c in feature_columns if str(c).startswith("threat_class_")),
        "malware_type_": sum(1 for c in feature_columns if str(c).startswith("malware_type_")),
    }

    fusion = modality.get("fusion_modality") or {}
    permission_mod = modality.get("permission_modality") or {}

    audit_rows = 0
    if leakage_audit_path.is_file():
        try:
            import pandas as pd

            audit_df = pd.read_csv(leakage_audit_path)
            audit_rows = int(len(audit_df))
        except Exception:
            audit_rows = 0

    fusion_total = int(fusion.get("feature_count_total") or 0)
    training_cols = len(feature_columns)
    dropped_delta = max(0, fusion_total - training_cols) if fusion_total else None

    narrative = {
        "modules_av_vendor_detection_features": (
            "obsidiandroid/matrix/av_binary_matrix_builder.py (binary pivot), "
            "database/db_av_engine_verdicts.fetch_verdicts_simple_ids; merged into enriched_matrix in "
            "obsidiandroid/pipeline/av_engine_pipeline.py."
        ),
        "modules_vendor_consensus_scoring": (
            "Vendor scores used for **selection/gating only** via obsidiandroid/pipeline/score_av_engines.py "
            "and obsidiandroid/features/vectorization/feature_engine_selection.py — scores are not appended "
            "as feature columns unless merged indirectly through enrichment frames."
        ),
        "modules_permission_features": (
            "obsidiandroid/orchestration/permission_features.py build_permission_feature_frame "
            "(Permission Intel android_permission_obs_sample via execute_permission_query)."
        ),
        "modules_metadata_features": (
            "obsidiandroid/pipeline/sample_preparation.py build_metadata_feature_frame "
            "(prefix meta__, sourced from cohort dataframe / primary DB fields)."
        ),
        "modules_vendor_parsed_encoding": (
            "obsidiandroid/features/vectorization/feature_vendor_extractor.py + feature_encoder.encode_features "
            "inside obsidiandroid/features/vectorization/feature_vector_builder.build_feature_vector."
        ),
        "modules_fusion": (
            "main.py merges enriched_matrix + metadata + permission, then "
            "obsidiandroid/pipeline/stage_modeling.build_feature_matrix_stage → build_feature_vector joins "
            "encoded vendor fields with extras."
        ),
        "modules_training_pruning": (
            "src/obsidiandroid/modeling/feature_selection_contract.py: train-partition no-variance "
            "and leakage guards; frozen ordered columns are applied to test rows; leakage audit CSV is emitted."
        ),
    }

    answers = {
        "family_label_leakage": (
            "Training labels use family_id; features must not include canonical family_name/family_id columns. "
            "parsed_family_* columns are **vendor-reported** strings, not Obsidian ground-truth labels — "
            "see leakage_assessment_<run_id>.txt for qualitative coupling classification."
        ),
        "parsed_vendor_vs_pure_detection": (
            "Vendor parsed strings use prefixes parsed_family_, threat_class_, malware_type_; "
            "wide binary detections use engine-name stems from the verdict pivot (distinct representations)."
        ),
        "feature_contract_modality_labels": (
            "feature_contract_<run_id>.json lists columns + encoder_mappings for categoricals; "
            "perm__/meta__/parsed prefixes give deterministic modality without extra tags per column."
        ),
        "permission_intel_vs_primary_metadata": (
            "perm__* rows originate from Permission Intel DB; meta__* rows from cohort/catalog VT aggregates "
            "on the primary database (see doc/data_sources.md)."
        ),
        "evidence_paper_mode_notes": (
            "RUNTIME_EVIDENCE_STRICT_MODE can force empty matrices when parser/top-k constraints fail; "
            "PERMISSION_ENRICHMENT_STRICT_IN_EVIDENCE gates PI fetch failures; "
            "PAPER_MODE_ENABLED disables vendor fallback widening — review profile + app_config."
        ),
    }

    payload: dict[str, Any] = {
        "artifact_sources": {
            "modality_method_contract": str(modality_path),
            "feature_contract": str(contract_path),
            "leakage_assessment_txt": str(leakage_txt) if leakage_txt.is_file() else None,
            "leakage_pruning_audit": str(leakage_audit_path) if leakage_audit_path.is_file() else None,
        },
        "fusion_stage_counts": {
            "matrix_rows": fusion.get("matrix_shape", {}).get("rows"),
            "matrix_columns_total": fusion_total,
            "permission_columns": fusion.get("feature_count_permission"),
            "vendor_parsed_columns": fusion.get("feature_count_av"),
            "other_columns": fusion.get("feature_count_other"),
            "permission_modality_feature_count_raw": permission_mod.get("feature_count_raw"),
        },
        "training_stage_counts": {
            "feature_columns_after_pruning": training_cols,
            "selected_vendor_count": contract.get("selected_vendor_count"),
            "approx_columns_dropped_since_fusion": dropped_delta,
            "leakage_pruning_audit_rows": audit_rows,
        },
        "lineage_group_counts_training": counts,
        "name_prefix_counts_training": prefix_counts_training,
        "code_reference": narrative,
        "audit_answers": answers,
        "warnings": [],
    }

    if fusion_total and training_cols and audit_rows:
        inferred_low_info = max(0, fusion_total - training_cols - audit_rows)
        payload["training_stage_counts"]["approx_low_information_drops"] = inferred_low_info
        if inferred_low_info > 0:
            payload["warnings"].append(
                "approx_low_information_drops is fusion_total - training_cols - leakage_audit_rows; "
                "exact list only appears in debug logs unless a dedicated export is added."
            )

    if not feature_columns:
        payload["warnings"].append(
            "Stamped feature contract missing or empty — supply run_id or a diagnostics directory under a run manifest."
        )

    return {
        "summary": payload,
        "column_rows": rows,
    }


def write_feature_lineage_artifacts(
    run_diagnostics_dir: Path | str,
    *,
    run_id: str | None = None,
) -> tuple[Path, Path]:
    """Write run-stamped feature-lineage summary JSON and CSV artifacts."""
    diag = Path(run_diagnostics_dir)
    diag.mkdir(parents=True, exist_ok=True)
    resolved_run_id = _resolve_run_id(diag, run_id)
    if not resolved_run_id:
        raise ValueError("run_id is required when run_manifest.json is unavailable")
    built = build_feature_lineage_report(diag, run_id=resolved_run_id)
    json_path = diag / f"feature_lineage_summary_{resolved_run_id}.json"
    csv_path = diag / f"feature_lineage_summary_{resolved_run_id}.csv"

    export_payload = dict(built["summary"])
    export_payload["column_lineage"] = built["column_rows"]
    json_path.write_text(json.dumps(export_payload, indent=2, sort_keys=True), encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["column_name", "lineage_group", "modality", "source_system", "notes"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in built["column_rows"]:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    return json_path, csv_path


__all__ = [
    "build_feature_lineage_report",
    "classify_column_lineage",
    "write_feature_lineage_artifacts",
]
