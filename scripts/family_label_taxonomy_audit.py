#!/usr/bin/env python3
"""Fast family label-space audit (cohort load only — no model training).

Loads the same prepared cohort as the pipeline for a profile, then writes:
  - diagnostics/family_label_taxonomy_audit.csv
  - diagnostics/family_label_taxonomy_audit.md
  - diagnostics/support_threshold_preview.csv
  - diagnostics/support_threshold_preview.md

Also pins analysis snapshot export (if enabled) to the same diagnostics directory as
``--diagnostics-dir`` using run-scoped ``analysis_snapshot_<run_id>.*`` filenames, so
adhoc audits do not overwrite ``output/diagnostics/analysis_snapshot.latest.*``.

When ``--diagnostics-dir`` points at ``output/runs/<run_id>/diagnostics``, artifacts are
routed under ``diagnostics/post_run_enrichments/<audit_id>/`` and provenance is recorded
in the canonical run-scoped ``diagnostic_provenance.json`` ledger.

Example:
  python scripts/family_label_taxonomy_audit.py --profile research_all_malicious
  python scripts/family_label_taxonomy_audit.py --profile research_all_malicious \\
      --diagnostics-dir output/runs/my_audit/diagnostics
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.runtime_bootstrap  # noqa: F401

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()

import pandas as pd

from config import app_config
from obsidiandroid.cli import profile_manager
from obsidiandroid.cli.ui import display as du
from obsidiandroid.diagnostics import family_label_taxonomy_audit as fam_audit
from obsidiandroid.diagnostics.diagnostic_provenance import (
    record_diagnostic_provenance,
    resolve_post_run_enrichment_target,
)
from obsidiandroid.governance import paper_cohort_contract
from obsidiandroid.pipeline.stage_samples import load_and_prepare_samples


def _read_json_dict(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _load_target_run_context(run_root: Path | None) -> dict[str, object]:
    if run_root is None:
        return {}
    manifest = _read_json_dict(Path(run_root) / "run_manifest.json")
    profile_id = ""
    profile_params = manifest.get("profile_params")
    if isinstance(profile_params, dict):
        profile_id = str(profile_params.get("profile_id", "") or "")
    return {
        "target_run_id": str(manifest.get("run_id", "") or Path(run_root).name),
        "target_run_profile": profile_id,
        "target_run_manifest": manifest,
    }


def _observed_counts(samples_df) -> dict[str, int]:
    fam_col = "family_canonical" if "family_canonical" in samples_df.columns else "family_id"
    type_col = "type_slug" if "type_slug" in samples_df.columns else None
    family_count = int(samples_df[fam_col].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().nunique()) if fam_col in samples_df.columns else 0
    type_count = int(samples_df[type_col].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().nunique()) if type_col else 0
    return {
        "sample_count": int(len(samples_df)),
        "family_count": family_count,
        "type_count": type_count,
    }


def _normalized_sample_ids(series) -> list[int]:
    return (
        pd.to_numeric(series, errors="coerce")
        .dropna()
        .astype(int)
        .drop_duplicates()
        .sort_values()
        .tolist()
    )


def _build_lock_diff(samples_df, lock_path: str) -> dict[str, object]:
    if not lock_path or not Path(lock_path).is_file():
        return {
            "lock_present": False,
            "expected_locked_sample_count": 0,
            "observed_locked_sample_count": int(len(samples_df)),
            "missing_locked_ids_count": 0,
            "extra_observed_ids_count": 0,
            "missing_locked_ids_preview": [],
            "extra_observed_ids_preview": [],
        }
    lock_df = pd.read_csv(lock_path)
    if "sample_id" not in lock_df.columns or "sample_id" not in samples_df.columns:
        return {
            "lock_present": True,
            "expected_locked_sample_count": 0,
            "observed_locked_sample_count": int(len(samples_df)),
            "missing_locked_ids_count": 0,
            "extra_observed_ids_count": 0,
            "missing_locked_ids_preview": [],
            "extra_observed_ids_preview": [],
        }
    locked_ids = set(_normalized_sample_ids(lock_df["sample_id"]))
    observed_ids = set(_normalized_sample_ids(samples_df["sample_id"]))
    missing = sorted(locked_ids - observed_ids)
    extra = sorted(observed_ids - locked_ids)
    return {
        "lock_present": True,
        "expected_locked_sample_count": int(len(locked_ids)),
        "observed_locked_sample_count": int(len(observed_ids)),
        "missing_locked_ids_count": int(len(missing)),
        "extra_observed_ids_count": int(len(extra)),
        "missing_locked_ids_preview": missing[:25],
        "extra_observed_ids_preview": extra[:25],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Family label taxonomy / support audit (no ML training).")
    parser.add_argument("--profile", required=True, help="Profile id or path to YAML")
    parser.add_argument(
        "--diagnostics-dir",
        default="",
        help="Output directory for CSV/MD (default: output/diagnostics/taxonomy_audit_<utc>)",
    )
    parser.add_argument(
        "--training-min-support",
        type=int,
        default=None,
        help="Override supervised min-family threshold (default: profile cohort_gates.min_samples_per_family)",
    )
    parser.add_argument(
        "--label-column",
        default="family_id",
        help="Label column for grouping (default family_id, matching headline training)",
    )
    args = parser.parse_args()

    runtime_override_keys = [
        "RUNTIME_DIAGNOSTICS_DIR",
        "RUNTIME_RUN_ID",
        "RUNTIME_MIN_FAMILY_SUPPORT",
        "RUNTIME_EVIDENCE_MODE",
        "RUNTIME_EVIDENCE_STRICT_MODE",
        "ANALYSIS_SNAPSHOT_FILE",
        "ANALYSIS_SNAPSHOT_META_FILE",
        "ANALYSIS_SNAPSHOT_CONFLICT_FILE",
        "COHORT_SNAPSHOT_FILE",
        "COHORT_SNAPSHOT_META_FILE",
    ]
    prior_values = {key: getattr(app_config, key, None) for key in runtime_override_keys}
    try:
        profile = profile_manager.load_profile(args.profile)
        profile_id = str(profile.get("profile_id", "unknown"))
        declared_contract = paper_cohort_contract.configure_runtime_snapshot_lock(profile)
        gates = profile.get("cohort_gates") or {}
        training_min = int(
            args.training_min_support
            if args.training_min_support is not None
            else int(gates.get("min_samples_per_family", 20) or 20)
        )

        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "__taxonomy_audit"
        requested_diag = Path(args.diagnostics_dir) if str(args.diagnostics_dir).strip() else (
            Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output"))) / "diagnostics" / f"taxonomy_audit_{run_id}"
        )
        target = resolve_post_run_enrichment_target(diagnostics_dir=requested_diag, audit_id=run_id)
        out_diag = Path(target["artifact_dir"]).resolve()
        provenance_diag = Path(target["provenance_dir"]).resolve()
        run_root = Path(target["run_root"]).resolve()
        target_run_ctx = _load_target_run_context(run_root if target.get("source_run_id") else None)
        out_diag.mkdir(parents=True, exist_ok=True)
        setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(out_diag))
        setattr(app_config, "RUNTIME_RUN_ID", run_id)
        setattr(app_config, "RUNTIME_MIN_FAMILY_SUPPORT", int(gates.get("min_samples_per_family", training_min) or training_min))
        setattr(app_config, "RUNTIME_EVIDENCE_MODE", bool(profile.get("evidence_mode", False)))
        setattr(app_config, "RUNTIME_EVIDENCE_STRICT_MODE", bool(declared_contract.get("paper_locked", False)))
    # Config defaults point at global output/diagnostics/*.latest.* ; pin snapshot export to this audit dir
    # so menu-driven audits (writes under latest run diagnostics) do not clobber global operator mirrors.
        snap_csv = str(out_diag / f"analysis_snapshot_{run_id}.csv")
        snap_meta = str(out_diag / f"analysis_snapshot_{run_id}.meta.txt")
        snap_conf = str(out_diag / f"analysis_snapshot_label_conflicts_{run_id}.csv")
        setattr(app_config, "ANALYSIS_SNAPSHOT_FILE", snap_csv)
        setattr(app_config, "ANALYSIS_SNAPSHOT_META_FILE", snap_meta)
        setattr(app_config, "ANALYSIS_SNAPSHOT_CONFLICT_FILE", snap_conf)
        setattr(app_config, "COHORT_SNAPSHOT_FILE", snap_csv)
        setattr(app_config, "COHORT_SNAPSHOT_META_FILE", snap_meta)

        type_slug = profile.get("type_slug_filter")
        if type_slug in ("", "null", "None"):
            type_slug = None

        du.print_section("FAMILY LABEL TAXONOMY AUDIT (cohort load)")
        du.print_info(f"Profile: {profile_id}")
        du.print_info(f"Diagnostics dir: {out_diag}")
        if target["is_run_scoped_enrichment"]:
            du.print_info(f"Provenance ledger: {provenance_diag / 'diagnostic_provenance.json'}")
        target_run_id = str(target_run_ctx.get("target_run_id", "") or "")
        target_run_profile = str(target_run_ctx.get("target_run_profile", "") or "")
        same_profile_as_target = bool(target_run_profile and target_run_profile == profile_id)

        def _record_audit_provenance(
            *,
            artifact_paths: list[str],
            cohort_lock_status_value: str,
            observed_counts: dict | None = None,
            lock_diff: dict | None = None,
        ) -> None:
            cmd_bits = [
                "scripts/family_label_taxonomy_audit.py",
                "--profile",
                str(args.profile),
                "--label-column",
                str(args.label_column),
            ]
            if str(args.diagnostics_dir).strip():
                cmd_bits.extend(["--diagnostics-dir", str(args.diagnostics_dir)])
            if args.training_min_support is not None:
                cmd_bits.extend(["--training-min-support", str(args.training_min_support)])
            record_diagnostic_provenance(
                diagnostics_dir=provenance_diag,
                run_root=run_root,
                run_id=str(target["source_run_id"] or run_id),
                entry_id=f"post_run::{run_id}",
                generated_during_pipeline=False,
                source_command=" ".join(cmd_bits),
                source_run_id=str(target["source_run_id"] or run_id),
                artifact_paths=artifact_paths,
                lifecycle_class="post_run_enrichment",
                extra={
                    "audit_id": run_id,
                    "profile_id": profile_id,
                    "audit_profile": profile_id,
                    "target_run_id": target_run_id,
                    "target_run_profile": target_run_profile,
                    "same_profile_as_target": same_profile_as_target,
                    "cohort_lock_status": cohort_lock_status_value,
                    "expected_counts": dict(declared_contract.get("expected", {}) or {}),
                    "observed_counts": dict(observed_counts or {}),
                    "lock_diff": dict(lock_diff or {}),
                    "contract_id": declared_contract.get("contract_id"),
                },
            )

        if target_run_id:
            du.print_info(f"Target run: {target_run_id}")
            du.print_info(f"Target run profile: {target_run_profile or 'unknown'}")
            if target_run_profile and target_run_profile != profile_id:
                du.print_warning(
                    "[AUDIT] Audit profile differs from the target run profile. "
                    "This enrichment is attached to the run for operator convenience but represents a different cohort definition."
                )
        if bool(declared_contract.get("paper_locked", False)):
            sample_lock = (
                declared_contract.get("sample_id_lock", {})
                if isinstance(declared_contract.get("sample_id_lock"), dict)
                else {}
            )
            if not bool(sample_lock.get("enforceable", False)):
                du.print_error(
                    "[AUDIT] Locked profile selected but no enforceable sample-ID lock is available. "
                    "Refusing post-run audit because profile gates alone are not sufficient."
                )
                _record_audit_provenance(
                    artifact_paths=[],
                    cohort_lock_status_value="lock_unenforceable",
                    observed_counts={},
                    lock_diff={},
                )
                return 2
            du.print_info(
                f"Locked cohort contract: {declared_contract.get('contract_id')} "
                f"(expected samples={declared_contract.get('expected', {}).get('sample_count')}, "
                f"families={declared_contract.get('expected', {}).get('family_count')}, "
                f"types={declared_contract.get('expected', {}).get('type_count')})"
            )
        du.print_info("Loading cohort from database (same path as pipeline samples stage)...")

        try:
            samples_df = load_and_prepare_samples(
                profile=profile,
                profile_id=profile_id,
                type_slug=type_slug,
                run_id=run_id,
                artifact_list=[],
            )
        except Exception as exc:
            du.print_error(f"Cohort load failed: {exc}")
            return 1

        if samples_df.empty:
            du.print_error("Cohort is empty — nothing to audit.")
            return 2

        observed = _observed_counts(samples_df)
        cohort_lock_status = str(
            declared_contract.get("cohort_lock_status", "not_paper_locked") or "not_paper_locked"
        )
        lock_diff = _build_lock_diff(
            samples_df,
            str((declared_contract.get("sample_id_lock") or {}).get("path", "") or ""),
        )
        if bool(declared_contract.get("paper_locked", False)):
            try:
                runtime_contract = paper_cohort_contract.build_runtime_contract(
                    profile=profile,
                    manifest_context={},
                    samples_df=samples_df,
                )
                cohort_lock_status = str(
                    runtime_contract.get("cohort_lock_status", cohort_lock_status) or cohort_lock_status
                )
            except ValueError as exc:
                du.print_error(str(exc))
                du.print_error(
                    "[AUDIT] Locked cohort mismatch. "
                    f"Expected locked IDs={lock_diff.get('expected_locked_sample_count')} "
                    f"observed={lock_diff.get('observed_locked_sample_count')} "
                    f"missing={lock_diff.get('missing_locked_ids_count')} "
                    f"extra={lock_diff.get('extra_observed_ids_count')}."
                )
                missing_preview = lock_diff.get("missing_locked_ids_preview") or []
                extra_preview = lock_diff.get("extra_observed_ids_preview") or []
                if missing_preview:
                    du.print_info(f"[AUDIT] Missing locked ID preview: {missing_preview}")
                if extra_preview:
                    du.print_info(f"[AUDIT] Extra observed ID preview: {extra_preview}")
                cohort_lock_status = "locked_mismatch"
                _record_audit_provenance(
                    artifact_paths=[],
                    cohort_lock_status_value=cohort_lock_status,
                    observed_counts=observed,
                    lock_diff=lock_diff,
                )
                return 3

        paths = fam_audit.write_family_label_taxonomy_audit(
            samples_df,
            diagnostics_dir=out_diag,
            profile_id=profile_id,
            training_min_support=training_min,
            run_id=run_id,
            label_col=str(args.label_column),
            print_fn=lambda s: du.print_info(s),
        )
        _record_audit_provenance(
            artifact_paths=[str(v) for k, v in paths.items() if k != "run_id"],
            cohort_lock_status_value=cohort_lock_status,
            observed_counts=observed,
            lock_diff=lock_diff,
        )
        du.print_success("Wrote:")
        for k, p in paths.items():
            if k == "run_id":
                continue
            du.print_info(f"  {p}")
        return 0
    finally:
        for key, value in prior_values.items():
            setattr(app_config, key, value)


if __name__ == "__main__":
    raise SystemExit(main())
