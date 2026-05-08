"""Manifest pointer writes, engine summaries, and ranking exports for the manifest stage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config import app_config

from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import output_paths
import obsidiandroid.governance.artifacts as artifacts
import obsidiandroid.governance.run_manifest as run_manifest
from obsidiandroid.pipeline.manifest.hashing import (
    canonical_csv_bytes,
    dataset_hash_from_sample_ids,
    sha256_hex,
)
from obsidiandroid.pipeline.manifest.writer import write_manifest_atomic


def try_add_artifact(
    writer: artifacts.ManifestWriter,
    key: str,
    file_path: Path,
    content_type: str,
    description: str,
) -> None:
    """Add artifact to manifest writer if file exists."""
    if not file_path.exists():
        return
    writer.add_file(
        artifact_key=key,
        path=file_path.resolve(),
        content_type=content_type,
        description=description,
    )


def write_manifest_with_pointer(
    *,
    manifest: dict[str, Any],
    run_id: str,
    paper_mode: bool,
    run_root: Path,
) -> None:
    """Write canonical manifest and update pointer file for latest run."""
    manifest_payload = dict(manifest)
    manifest_payload["manifest_schema_version"] = run_manifest.MANIFEST_SCHEMA_VERSION
    pointer_payload = {
        "run_id": run_id,
        "created_at_utc": manifest.get("timestamp_utc", ""),
        "run_root": str(run_root).replace("\\", "/"),
    }
    canonical_path = run_root / "run_manifest.json"
    write_manifest_atomic(
        target_path=canonical_path,
        payload=manifest_payload,
    )
    # `run_manifest.latest.json` is always the full manifest schema.
    run_manifest.write_run_manifest(manifest_payload)
    pointer_path = Path(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")) / "diagnostics" / "latest_run_pointer.json"
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    pointer_path.write_text(
        json.dumps(pointer_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    write_promoted_latest_run_pointer(pointer_payload=pointer_payload)


def write_promoted_latest_run_pointer(*, pointer_payload: dict[str, Any]) -> None:
    """Write stable promoted pointers for human/tester run discovery."""
    run_id = str(pointer_payload.get("run_id", "")).strip()
    if not run_id:
        return
    promoted_root = output_paths.promoted_root()
    promoted_root.mkdir(parents=True, exist_ok=True)
    (promoted_root / "latest_run.txt").write_text(f"{run_id}\n", encoding="utf-8")
    (promoted_root / "latest_run_manifest.json").write_text(
        json.dumps(pointer_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def write_run_artifact_index(
    *,
    run_id: str,
    run_root: Path,
    diagnostics_dir: Path,
) -> Path | None:
    """Write a concise run-scoped index for tester/QA artifact discovery."""
    try:
        lines = [
            f"# Run Artifact Index ({run_id})",
            "",
            "**Start here for paper-style review:** `run_evidence_index.md` (run root).",
            "",
            "Authoritative source: all artifacts under this run root.",
            "",
            f"- run_root: `{run_root}`",
            f"- run_evidence_index: `{run_root / 'run_evidence_index.md'}`",
            f"- paper_exports: `{run_root / 'paper_exports'}`",
            f"- bundles/permission_trends: `{run_root / 'bundles' / 'permission_trends'}`",
            f"- diagnostics: `{diagnostics_dir}`",
            f"- models: `{run_root / 'models'}`",
            f"- conf_matrices: `{run_root / 'conf_matrices'}`",
            "",
            "Notes:",
            "- Root-level latest/promoted paths are convenience mirrors only.",
            "- Use run-scoped artifacts for paper evidence and QA checks.",
        ]
        out_path = diagnostics_dir / "run_artifact_index.md"
        out_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        return out_path
    except Exception as exc:
        du.print_warning(f"[SUMMARY] Failed to write run artifact index: {exc}")
        return None


def summarize_engine_lifecycle(
    pipeline_results: dict[str, Any] | None,
) -> tuple[int, int, list[str]]:
    """Summarize included/excluded engine counts and canonical names."""
    engine_lifecycle = None
    if isinstance(pipeline_results, dict):
        engine_lifecycle = pipeline_results.get("engine_lifecycle")

    if not isinstance(engine_lifecycle, pd.DataFrame) or engine_lifecycle.empty:
        return 0, 0, []

    included_engines = int(
        engine_lifecycle["included_in_model_flag"].fillna(False).astype(bool).sum()
    )
    excluded_engines = int(
        (~engine_lifecycle["included_in_model_flag"].fillna(False).astype(bool)).sum()
    )
    engine_names = sorted(
        engine_lifecycle["engine_name_canonical"].dropna().astype(str).unique().tolist()
    )
    return included_engines, excluded_engines, engine_names


def extract_parser_list(vendor_eval_df: pd.DataFrame | None) -> list[str]:
    """Extract sorted parser list from vendor evaluation dataframe."""
    if not isinstance(vendor_eval_df, pd.DataFrame) or "Vendor" not in vendor_eval_df.columns:
        return []
    return sorted(vendor_eval_df["Vendor"].dropna().astype(str).unique().tolist())


def compute_dataset_hash(samples_df: pd.DataFrame | None) -> str:
    """Compute dataset hash from sorted sample_id values."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty or "sample_id" not in samples_df.columns:
        return ""
    values = samples_df["sample_id"].dropna().tolist()
    return dataset_hash_from_sample_ids(values)


def rank_tier_from_publication_score(score: float) -> str:
    """Map publication score to fixed PM-approved tiers."""
    if score >= 0.75:
        return "High"
    if score >= 0.25:
        return "Moderate"
    return "Low"


def export_engine_ranking_tiers(
    *,
    run_root: Path,
    run_id: str,
    evidence_mode: bool,
    weights_df: pd.DataFrame | None,
) -> tuple[Path | None, str]:
    """Export deterministic Paper #2 engine ranking table and hash."""
    if not isinstance(weights_df, pd.DataFrame) or weights_df.empty:
        return None, ""
    if evidence_mode:
        out_dir = run_root / "paper2_pack"
    else:
        out_dir = run_root / "paper_exports" / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)

    frame = weights_df.copy()
    vendor_col = "Vendor" if "Vendor" in frame.columns else None
    if vendor_col is None:
        return None, ""
    if "Leakage Safe Score Raw" not in frame.columns:
        return None, ""

    frame["engine_id"] = frame[vendor_col].astype(str).str.strip().str.lower()
    frame["publication_score"] = pd.to_numeric(frame["Leakage Safe Score Raw"], errors="coerce").fillna(0.0)
    rel_col = "Reliability" if "Reliability" in frame.columns else ("Specificity Score" if "Specificity Score" in frame.columns else None)
    if rel_col:
        frame["reliability_score"] = pd.to_numeric(frame[rel_col], errors="coerce").fillna(0.0)
    else:
        frame["reliability_score"] = 0.0
    frame["final_ml_score"] = pd.to_numeric(frame.get("Final ML Score", 0.0), errors="coerce").fillna(0.0)
    frame["composite_score"] = pd.to_numeric(frame.get("Composite Score", 0.0), errors="coerce").fillna(0.0)
    frame["enrichment_score"] = pd.to_numeric(frame.get("Enrichment Score", 0.0), errors="coerce").fillna(0.0)
    frame["parser_gate_status"] = frame.get("parser_gate_status", "unknown").astype(str)
    frame["included_in_model"] = pd.to_numeric(frame.get("included_in_model", 0), errors="coerce").fillna(0).astype(int)
    frame = frame.sort_values(
        ["publication_score", "reliability_score", "engine_id"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    frame["rank"] = frame.index + 1
    frame["tier"] = frame["publication_score"].apply(_rank_tier_from_publication_score)
    columns = [
        "rank",
        "engine_id",
        "publication_score",
        "tier",
        "final_ml_score",
        "reliability_score",
        "composite_score",
        "enrichment_score",
        "parser_gate_status",
        "included_in_model",
    ]
    export_df = frame[columns].copy()
    out_path = out_dir / "engine_ranking_tiers.csv"
    export_df.to_csv(out_path, index=False, lineterminator="\n", float_format="%.6f")
    ranking_hash = sha256_hex(
        canonical_csv_bytes(
            export_df,
            float_format="%.6f",
            lineterminator="\n",
        )
    )
    return out_path, ranking_hash


def export_parser_quality_final(
    *,
    diagnostics_dir: Path,
    run_id: str,
    weights_df: pd.DataFrame | None,
) -> Path | None:
    """Export final parser-gate/model-inclusion snapshot from engine weights."""
    if not isinstance(weights_df, pd.DataFrame) or weights_df.empty:
        return None
    vendor_col = "Vendor" if "Vendor" in weights_df.columns else None
    if vendor_col is None:
        return None
    frame = weights_df.copy()
    export_df = pd.DataFrame(
        {
            "vendor_id": frame[vendor_col].astype(str).str.strip().str.lower(),
            "parser_gate_status": frame.get("parser_gate_status", "unknown").astype(str),
            "included_in_model": pd.to_numeric(
                frame.get("included_in_model", 0),
                errors="coerce",
            ).fillna(0).astype(int),
            "diagnostic_stage": "engine_weights_final",
        }
    )
    export_df["included_in_engine_weights"] = export_df["included_in_model"].astype(int)
    export_df["selected_for_feature_matrix"] = np.nan
    export_df["selection_status"] = "unknown"
    export_df["selection_stage"] = "feature_matrix_topk"
    debug_path = diagnostics_dir / f"vendor_gate_debug_{run_id}.csv"
    if not debug_path.exists():
        debug_path = diagnostics_dir / "vendor_gate_debug.latest.csv"
    if debug_path.exists():
        try:
            debug_df = pd.read_csv(debug_path)
            if not debug_df.empty and "vendor" in debug_df.columns:
                sel = pd.DataFrame(
                    {
                        "vendor_id": debug_df["vendor"].astype(str).str.strip().str.lower(),
                        "selected_for_feature_matrix": pd.to_numeric(
                            debug_df.get("selected_flag", 0),
                            errors="coerce",
                        ).fillna(0).astype(int),
                    }
                ).drop_duplicates(subset=["vendor_id"], keep="last")
                export_df = export_df.merge(sel, on="vendor_id", how="left", suffixes=("", "_dbg"))
                if "selected_for_feature_matrix_dbg" in export_df.columns:
                    export_df["selected_for_feature_matrix"] = (
                        pd.to_numeric(export_df["selected_for_feature_matrix_dbg"], errors="coerce")
                        .fillna(pd.to_numeric(export_df["selected_for_feature_matrix"], errors="coerce"))
                    )
                    export_df = export_df.drop(columns=["selected_for_feature_matrix_dbg"])
                export_df["selected_for_feature_matrix"] = pd.to_numeric(
                    export_df["selected_for_feature_matrix"],
                    errors="coerce",
                ).fillna(0).astype(int)
                export_df["selection_status"] = export_df["selected_for_feature_matrix"].map(
                    {1: "selected_topk", 0: "not_selected_topk"}
                ).fillna("unknown")
        except Exception:
            pass
    run_path = diagnostics_dir / f"parser_quality_final_{run_id}.csv"
    latest_path = diagnostics_dir / "parser_quality_final.latest.csv"
    export_df.to_csv(run_path, index=False)
    export_df.to_csv(latest_path, index=False)
    return run_path

