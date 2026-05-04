"""Run path resolution, cohort hashing, and optional canonical heatmap publishing."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

from config import app_config
from utils import display_utils as du
from obsidiandroid.common import output_paths
from utils.hash_utils import hash_payload

from analysis.pipeline.permission_trends.constants import (
    PERMISSION_ALIAS_MAP_VERSION,
    PRIMARY_PERMISSION_VIEW,
    RUN_SUFFIX_PNG_PATTERN,
)


def compute_cohort_hash(sample_core_df: pd.DataFrame) -> str:
    """Compute deterministic cohort identity hash for paper artifact versioning."""
    if not isinstance(sample_core_df, pd.DataFrame) or sample_core_df.empty:
        return hash_payload({"sample_ids": []})
    sample_ids = (
        pd.to_numeric(sample_core_df.get("sample_id"), errors="coerce")
        .dropna()
        .astype(int)
        .sort_values()
        .tolist()
    )
    return hash_payload({"sample_ids": sample_ids})


def resolve_run_root_for_run_id(run_id: str) -> Path:
    """Resolve canonical run root using runtime override when available."""
    run_id_clean = str(run_id).strip()
    runtime_root_raw = str(getattr(app_config, "RUNTIME_RUN_ROOT", "") or "").strip()
    if runtime_root_raw:
        runtime_root = Path(runtime_root_raw)
        if not run_id_clean or runtime_root.name == run_id_clean:
            return runtime_root
    if run_id_clean:
        return output_paths.runs_root() / run_id_clean
    return output_paths.output_root()


def compute_permission_feature_hash(kept_permissions_by_view: dict[str, list[str]]) -> str:
    """Compute deterministic feature identity hash for permission-view contract."""
    payload = {
        "primary_view": PRIMARY_PERMISSION_VIEW,
        "permission_alias_map_version": PERMISSION_ALIAS_MAP_VERSION,
        "kept_permissions_by_view": {
            str(key): sorted([str(value) for value in values])
            for key, values in sorted(kept_permissions_by_view.items(), key=lambda item: str(item[0]))
        },
    }
    return hash_payload(payload)


def publish_canonical_type_heatmap(
    source_path: str | None,
    run_id: str,
    cohort_hash: str,
    permission_feature_hash: str,
    type_heatmap_identity: str,
) -> list[str]:
    """Publish canonical type heatmap into run-scoped and mutable latest workspaces."""
    if not bool(getattr(app_config, "ENABLE_LEGACY_CANONICAL_HEATMAP_EXPORT", False)):
        return []
    if not source_path:
        return []
    src = Path(source_path)
    if not src.exists():
        return []
    run_paper_dir = output_paths.runs_root() / str(run_id) / "paper"
    latest_dir = output_paths.latest_root()
    run_paper_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)

    run_path = run_paper_dir / "type_permission_heatmap.png"
    latest_path = latest_dir / "type_permission_heatmap.png"
    shutil.copy2(src, run_path)
    shutil.copy2(src, latest_path)

    identity_path = latest_dir / "type_permission_heatmap.identity.json"
    identity_payload = {
        "run_id": str(run_id),
        "cohort_hash": str(cohort_hash),
        "permission_feature_hash": str(permission_feature_hash),
        "type_permission_heatmap_identity": str(type_heatmap_identity),
        "source_artifact": str(src),
    }
    identity_path.write_text(json.dumps(identity_payload, indent=2, sort_keys=True), encoding="utf-8")
    return [str(run_path), str(latest_path), str(identity_path)]


def prune_run_stamped_pngs_in_latest_bundle(bundle_dir: Path) -> list[str]:
    """Delete legacy run-suffixed PNGs in mutable latest permission bundle."""
    if not isinstance(bundle_dir, Path) or not bundle_dir.exists():
        return []
    if bundle_dir.name != "permission_trends":
        return []
    removed: list[str] = []
    for png_path in bundle_dir.rglob("*.png"):
        if not RUN_SUFFIX_PNG_PATTERN.match(png_path.name):
            continue
        try:
            png_path.unlink()
            removed.append(str(png_path))
        except Exception:
            continue
    return removed
