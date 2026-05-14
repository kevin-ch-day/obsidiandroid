"""Backfill results warehouse tables from an existing permission-trends bundle.

This utility is intended for runs where artifacts were already generated to:
`output/runs/<run_id>/bundles/permission_trends`
but DB persistence was disabled at runtime.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.runtime_bootstrap  # noqa: F401

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

ensure_repo_src_on_sys_path()

from config import app_config

from obsidiandroid.pipeline import stage_results_warehouse

persist_permission_trends_results = stage_results_warehouse.persist_permission_trends_results


def _read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV file into a DataFrame.

    Args:
        path: CSV file path.

    Returns:
        DataFrame loaded from path.
    """
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    return pd.read_csv(path)


def _load_bundle_manifest(bundle_dir: Path) -> dict:
    """Load bundle manifest if present."""
    manifest_path = bundle_dir / "contracts" / "permission_trends_bundle_manifest.json"
    if not manifest_path.exists():
        return {}
    with manifest_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def _artifact_path_from_manifest(bundle_dir: Path, manifest: dict, artifact_id: str) -> Path | None:
    """Resolve artifact path by canonical id from bundle manifest."""
    artifacts = manifest.get("artifacts", []) if isinstance(manifest, dict) else []
    if not isinstance(artifacts, list):
        return None
    for entry in artifacts:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("artifact_id", "")).strip() != str(artifact_id).strip():
            continue
        rel = str(entry.get("relative_path", "")).strip()
        if not rel:
            continue
        candidate = (bundle_dir / rel).resolve()
        if candidate.exists():
            return candidate
    return None


def _resolve_csv_by_artifact_id(
    *,
    bundle_dir: Path,
    manifest: dict,
    artifact_id: str,
    legacy_stems: list[str],
    run_id: str,
) -> pd.DataFrame:
    """Resolve CSV using manifest artifact_id with legacy fallback."""
    path = _artifact_path_from_manifest(bundle_dir, manifest, artifact_id)
    if path is not None:
        return pd.read_csv(path)
    for stem in legacy_stems:
        try:
            return _resolve_csv(bundle_dir, stem, run_id)
        except FileNotFoundError:
            continue
    raise FileNotFoundError(
        f"Missing CSV artifact_id='{artifact_id}' and legacy stems={legacy_stems} in {bundle_dir}"
    )


def _resolve_json_by_artifact_id(
    *,
    bundle_dir: Path,
    manifest: dict,
    artifact_id: str,
    legacy_stems: list[str],
    run_id: str,
) -> dict:
    """Resolve JSON using manifest artifact_id with legacy fallback."""
    path = _artifact_path_from_manifest(bundle_dir, manifest, artifact_id)
    if path is not None:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    for stem in legacy_stems:
        try:
            return _resolve_json(bundle_dir, stem, run_id)
        except FileNotFoundError:
            continue
    raise FileNotFoundError(
        f"Missing JSON artifact_id='{artifact_id}' and legacy stems={legacy_stems} in {bundle_dir}"
    )


def _resolve_top_family_stem_from_manifest(manifest: dict, prefix: str, fallback_stem: str) -> str:
    """Resolve dynamic top{N} stem from manifest artifact IDs."""
    artifacts = manifest.get("artifacts", []) if isinstance(manifest, dict) else []
    if not isinstance(artifacts, list):
        return fallback_stem
    pattern = re.compile(rf"^{re.escape(prefix)}_top\d+$")
    for entry in artifacts:
        artifact_id = str(entry.get("artifact_id", "")).strip()
        if pattern.match(artifact_id):
            return artifact_id
    return fallback_stem


def _resolve_csv(bundle_dir: Path, stem: str, run_id: str) -> pd.DataFrame:
    """Load run-scoped CSV when present, else fallback to latest CSV."""
    run_path = bundle_dir / f"{stem}_{run_id}.csv"
    latest_path = bundle_dir / f"{stem}.latest.csv"
    if run_path.exists():
        return pd.read_csv(run_path)
    if latest_path.exists():
        return pd.read_csv(latest_path)
    raise FileNotFoundError(f"Missing both run/latest CSV for {stem} in {bundle_dir}")


def _resolve_json(bundle_dir: Path, stem: str, run_id: str) -> dict:
    """Load run-scoped JSON when present, else fallback to latest JSON."""
    run_path = bundle_dir / f"{stem}_{run_id}.json"
    latest_path = bundle_dir / f"{stem}.latest.json"
    path = run_path if run_path.exists() else latest_path
    if not path.exists():
        raise FileNotFoundError(f"Missing both run/latest JSON for {stem} in {bundle_dir}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
    parser = argparse.ArgumentParser(
        description="Persist permission-trends artifacts for a run into MariaDB tables."
    )
    parser.add_argument(
        "--output-root",
        default=str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")),
        help="Output root containing runs/ (default: DEFAULT_OUTPUT_DIR).",
    )
    parser.add_argument("--run-id", required=True, help="Pipeline run ID.")
    parser.add_argument(
        "--profile-id",
        default=None,
        help="Profile ID override. Defaults to profile_id from coverage CSV.",
    )
    parser.add_argument(
        "--bundle-dir",
        default=None,
        help="Override bundle directory. Defaults to output/runs/<run_id>/bundles/permission_trends.",
    )
    parser.add_argument(
        "--snapshot-csv",
        default=None,
        help="Snapshot CSV path (must contain sample_id, sha256, family_id, family_canonical, type_slug).",
    )
    return parser


def _resolve_run_root(*, output_root: Path, run_id: str) -> Path:
    """Resolve and validate run root under the configured output root."""
    root = output_root.resolve()
    run_root = (root / "runs" / run_id).resolve()
    if root not in run_root.parents:
        raise ValueError(f"Run root escapes output_root: run_root={run_root} output_root={root}")
    return run_root


def main() -> None:
    """Run warehouse backfill for one permission-trends bundle."""
    args = _parser().parse_args()
    run_id = args.run_id.strip()
    if not run_id:
        raise ValueError("run_id must be non-empty")
    output_root = Path(str(args.output_root))
    run_root = _resolve_run_root(output_root=output_root, run_id=run_id)

    bundle_dir = (
        Path(args.bundle_dir)
        if args.bundle_dir
        else run_root / "bundles" / "permission_trends"
    )
    if args.bundle_dir:
        bundle_dir = Path(args.bundle_dir).resolve()
        if run_root.resolve() not in bundle_dir.parents:
            raise ValueError(
                f"Bundle directory must be under run root: bundle_dir={bundle_dir} run_root={run_root}"
            )
    if not bundle_dir.exists():
        raise FileNotFoundError(f"Bundle directory not found: {bundle_dir}")
    manifest = _load_bundle_manifest(bundle_dir)
    family_profiles_stem = _resolve_top_family_stem_from_manifest(
        manifest,
        prefix="family_permission_profiles",
        fallback_stem="family_permission_profiles_topN",
    )
    family_entropy_stem = _resolve_top_family_stem_from_manifest(
        manifest,
        prefix="family_permission_entropy",
        fallback_stem="family_permission_entropy_topN",
    )
    family_jsd_stem = _resolve_top_family_stem_from_manifest(
        manifest,
        prefix="family_jsd_matrix",
        fallback_stem="family_jsd_matrix_topN",
    )

    snapshot_csv = (
        Path(str(args.snapshot_csv))
        if args.snapshot_csv
        else output_root / "diagnostics" / "analysis_snapshot.latest.csv"
    )
    sample_core_df = _read_csv(snapshot_csv)
    coverage_df = _resolve_csv_by_artifact_id(
        bundle_dir=bundle_dir,
        manifest=manifest,
        artifact_id="permission_coverage_report",
        legacy_stems=["permission_coverage_report"],
        run_id=run_id,
    )
    dangerous_df = _resolve_csv_by_artifact_id(
        bundle_dir=bundle_dir,
        manifest=manifest,
        artifact_id="dangerous_permission_distribution_by_type",
        legacy_stems=["dangerous_distribution_by_type"],
        run_id=run_id,
    )
    type_prevalence_df = _resolve_csv_by_artifact_id(
        bundle_dir=bundle_dir,
        manifest=manifest,
        artifact_id="type_permission_prevalence",
        legacy_stems=["type_permission_prevalence"],
        run_id=run_id,
    )
    family_profiles_df = _resolve_csv_by_artifact_id(
        bundle_dir=bundle_dir,
        manifest=manifest,
        artifact_id=family_profiles_stem,
        legacy_stems=[family_profiles_stem, "family_permission_profiles_topN"],
        run_id=run_id,
    )
    type_entropy_df = _resolve_csv_by_artifact_id(
        bundle_dir=bundle_dir,
        manifest=manifest,
        artifact_id="type_permission_entropy",
        legacy_stems=["type_permission_entropy"],
        run_id=run_id,
    )
    family_entropy_df = _resolve_csv_by_artifact_id(
        bundle_dir=bundle_dir,
        manifest=manifest,
        artifact_id=family_entropy_stem,
        legacy_stems=[family_entropy_stem, "family_permission_entropy_topN"],
        run_id=run_id,
    )
    jsd_df = _resolve_csv_by_artifact_id(
        bundle_dir=bundle_dir,
        manifest=manifest,
        artifact_id=family_jsd_stem,
        legacy_stems=[family_jsd_stem, "family_jsd_matrix_topN"],
        run_id=run_id,
    )
    banker_enrichment_df = _resolve_csv_by_artifact_id(
        bundle_dir=bundle_dir,
        manifest=manifest,
        artifact_id="banker_permission_enrichment",
        legacy_stems=["banker_permission_enrichment"],
        run_id=run_id,
    )
    discriminability_df = _resolve_csv_by_artifact_id(
        bundle_dir=bundle_dir,
        manifest=manifest,
        artifact_id="permission_discriminability_rank",
        legacy_stems=["permission_discriminability_rank"],
        run_id=run_id,
    )
    consensus_df = _resolve_csv_by_artifact_id(
        bundle_dir=bundle_dir,
        manifest=manifest,
        artifact_id="consensus_distribution",
        legacy_stems=["consensus_distribution"],
        run_id=run_id,
    )
    per_family_perf_df = _resolve_csv_by_artifact_id(
        bundle_dir=bundle_dir,
        manifest=manifest,
        artifact_id="per_family_performance_spread",
        legacy_stems=["per_family_performance_spread"],
        run_id=run_id,
    )
    banker_cluster_assignments_df = _resolve_csv_by_artifact_id(
        bundle_dir=bundle_dir,
        manifest=manifest,
        artifact_id="banker_family_pattern_clusters",
        legacy_stems=["banker_family_pattern_clusters"],
        run_id=run_id,
    )
    banker_cluster_profiles_df = _resolve_csv_by_artifact_id(
        bundle_dir=bundle_dir,
        manifest=manifest,
        artifact_id="banker_family_cluster_profiles",
        legacy_stems=["banker_family_cluster_profiles"],
        run_id=run_id,
    )
    try:
        temporal_trends_df = _resolve_csv_by_artifact_id(
            bundle_dir=bundle_dir,
            manifest=manifest,
            artifact_id="banker_permission_trends_over_time",
            legacy_stems=["banker_permission_trends_over_time"],
            run_id=run_id,
        )
    except FileNotFoundError:
        temporal_trends_df = pd.DataFrame()

    banker_enrichment_by_view_df = pd.concat(
        [
            banker_enrichment_df.assign(view_mode="aosp_only"),
            _resolve_csv_by_artifact_id(
                bundle_dir=bundle_dir,
                manifest=manifest,
                artifact_id="banker_permission_enrichment_inclusive",
                legacy_stems=["banker_permission_enrichment_inclusive"],
                run_id=run_id,
            ).assign(
                view_mode="inclusive"
            ),
            _resolve_csv_by_artifact_id(
                bundle_dir=bundle_dir,
                manifest=manifest,
                artifact_id="banker_permission_enrichment_ecosystem",
                legacy_stems=["banker_permission_enrichment_ecosystem"],
                run_id=run_id,
            ).assign(
                view_mode="ecosystem"
            ),
        ],
        ignore_index=True,
    )

    bundle_metadata = _resolve_json_by_artifact_id(
        bundle_dir=bundle_dir,
        manifest=manifest,
        artifact_id="bundle_metadata",
        legacy_stems=["bundle_metadata"],
        run_id=run_id,
    )

    profile_id = args.profile_id or str(coverage_df.iloc[0].get("profile_id", "all_malicious"))
    artifact_paths = [str(path) for path in bundle_dir.iterdir() if path.is_file()]

    persist_permission_trends_results(
        run_id=run_id,
        profile_id=profile_id,
        bundle_metadata=bundle_metadata,
        sample_core_df=sample_core_df,
        coverage_df=coverage_df,
        dangerous_df=dangerous_df,
        type_prevalence_df=type_prevalence_df,
        family_profiles_df=family_profiles_df,
        type_entropy_df=type_entropy_df,
        family_entropy_df=family_entropy_df,
        jsd_df=jsd_df,
        banker_enrichment_df=banker_enrichment_df,
        discriminability_df=discriminability_df,
        consensus_df=consensus_df,
        per_family_perf_df=per_family_perf_df,
        artifact_paths=artifact_paths,
        banker_enrichment_by_view_df=banker_enrichment_by_view_df,
        banker_cluster_assignments_df=banker_cluster_assignments_df,
        banker_cluster_profiles_df=banker_cluster_profiles_df,
        temporal_trends_df=temporal_trends_df,
    )
    print(f"Warehouse backfill complete for run_id={run_id}")


if __name__ == "__main__":
    main()
