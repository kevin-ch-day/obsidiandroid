"""Permission-trends bundle filesystem I/O (tables/docs/contracts export, zip, readme, mirrors)."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common import output_paths
from obsidiandroid.pipeline.permission_trends.bundle_manifest import resolve_bundle_artifact_dir
from obsidiandroid.pipeline.permission_trends.constants import (
    ARTIFACT_GROUP_CONTRACTS,
    ARTIFACT_GROUP_DOCS,
    ARTIFACT_GROUP_TABLES,
    BUNDLE_CONTRACT_NAME,
    BUNDLE_CONTRACT_VERSION,
)
from obsidiandroid.pipeline.permission_trends.publish_paths import resolve_run_root_for_run_id


def export_df_with_latest(
    df: pd.DataFrame,
    run_id: str,
    file_stem: str,
    bundle_dir: Path,
    *,
    artifact_group: str = ARTIFACT_GROUP_TABLES,
) -> str:
    """Write bundle CSV with run-scoped name; mirror ``*.latest.csv`` per output hygiene policy."""
    out_dir = resolve_bundle_artifact_dir(bundle_dir, artifact_group)
    csv_text = df.to_csv(index=False)
    rid = str(run_id).strip() or "unknown"
    paths = oh.mirror_csv_text_run_then_global(
        diagnostics_dir=out_dir,
        run_filename=f"{file_stem}_{rid}.csv",
        csv_text=csv_text,
        global_latest_name=f"{file_stem}.latest.csv",
    )
    return str(paths[0])


def export_df_diagnostics_with_latest(
    df: pd.DataFrame,
    *,
    run_id: str,
    file_stem: str,
) -> str:
    """Export CSV to run diagnostics with run-scoped name and hygiene mirror for ``*.latest``."""
    diagnostics_dir = Path(
        str(
            getattr(
                app_config,
                "RUNTIME_DIAGNOSTICS_DIR",
                Path(app_config.DEFAULT_OUTPUT_DIR) / "diagnostics",
            )
        )
    )
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    rid = str(run_id).strip() or "unknown"
    csv_text = df.to_csv(index=False)
    paths = oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=f"{file_stem}_{rid}.csv",
        csv_text=csv_text,
        global_latest_name=f"{file_stem}.latest.csv",
    )
    return str(paths[0])


def export_json_with_latest(
    payload: dict[str, Any],
    run_id: str,
    file_stem: str,
    bundle_dir: Path,
) -> str:
    """Write bundle JSON with run-scoped name; mirror ``*.latest.json`` per output hygiene policy."""
    contracts_dir = resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_CONTRACTS)
    rid = str(run_id).strip() or "unknown"
    paths = oh.mirror_json_text_run_then_global(
        diagnostics_dir=contracts_dir,
        run_filename=f"{file_stem}_{rid}.json",
        payload=payload,
        global_latest_name=f"{file_stem}.latest.json",
    )
    return str(paths[0])


def export_text_with_latest(
    text: str,
    run_id: str,
    file_stem: str,
    bundle_dir: Path,
) -> str:
    """Write bundle text doc with run-scoped name; mirror ``*.latest.txt`` per output hygiene policy."""
    docs_dir = resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_DOCS)
    rid = str(run_id).strip() or "unknown"
    paths = oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=docs_dir,
        run_filename=f"{file_stem}_{rid}.txt",
        text=text,
        global_latest_name=f"{file_stem}.latest.txt",
    )
    return str(paths[0])


def export_markdown_with_latest(
    text: str,
    run_id: str,
    file_stem: str,
    bundle_dir: Path,
) -> str:
    """Write bundle Markdown with run-scoped name; mirror ``*.latest.md`` per output hygiene policy."""
    docs_dir = resolve_bundle_artifact_dir(bundle_dir, ARTIFACT_GROUP_DOCS)
    rid = str(run_id).strip() or "unknown"
    paths = oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=docs_dir,
        run_filename=f"{file_stem}_{rid}.md",
        text=text,
        global_latest_name=f"{file_stem}.latest.md",
    )
    return str(paths[0])


def export_permission_trends_bundle_readme(run_id: str, bundle_dir: Path) -> str:
    """Write operator-readable scope notes for the permission_trends bundle."""
    lines = [
        "# Permission Trends Bundle",
        "",
        f"- run_id: {run_id}",
        f"- bundle_contract_name: {BUNDLE_CONTRACT_NAME}",
        f"- bundle_contract_version: {BUNDLE_CONTRACT_VERSION}",
        "",
        "This bundle contains full structural-analysis research artifacts.",
        "",
        "Directory semantics:",
        "- contracts/: bundle contracts and machine-readable metadata.",
        "- docs/: operator-readable notes and narrative summaries.",
        "- figures/: structural analysis figures.",
        "- tables/: structural analysis tables.",
        "",
        "Related run directories:",
        "- diagnostics/: QA, provenance, and validation outputs.",
        "- paper_exports/: strict paper subset (paper mode only).",
        "- models/: trained model artifacts.",
        "- conf_matrices/: model confusion matrices.",
    ]
    readme_path = bundle_dir / "README.md"
    readme_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(readme_path)


def zip_bundle(bundle_dir: Path) -> str:
    zip_path = bundle_dir.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in bundle_dir.rglob("*"):
            if path.is_file():
                archive.write(path, arcname=str(path.relative_to(bundle_dir.parent)))
    return str(zip_path)


def resolve_permission_bundle_dir(run_id: str) -> Path:
    """Resolve output folder for permission trends bundle."""
    run_id_clean = str(run_id).strip()
    if run_id_clean:
        return resolve_run_root_for_run_id(run_id_clean) / "bundles" / "permission_trends"
    return output_paths.output_root() / "tools" / "permission_trends"


def copy_permission_bundle_to_latest(bundle_dir: Path) -> Path | None:
    """Best-effort copy of canonical bundle into mutable latest location."""
    if not bool(getattr(app_config, "ENABLE_PERMISSION_TRENDS_LATEST_MIRROR", False)):
        return None
    if not isinstance(bundle_dir, Path) or not bundle_dir.exists():
        return None
    latest_dir = output_paths.bundles_root() / "latest" / "permission_trends"
    try:
        if latest_dir.exists():
            shutil.rmtree(latest_dir)
        shutil.copytree(bundle_dir, latest_dir)
        return latest_dir
    except Exception as exc:
        du.print_warning(f"[REPORT] Latest permission bundle copy skipped (non-fatal): {exc}")
        return None
