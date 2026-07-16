"""Immutable cohort-lock manifest helpers.

This module defines the canonical lock artifact that paper-facing locked
profiles should use to resolve cohort identity. The lock manifest is the
source of truth for frozen membership counts and hashes; live SQL may later
report drift relative to that immutable artifact, but should not redefine it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import json
import pandas as pd

from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.common.repo_paths import repo_root
from obsidiandroid.governance.label_snapshot_contract import label_snapshot_hash


DEFAULT_LOCK_MANIFEST_FILENAME = "cohort_lock_manifest.json"


def resolve_lock_manifest_path(raw_lock: dict[str, Any]) -> Path | None:
    """Resolve the canonical lock-manifest path from a profile lock block."""
    raw_path = str(raw_lock.get("cohort_lock_manifest_file", "") or "").strip()
    if raw_path:
        path = Path(raw_path)
        if not path.is_absolute():
            path = repo_root() / path
        return path.resolve()
    baseline_root = str(raw_lock.get("baseline_artifact_root", "") or "").strip()
    if not baseline_root:
        return None
    root_path = Path(baseline_root)
    if not root_path.is_absolute():
        root_path = repo_root() / root_path
    return (root_path / DEFAULT_LOCK_MANIFEST_FILENAME).resolve()


def load_lock_manifest(raw_lock: dict[str, Any]) -> dict[str, Any] | None:
    """Load a lock manifest when one is configured and exists."""
    path = resolve_lock_manifest_path(raw_lock)
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Lock manifest must be a JSON object: {path}")
    normalized = dict(payload)
    normalized["manifest_path"] = str(path)
    normalized["baseline_artifact_root"] = str(path.parent)
    member_path = str(normalized.get("member_list_path", "") or "").strip()
    if member_path:
        member_obj = Path(member_path)
        if not member_obj.is_absolute():
            member_obj = path.parent / member_obj
        normalized["member_list_path"] = str(member_obj.resolve())
    label_snapshot_path = str(normalized.get("label_snapshot_path", "") or "").strip()
    if label_snapshot_path:
        snapshot_obj = Path(label_snapshot_path)
        if not snapshot_obj.is_absolute():
            snapshot_obj = path.parent / snapshot_obj
        normalized["label_snapshot_path"] = str(snapshot_obj.resolve())
    return normalized


def validate_lock_manifest(*, manifest: dict[str, Any], manifest_path: Path) -> None:
    """Validate the minimum immutable cohort-lock manifest contract."""
    required = {
        "lock_version",
        "profile_id",
        "contract_id",
        "created_at_utc",
        "member_list_path",
        "sample_count",
        "family_count",
        "type_count",
        "cohort_hash",
        "taxonomy_hash",
        "time_window",
    }
    missing = sorted(required - set(manifest))
    if missing:
        raise ValueError(f"Lock manifest '{manifest_path}' missing required keys: {missing}")

    for key in ("sample_count", "family_count", "type_count"):
        value = manifest.get(key)
        if not isinstance(value, int) or value <= 0:
            raise ValueError(f"Lock manifest '{manifest_path}' key '{key}' must be a positive integer.")

    member_path = Path(str(manifest.get("member_list_path", "") or ""))
    if not member_path.is_absolute():
        member_path = manifest_path.parent / member_path
    if not member_path.exists():
        raise ValueError(
            f"Lock manifest '{manifest_path}' member_list_path does not exist: {member_path}"
        )
    if not str(manifest.get("cohort_hash", "") or "").strip():
        raise ValueError(f"Lock manifest '{manifest_path}' must declare a non-empty cohort_hash.")
    if not str(manifest.get("taxonomy_hash", "") or "").strip():
        raise ValueError(f"Lock manifest '{manifest_path}' must declare a non-empty taxonomy_hash.")
    member_df = read_member_list(member_path)
    observed_count = int(len(member_df))
    if observed_count != int(manifest.get("sample_count", 0) or 0):
        raise ValueError(
            f"Lock manifest '{manifest_path}' sample_count mismatch: "
            f"manifest={manifest.get('sample_count')} member_list={observed_count}"
        )
    observed_hash = compute_cohort_hash_from_member_list(member_df)
    if observed_hash != str(manifest.get("cohort_hash", "") or ""):
        raise ValueError(
            f"Lock manifest '{manifest_path}' cohort_hash mismatch: "
            f"manifest={manifest.get('cohort_hash')} member_list={observed_hash}"
        )

    # Older locks may not have retained a row-level label snapshot.  Once a
    # lock declares one, however, validate it as an immutable component of the
    # cohort rather than merely recording its path for operator convenience.
    snapshot_path_raw = str(manifest.get("label_snapshot_path", "") or "").strip()
    snapshot_hash_declared = str(manifest.get("label_snapshot_hash", "") or "").strip()
    # The accepted historical manifest predates snapshot-path retention: it
    # carries a recorded label hash but no file pointer. Preserve that artifact
    # as legacy evidence. New manifests exported by this code always include
    # both fields and therefore receive the strict verification below.
    if snapshot_path_raw and not snapshot_hash_declared:
        raise ValueError(
            f"Lock manifest '{manifest_path}' declares label_snapshot_path without "
            "the required label_snapshot_hash."
        )
    if snapshot_path_raw:
        snapshot_path = Path(snapshot_path_raw)
        if not snapshot_path.is_absolute():
            snapshot_path = manifest_path.parent / snapshot_path
        if not snapshot_path.exists():
            raise ValueError(
                f"Lock manifest '{manifest_path}' label_snapshot_path does not exist: "
                f"{snapshot_path}"
            )
        observed_snapshot_hash = label_snapshot_hash(pd.read_csv(snapshot_path))
        if not observed_snapshot_hash:
            raise ValueError(
                f"Lock manifest '{manifest_path}' label snapshot is missing the required "
                "row-level label fields."
            )
        if observed_snapshot_hash != snapshot_hash_declared:
            raise ValueError(
                f"Lock manifest '{manifest_path}' label_snapshot_hash mismatch: "
                f"manifest={snapshot_hash_declared} observed={observed_snapshot_hash}"
            )
        if str(manifest.get("taxonomy_hash", "") or "") != observed_snapshot_hash:
            raise ValueError(
                f"Lock manifest '{manifest_path}' taxonomy_hash must equal the validated "
                "row-level label snapshot hash."
            )


def compute_cohort_hash_from_member_list(member_df: pd.DataFrame) -> str:
    """Compute a stable cohort hash from sorted member sample IDs."""
    if "sample_id" not in member_df.columns:
        return ""
    ids = (
        pd.to_numeric(member_df["sample_id"], errors="coerce")
        .dropna()
        .astype(int)
        .drop_duplicates()
        .sort_values()
        .tolist()
    )
    return hash_payload(ids)


def read_member_list(member_list_path: str | Path) -> pd.DataFrame:
    """Read a canonical lock member list and normalize ordering."""
    path = Path(member_list_path)
    df = pd.read_csv(path)
    if "sample_id" not in df.columns:
        raise ValueError(f"Lock member list missing sample_id column: {path}")
    out = df.copy()
    out["sample_id"] = pd.to_numeric(out["sample_id"], errors="coerce")
    out = out.dropna(subset=["sample_id"])
    out["sample_id"] = out["sample_id"].astype(int)
    return out.sort_values("sample_id", kind="mergesort").drop_duplicates("sample_id")


def build_lock_manifest_payload(
    *,
    lock_version: str,
    profile_id: str,
    contract_id: str,
    created_at_utc: str,
    canonical_historical_run_id: str,
    member_list_path: str,
    sample_count: int,
    family_count: int,
    type_count: int,
    cohort_hash: str,
    taxonomy_hash: str,
    sql_profile_version: str,
    profile_version: str,
    time_window: dict[str, Any],
    label_snapshot_path: str | None = None,
    label_snapshot_hash: str | None = None,
    top_family_support: int | None = None,
    top_family_share: float | None = None,
    label_target_class_stats: list[dict[str, Any]] | None = None,
    source_artifacts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a canonical immutable cohort-lock manifest payload."""
    return {
        "schema_version": "1.0",
        "lock_version": str(lock_version),
        "profile_id": str(profile_id),
        "contract_id": str(contract_id),
        "canonical_historical_run_id": str(canonical_historical_run_id),
        "created_at_utc": str(created_at_utc),
        "member_list_path": str(member_list_path),
        "sample_count": int(sample_count),
        "family_count": int(family_count),
        "type_count": int(type_count),
        "cohort_hash": str(cohort_hash),
        "taxonomy_hash": str(taxonomy_hash),
        "label_snapshot_path": str(label_snapshot_path or ""),
        "label_snapshot_hash": str(label_snapshot_hash or ""),
        "sql_profile_version": str(sql_profile_version),
        "profile_version": str(profile_version),
        "time_window": dict(time_window),
        "top_family_support": int(top_family_support) if top_family_support is not None else None,
        "top_family_share": float(top_family_share) if top_family_share is not None else None,
        "label_target_class_stats": list(label_target_class_stats or []),
        "source_artifacts": dict(source_artifacts or {}),
    }
