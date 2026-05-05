"""Run all hostile-audit writers and attach paths for manifest artifact lists."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from analysis.diagnostics.hostile_audit.baseline_comparison import write_baseline_comparison
from analysis.diagnostics.hostile_audit.cohort_population_audit import write_cohort_population_audit
from analysis.diagnostics.hostile_audit.figure_validity_audit import write_figure_validity_audit
from analysis.diagnostics.hostile_audit.permission_signal_quality import write_permission_signal_quality
from analysis.diagnostics.hostile_audit.recommended_findings import write_recommended_findings
from analysis.diagnostics.hostile_audit.taxonomy_label_quality_audit import (
    write_taxonomy_label_quality_audit,
)
from analysis.diagnostics.hostile_audit.temporal_validity_audit import write_temporal_validity_audit
from analysis.diagnostics.hostile_audit.target_validity_audit import write_target_validity_audit
from analysis.diagnostics.hostile_audit.vendor_label_leakage_audit import write_vendor_label_leakage_audit


def write_hostile_audit_bundle(
    *,
    run_root: Path,  # reserved for manifest path conventions
    diagnostics_dir: Path,
    run_id: str,
    manifest_context: dict[str, Any],
    manifest: dict[str, Any],
    samples_df: pd.DataFrame | None,
    artifact_list: list[str],
) -> list[str]:
    """Emit cohort/population, baselines, targets, leakage, permission, temporal, figure, taxonomy, synthesis.

    Appends emitted paths (as strings) to ``artifact_list`` and returns the same paths.
    Failures in individual auditors should not collapse the bundle; callers may wrap try/except.
    """
    _ = run_root
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    partial_log = diagnostics_dir / "hostile_audit_partial_errors.txt"
    partial_log.write_text("", encoding="utf-8")

    emitted: list[str] = []

    def _add(path: Path | None) -> None:
        if path is None:
            return
        sp = str(path)
        if sp not in artifact_list:
            artifact_list.append(sp)
        emitted.append(sp)

    mctx = manifest_context if isinstance(manifest_context, dict) else {}
    man = manifest if isinstance(manifest, dict) else {}
    profile = mctx.get("profile_params") if isinstance(mctx.get("profile_params"), dict) else man.get(
        "profile_params"
    )
    profile_params = profile if isinstance(profile, dict) else {}

    def _safe(write_fn, label: str) -> None:
        try:
            write_fn()
        except Exception as exc:  # pylint: disable=broad-except
            err = diagnostics_dir / "hostile_audit_partial_errors.txt"
            err.parent.mkdir(parents=True, exist_ok=True)
            with partial_log.open("a", encoding="utf-8") as fh:
                fh.write(f"{label}: {exc!r}\n")
            stub = diagnostics_dir / f"hostile_audit_stub_{label}.txt"
            stub.write_text(f"hostile audit step `{label}` failed: {exc}\n", encoding="utf-8")
            _add(stub)

    def _cohort() -> None:
        cohort_csv, cohort_md = write_cohort_population_audit(
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            manifest=man,
            manifest_context=mctx,
            samples_df=samples_df,
        )
        _add(cohort_csv)
        _add(cohort_md)
        flags_csv = diagnostics_dir / "cohort_population_audit_flags.csv"
        if flags_csv.exists():
            _add(flags_csv)

    _safe(_cohort, "cohort_population")

    def _baselines() -> None:
        b_csv, b_md = write_baseline_comparison(
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            samples_df=samples_df,
        )
        _add(b_csv)
        _add(b_md)

    _safe(_baselines, "baseline_comparison")

    def _targets() -> None:
        t_csv, t_md = write_target_validity_audit(
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            samples_df=samples_df,
        )
        _add(t_csv)
        _add(t_md)

    _safe(_targets, "target_validity")

    def _vendor() -> None:
        vl_csv, vl_md = write_vendor_label_leakage_audit(diagnostics_dir=diagnostics_dir, run_id=run_id)
        _add(vl_csv)
        _add(vl_md)

    _safe(_vendor, "vendor_leakage")

    def _perm() -> None:
        perm_csv, perm_md = write_permission_signal_quality(diagnostics_dir=diagnostics_dir, samples_df=samples_df)
        _add(perm_csv)
        _add(perm_md)

    _safe(_perm, "permission_signal")

    def _temporal() -> None:
        fy_csv, tm_md = write_temporal_validity_audit(
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            manifest_context=mctx,
            samples_df=samples_df,
            profile_params=profile_params,
        )
        _add(fy_csv)
        _add(tm_md)

    _safe(_temporal, "temporal_validity")

    def _figures() -> None:
        fig_md = write_figure_validity_audit(diagnostics_dir=diagnostics_dir, run_id=run_id)
        _add(fig_md)

    _safe(_figures, "figure_validity")

    def _taxonomy() -> None:
        tax_md = write_taxonomy_label_quality_audit(diagnostics_dir=diagnostics_dir, run_id=run_id)
        _add(tax_md)

    _safe(_taxonomy, "taxonomy_label_quality")

    def _rec() -> None:
        rec_md = write_recommended_findings(diagnostics_dir=diagnostics_dir, run_id=run_id)
        _add(rec_md)

    _safe(_rec, "recommended_findings")

    if partial_log.exists() and partial_log.stat().st_size > 0:
        sp = str(partial_log)
        if sp not in artifact_list:
            artifact_list.append(sp)
        emitted.append(sp)

    from obsidiandroid.observability.pipeline_observability import api as obs_api

    for p_str in reversed(emitted):
        if p_str.endswith("recommended_findings.md"):
            obs_api.record_artifact_write(mctx, p_str, detail="hostile_audit:recommended_findings")
            break

    return emitted


__all__ = ["write_hostile_audit_bundle"]
