"""Orchestrate research-validity artifact generation at manifest finalization."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.cli.ui import display as du

from ..contract_and_taxonomy_reports import (
    write_headline_vs_ablation_contract_reports,
    write_taxonomy_type_authority_reports,
)
from ..hostile_audit.bundle import write_hostile_audit_bundle

from .cohort_funnel import (
    finalize_cohort_funnel_dict,
    write_cohort_funnel_artifacts,
)
from .figures import write_validity_figures
from .paper_claim_audit import write_paper_claim_audit_md
from .permission_audit import (
    write_permission_feature_audit_csv,
    write_permission_intel_audit_artifacts,
)
from .signal_export import write_signal_decomposition_artifacts
from .type_permission_figures import (
    write_type_permission_figure_bundle,
)
from obsidiandroid.common.run_slots import is_canonical_profile
from obsidiandroid.diagnostics.cohort_persistence import resolve_effective_samples_df
from obsidiandroid.observability.pipeline_observability import api as obs_api


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
    step_timings = manifest_context.setdefault("research_validity_step_timings_sec", {})

    def finish_step(step: str, started_at: float) -> None:
        """Persist and display a bounded progress checkpoint for a long final stage."""
        elapsed = max(0.0, perf_counter() - started_at)
        if isinstance(step_timings, dict):
            step_timings[step] = elapsed
        du.print_info(f"[RESEARCH] {step}: {du.format_elapsed_duration(elapsed)}")

    profile_id = str(manifest.get("profile_id", "") or manifest_context.get("profile_id", "") or "")
    effective_samples = resolve_effective_samples_df(diagnostics_dir, run_id, samples_df)
    if effective_samples is not None:
        samples_df = effective_samples
    cohort_size = int(manifest.get("cohort_size", 0) or 0)
    if is_canonical_profile(profile_id) and cohort_size > 0:
        if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
            raise RuntimeError(
                "canonical_profile_research_validity_requires_cohort_samples "
                f"(profile={profile_id}, cohort_size={cohort_size})"
            )
    finalize_cohort_funnel_dict(manifest_context)
    step_t0 = perf_counter()
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
    finish_step("Cohort funnel", step_t0)

    step_t0 = perf_counter()
    for path in write_signal_decomposition_artifacts(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
    ):
        sp = str(path)
        if sp not in artifact_list:
            artifact_list.append(sp)
    finish_step("Signal decomposition", step_t0)

    step_t0 = perf_counter()
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

    for pi_path in write_permission_intel_audit_artifacts(
        diagnostics_dir=diagnostics_dir,
        samples_df=samples_df,
    ):
        spi = str(pi_path)
        if spi not in artifact_list:
            artifact_list.append(spi)
        obs_api.record_artifact_write(
            manifest_context,
            pi_path,
            detail="research_validity:permission_intel_audit",
        )
    finish_step("Permission audits", step_t0)

    step_t0 = perf_counter()
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
    finish_step("Validity figures", step_t0)

    step_t0 = perf_counter()
    claim_path = write_paper_claim_audit_md(
        diagnostics_dir=diagnostics_dir,
        manifest=manifest,
        manifest_context=manifest_context,
        run_id=run_id,
    )
    if str(claim_path) not in artifact_list:
        artifact_list.append(str(claim_path))
    obs_api.record_artifact_write(manifest_context, claim_path, detail="research_validity:paper_claim_audit")
    finish_step("Claim audit", step_t0)

    step_t0 = perf_counter()
    try:
        _h_md, _h_csv, _ = write_headline_vs_ablation_contract_reports(
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            manifest_context=dict(manifest_context) if isinstance(manifest_context, dict) else None,
            runtime_headline_hash=str(
                getattr(app_config, "RUNTIME_HEADLINE_FEATURE_COLUMN_HASH", "") or ""
            ).strip()
            or None,
        )
        for p in (_h_md, _h_csv):
            if p and str(p) not in artifact_list:
                artifact_list.append(str(p))
        _t_md, _t_csv = write_taxonomy_type_authority_reports(diagnostics_dir, run_id)
        for p in (_t_md, _t_csv):
            if p and str(p) not in artifact_list:
                artifact_list.append(str(p))
    except Exception as exc:
        partial_failures = manifest_context.setdefault("research_validity_partial_failures", [])
        if isinstance(partial_failures, list):
            partial_failures.append(
                {"step": "contract_and_taxonomy_reports", "error": str(exc)}
            )
        if is_canonical_profile(profile_id):
            raise
    finally:
        finish_step("Contract and taxonomy reports", step_t0)

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
        finish_step("Hostile audit", hostile_t0)


__all__ = ["write_research_validity_bundle"]
