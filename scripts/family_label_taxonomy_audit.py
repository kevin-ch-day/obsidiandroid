#!/usr/bin/env python3
"""Fast family label-space audit (cohort load only — no model training).

Loads the same prepared cohort as the pipeline for a profile, then writes:
  - diagnostics/family_label_taxonomy_audit.csv
  - diagnostics/family_label_taxonomy_audit.md
  - diagnostics/support_threshold_preview.csv
  - diagnostics/support_threshold_preview.md

Example:
  python scripts/family_label_taxonomy_audit.py --profile research_all_malicious
  python scripts/family_label_taxonomy_audit.py --profile research_all_malicious \\
      --diagnostics-dir output/runs/my_audit/diagnostics
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()

from config import app_config
from obsidiandroid.cli import profile_manager
from obsidiandroid.cli.ui import display as du
from obsidiandroid.diagnostics import family_label_taxonomy_audit as fam_audit
from obsidiandroid.pipeline.stage_samples import load_and_prepare_samples


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

    profile = profile_manager.load_profile(args.profile)
    profile_id = str(profile.get("profile_id", "unknown"))
    gates = profile.get("cohort_gates") or {}
    training_min = int(
        args.training_min_support
        if args.training_min_support is not None
        else int(gates.get("min_samples_per_family", 20) or 20)
    )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "__taxonomy_audit"
    out_diag = Path(args.diagnostics_dir) if str(args.diagnostics_dir).strip() else (
        Path(str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output"))) / "diagnostics" / f"taxonomy_audit_{run_id}"
    )
    out_diag = out_diag.resolve()
    out_diag.mkdir(parents=True, exist_ok=True)
    setattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", str(out_diag))
    setattr(app_config, "RUNTIME_RUN_ID", run_id)
    setattr(app_config, "RUNTIME_MIN_FAMILY_SUPPORT", int(gates.get("min_samples_per_family", training_min) or training_min))

    type_slug = profile.get("type_slug_filter")
    if type_slug in ("", "null", "None"):
        type_slug = None

    du.print_section("FAMILY LABEL TAXONOMY AUDIT (cohort load)")
    du.print_info(f"Profile: {profile_id}")
    du.print_info(f"Diagnostics dir: {out_diag}")
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

    paths = fam_audit.write_family_label_taxonomy_audit(
        samples_df,
        diagnostics_dir=out_diag,
        profile_id=profile_id,
        training_min_support=training_min,
        run_id=run_id,
        label_col=str(args.label_column),
        print_fn=lambda s: du.print_info(s),
    )
    du.print_success("Wrote:")
    for k, p in paths.items():
        if k == "run_id":
            continue
        du.print_info(f"  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
