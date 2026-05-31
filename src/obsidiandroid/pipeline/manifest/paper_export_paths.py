"""Shared paper-export path and payload helpers.

These helpers centralize the canonical paper-facing docs filenames and the
small manifest/profile payloads that point to them. The goal is to keep
``paper2_strict_exports`` focused on export orchestration instead of carrying
duplicated filename contracts inline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_paper_export_settings(*, app_config_obj: Any) -> dict[str, int]:
    """Return normalized paper-export numeric settings from app config."""
    from obsidiandroid.common.cv_fold_config import safe_int_config_value

    return {
        "visual_family_support_threshold": safe_int_config_value(
            getattr(app_config_obj, "MIN_FAMILY_SUPPORT_FOR_VISUAL", 20),
            default=20,
        ),
        "top_families_visual": safe_int_config_value(
            getattr(app_config_obj, "MAX_FAMILY_VISUAL_COUNT", 12),
            default=12,
        ),
        "top_permissions": safe_int_config_value(
            getattr(app_config_obj, "MAX_PERMISSIONS_HEATMAP", 16),
            default=16,
        ),
    }


def build_paper_docs_paths(*, docs_dir: Path) -> dict[str, Path]:
    """Return canonical docs artifact paths for strict paper exports."""
    return {
        "manuscript_table_constants_json": docs_dir / "manuscript_table_constants.json",
        "feature_set_glossary_json": docs_dir / "feature_set_glossary.json",
        "feature_set_glossary_md": docs_dir / "feature_set_glossary.md",
        "perturbation_summary_csv": docs_dir / "perturbation_summary.csv",
        "perturbation_summary_json": docs_dir / "perturbation_summary.json",
        "perturbation_summary_md": docs_dir / "perturbation_summary.md",
        "paper_contract_validation_json": docs_dir / "paper_contract_validation.json",
        "paper_export_profile_json": docs_dir / "paper_export_profile.json",
        "paper_figure_qc_csv": docs_dir / "paper_figure_qc.csv",
        "paper_registry_json": docs_dir / "paper_registry.json",
        "paper_exports_manifest_json": docs_dir / "paper_exports_manifest.json",
    }


def build_paper_export_profile_payload(
    *,
    strict_profile: bool,
    run_id: str,
    contract_version: str,
    visual_family_support_threshold: int,
    top_families_visual: int,
    top_permissions: int,
    docs_paths: dict[str, Path],
) -> dict[str, Any]:
    """Build the stable paper export profile payload."""
    return {
        "strict_profile_enabled": bool(strict_profile),
        "single_run_id": str(run_id),
        "visual_family_support_threshold": int(visual_family_support_threshold),
        "top_families_visual": int(top_families_visual),
        "top_permissions": int(top_permissions),
        "paper_export_contract_version": str(contract_version),
        "manuscript_table_constants_path": str(docs_paths["manuscript_table_constants_json"].resolve()),
        "feature_set_glossary_json": str(docs_paths["feature_set_glossary_json"].resolve()),
        "feature_set_glossary_md": str(docs_paths["feature_set_glossary_md"].resolve()),
        "perturbation_summary_csv": str(docs_paths["perturbation_summary_csv"].resolve()),
        "perturbation_summary_json": str(docs_paths["perturbation_summary_json"].resolve()),
        "perturbation_summary_md": str(docs_paths["perturbation_summary_md"].resolve()),
        "paper_contract_validation_path": str(docs_paths["paper_contract_validation_json"].resolve()),
    }


def build_paper_exports_manifest_payload(
    *,
    run_id: str,
    contract_version: str,
    strict_profile: bool,
    figure_registry_path: Path,
    table_registry_path: Path,
    profile_path: Path,
    paper_registry_path: Path,
    latex_dir: Path,
    figure_registry_rows: list[dict[str, Any]],
    table_registry_rows: list[dict[str, Any]],
    figure_inputs: dict[str, str],
    table_inputs: dict[str, str],
    docs_paths: dict[str, Path],
    validation_summary: dict[str, Any],
    contract_validation_written: bool,
) -> dict[str, Any]:
    """Build the canonical paper exports manifest payload."""
    return {
        "run_id": str(run_id),
        "contract_version": str(contract_version),
        "strict_profile_enabled": bool(strict_profile),
        "run_mode": "paper",
        "figure_ids": sorted([str(row.get("figure_id", "")) for row in figure_registry_rows]),
        "table_ids": sorted([str(row.get("table_id", "")) for row in table_registry_rows]),
        "figure_registry_csv": str(figure_registry_path.resolve()),
        "table_registry_csv": str(table_registry_path.resolve()),
        "paper_export_profile_json": str(profile_path.resolve()),
        "paper_registry_json": str(paper_registry_path.resolve()),
        "tables_latex_dir": str(latex_dir.resolve()),
        "figure_sources": figure_inputs,
        "table_sources": table_inputs,
        "manuscript_table_constants_json": str(docs_paths["manuscript_table_constants_json"].resolve()),
        "feature_set_glossary_json": str(docs_paths["feature_set_glossary_json"].resolve()),
        "feature_set_glossary_md": str(docs_paths["feature_set_glossary_md"].resolve()),
        "perturbation_summary_csv": str(docs_paths["perturbation_summary_csv"].resolve()),
        "perturbation_summary_json": str(docs_paths["perturbation_summary_json"].resolve()),
        "perturbation_summary_md": str(docs_paths["perturbation_summary_md"].resolve()),
        "paper_contract_validation_json": (
            str(docs_paths["paper_contract_validation_json"].resolve()) if contract_validation_written else ""
        ),
        "validation_summary": validation_summary,
    }


__all__ = [
    "build_paper_export_settings",
    "build_paper_docs_paths",
    "build_paper_export_profile_payload",
    "build_paper_exports_manifest_payload",
]
