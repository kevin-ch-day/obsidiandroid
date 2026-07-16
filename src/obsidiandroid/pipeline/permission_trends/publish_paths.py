"""Run path resolution, cohort hashing, and latest-bundle cleanup helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from config import app_config
from obsidiandroid.common import output_paths
from obsidiandroid.common.hash_utils import hash_payload

from obsidiandroid.pipeline.permission_trends.constants import (
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
        if not run_id_clean:
            return runtime_root
        active_run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "") or "").strip()
        if not active_run_id or run_id_clean == active_run_id:
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
