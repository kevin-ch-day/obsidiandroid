"""Orchestrate research-validity artifact generation at manifest finalization."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd

from analysis.diagnostics.research_validity.cohort_funnel import (
    finalize_cohort_funnel_dict,
    write_cohort_funnel_artifacts,
)
from analysis.diagnostics.research_validity.figures import write_validity_figures
from analysis.diagnostics.hostile_audit.bundle import write_hostile_audit_bundle
from analysis.diagnostics.research_validity.paper_claim_audit import write_paper_claim_audit_md
from analysis.diagnostics.research_validity.permission_audit import write_permission_feature_audit_csv
from analysis.diagnostics.research_validity.signal_export import write_signal_decomposition_artifacts
from analysis.diagnostics.research_validity.type_permission_figures import (
    write_type_permission_figure_bundle,
)
from analysis.observability import api as obs_api


def write_research_validity_bundle(
    *,
    run_root: Path,  # reserved for future path policies
    diagnostics_dir: Path,
    run_id: str,
    manifest_context: dict[str, Any],
    manifest: dict[str, Any],
    samples_df: pd.DataFrame | None,
    artifact_list: list[str],
    paper_mode: bool,
) -> None:
    """Emit cohort funnel, signal decomposition exports, audits, figures, claim review."""
    finalize_cohort_funnel_dict(manifest_context)
    cohort_paths = list(
        write_cohort_funnel_artifacts(
            diagnostics_dir=diagnostics_dir,
            manifest_context=manifest_context,
        )
    )
    for path in cohort_paths:
        sp = str(path)
        if sp not in artifact_list:
            artifact_list.append(sp)
    if cohort_paths:
        obs_api.record_artifact_write(
            manifest_context,
            cohort_paths[-1],
            detail="research_validity:cohort_funnel_bundle",
        )

    for path in write_signal_decomposition_artifacts(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
    ):
        sp = str(path)
        if sp not in artifact_list:
            artifact_list.append(sp)

    perm_path = write_permission_feature_audit_csv(
        diagnostics_dir=diagnostics_dir,
        samples_df=samples_df,
    )
    if perm_path and str(perm_path) not in artifact_list:
        artifact_list.append(str(perm_path))
    if perm_path:
        obs_api.record_artifact_write(
            manifest_context,
            perm_path,
            detail="research_validity:permission_feature_audit",
        )

    fig_paths = write_validity_figures(
        diagnostics_dir=diagnostics_dir,
        manifest_context=manifest_context,
    )
    for path in fig_paths:
        sp = str(path)
        if sp not in artifact_list:
            artifact_list.append(sp)

    write_type_permission_figure_bundle(
        diagnostics_dir=diagnostics_dir,
        samples_df=samples_df,
        artifact_list=artifact_list,
    )

    claim_path = write_paper_claim_audit_md(
        diagnostics_dir=diagnostics_dir,
        manifest=manifest,
        manifest_context=manifest_context,
        run_id=run_id,
    )
    if str(claim_path) not in artifact_list:
        artifact_list.append(str(claim_path))
    obs_api.record_artifact_write(manifest_context, claim_path, detail="research_validity:paper_claim_audit")

    hostile_wall = datetime.now(timezone.utc).isoformat()
    hostile_t0 = perf_counter()
    try:
        for ha_path in write_hostile_audit_bundle(
            run_root=run_root,
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            manifest_context=manifest_context,
            manifest=manifest,
            samples_df=samples_df,
            artifact_list=artifact_list,
        ):
            if ha_path not in artifact_list:
                artifact_list.append(ha_path)
    finally:
        if isinstance(manifest_context, dict):
            manifest_context["_hostile_bundle_wall_start_iso"] = hostile_wall
            manifest_context["_hostile_bundle_duration_sec"] = max(0.0, perf_counter() - hostile_t0)


__all__ = ["write_research_validity_bundle"]
