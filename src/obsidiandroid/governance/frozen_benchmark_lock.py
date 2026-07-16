"""Pure cohort, duplicate, lineage, and split locks for frozen benchmarks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

from obsidiandroid.common.family_label_semantics import is_family_placeholder_token
from obsidiandroid.common.hash_utils import hash_payload


COHORT_ID = "android_malware_major_families_frozen_n20_v1"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_PACKAGE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){1,}$")
_GENERIC_PACKAGES = {"android", "com.android", "unknown", "none", "null", "n/a"}


@dataclass(frozen=True)
class FrozenCohortLock:
    frame: pd.DataFrame
    payload: dict[str, Any]


def _valid_package(value: object) -> str:
    token = str(value or "").strip().lower()
    return token if token not in _GENERIC_PACKAGES and _PACKAGE.fullmatch(token) else ""


def _validate_labels(frame: pd.DataFrame) -> None:
    required = {"sample_id", "sha256", "family_id", "family_canonical"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Frozen cohort missing columns: {sorted(missing)}")
    labels = frame["family_canonical"].fillna("").astype(str).str.strip()
    if labels.eq("").any() or labels.map(is_family_placeholder_token).any():
        raise ValueError("Frozen cohort contains missing or numeric family placeholders.")


def _canonical_duplicate_rows(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = frame.copy()
    work["sample_id"] = pd.to_numeric(work["sample_id"], errors="raise").astype(int)
    work["sha256"] = work["sha256"].fillna("").astype(str).str.strip().str.lower()
    if (~work["sha256"].map(lambda value: bool(_SHA.fullmatch(value)))).any():
        raise ValueError("Frozen cohort contains invalid SHA-256 values.")
    label_counts = work.groupby("sha256")["family_id"].nunique()
    conflicts = label_counts[label_counts > 1]
    if not conflicts.empty:
        raise ValueError("Duplicate SHA-256 group has conflicting canonical family labels.")
    work = work.sort_values(["sha256", "sample_id"]).copy()
    work["duplicate_resolution"] = work.duplicated("sha256", keep="first").map(
        {True: "excluded_duplicate_sha", False: "retained_canonical_sample_id"}
    )
    ledger = work[["sha256", "sample_id", "family_id", "family_canonical", "duplicate_resolution"]].copy()
    retained = work[work["duplicate_resolution"] == "retained_canonical_sample_id"].copy()
    return retained, ledger


def _lineage_components(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy().reset_index(drop=True)
    package = (
        work["android_package_name"]
        if "android_package_name" in work
        else work["package_name"]
        if "package_name" in work
        else pd.Series("", index=work.index, dtype="object")
    )
    work["_package"] = package.map(_valid_package)
    parent = list(range(len(work)))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: int, right: int) -> None:
        left, right = find(left), find(right)
        if left != right:
            parent[right] = left

    for column in ("sha256", "_package"):
        for _, indices in work.groupby(column, dropna=False).groups.items():
            values = list(indices)
            if column == "_package" and not str(work.loc[values[0], column]):
                continue
            for index in values[1:]:
                union(values[0], index)
    work["lineage_component_id"] = [f"lc_{find(index):08d}" for index in range(len(work))]
    conflict = work.groupby("lineage_component_id")["family_id"].nunique().gt(1)
    if conflict.any():
        raise ValueError("CROSS_FAMILY_COMPONENT: resolve shared-package family conflicts before locking.")
    work["lineage_link_reason"] = work["_package"].map(lambda value: "package_or_sha" if value else "sha_only")
    return work.drop(columns=["_package"])


def freeze_cohort(frame: pd.DataFrame, *, min_total_support: int = 20, max_component_share: float = 0.80) -> FrozenCohortLock:
    """Validate, canonicalize, and lock a cohort before any feature fitting."""
    _validate_labels(frame)
    retained, duplicate_ledger = _canonical_duplicate_rows(frame)
    locked = _lineage_components(retained)
    support = locked.groupby("family_id").size()
    component_support = locked.groupby(["family_id", "lineage_component_id"]).size()
    component_n = component_support.groupby(level=0).size()
    max_share = component_support.groupby(level=0).max() / support
    eligible = support.index[
        (support >= int(min_total_support))
        & (component_n >= 3)
        & (max_share <= float(max_component_share))
    ]
    locked = locked[locked["family_id"].isin(eligible)].copy().sort_values("sample_id").reset_index(drop=True)
    if locked.empty:
        raise ValueError("No cohort families satisfy frozen support and lineage requirements.")
    payload = {
        "cohort_id": COHORT_ID,
        "min_total_support": int(min_total_support),
        "max_component_share": float(max_component_share),
        "ordered_family_ids": sorted(map(int, locked["family_id"].unique())),
        "sample_id_hash": hash_payload(locked["sample_id"].astype(int).tolist()),
        "label_hash": hash_payload(locked[["sample_id", "family_id", "family_canonical"]].to_dict("records")),
        "lineage_hash": hash_payload(locked[["sample_id", "lineage_component_id"]].to_dict("records")),
        "duplicate_resolution_ledger": duplicate_ledger.to_dict("records"),
    }
    payload["cohort_hash"] = hash_payload(payload)
    return FrozenCohortLock(locked, payload)


def create_frozen_group_split(lock: FrozenCohortLock, *, seed: int = 42) -> pd.DataFrame:
    """Choose one valid 80/20 family-stratified lineage-group split or fail."""
    frame = lock.frame.reset_index(drop=True)
    y = frame["family_id"].astype(int).to_numpy()
    groups = frame["lineage_component_id"].to_numpy()
    candidates: list[tuple[tuple[float, float, int], pd.DataFrame]] = []
    for fold, (train_index, test_index) in enumerate(StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed).split(frame, y, groups)):
        split = frame[["sample_id", "family_id", "family_canonical", "sha256", "lineage_component_id"]].copy()
        split["split_role"] = "train"
        split.loc[test_index, "split_role"] = "test"
        train_counts = split[split["split_role"] == "train"].groupby("family_id").size()
        test_counts = split[split["split_role"] == "test"].groupby("family_id").size()
        test_components = split[split["split_role"] == "test"].groupby("family_id")["lineage_component_id"].nunique()
        if (train_counts < 15).any() or (test_counts < 4).any() or (test_components < 2).any():
            continue
        family_total = split.groupby("family_id").size()
        deviation = max(abs((test_counts / family_total) - 0.20))
        size_deviation = abs(len(test_index) / len(frame) - 0.20)
        candidates.append(((float(deviation), float(size_deviation), fold), split))
    if not candidates:
        raise ValueError("No candidate fold satisfies frozen family and component support requirements.")
    _, chosen = min(candidates, key=lambda item: item[0])
    chosen["split_seed"] = int(seed)
    chosen["split_algorithm"] = "stratified_group_kfold_holdout_v1"
    chosen["cohort_hash"] = lock.payload["cohort_hash"]
    chosen["split_hash"] = hash_payload(chosen.sort_values("sample_id").to_dict("records"))
    return chosen.sort_values("sample_id").reset_index(drop=True)
