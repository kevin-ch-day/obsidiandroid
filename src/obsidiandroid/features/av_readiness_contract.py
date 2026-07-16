"""Outer-train engine-readiness contract for frozen AV arm C."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.features.av_detection_contract import classify_av_row, select_coherent_report_snapshot
from obsidiandroid.pipeline.engine_normalization import canonicalize_engine_name, load_engine_aliases


READINESS_POLICY = {
    "minimum_scans": 10,
    "minimum_coverage_percentage": 20.0,
    "minimum_positive_detections": 5,
    "minimum_detection_percentage": 1.0,
    "exclude_zero_detections": True,
    "active_only": True,
    "trusted_only": False,
}


@dataclass(frozen=True)
class AVReadinessContract:
    eligible_engines: tuple[str, ...]
    ledger: pd.DataFrame
    policy_hash: str
    train_id_hash: str
    eligibility_hash: str


def _flag(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "active", "trusted"}


def fit_av_readiness_contract(
    rows: pd.DataFrame,
    engine_metadata: pd.DataFrame,
    train_sample_ids: Iterable[int],
    *,
    policy: dict[str, object] | None = None,
) -> AVReadinessContract:
    """Fit arm-C readiness from only coherent outer-train observations.

    Provider readiness fields intentionally never participate in eligibility;
    they may be retained as documentary metadata by callers only.
    """
    resolved = {**READINESS_POLICY, **(policy or {})}
    train_ids = sorted({int(value) for value in train_sample_ids})
    selected, _ = select_coherent_report_snapshot(rows)
    aliases = load_engine_aliases()
    selected["engine_canonical"] = selected["engine_name"].map(lambda item: canonicalize_engine_name(str(item), aliases))
    selected[["avobs", "avdet", "normalized_status"]] = selected.apply(classify_av_row, axis=1, result_type="expand")
    train = selected[selected["sample_id"].astype(int).isin(train_ids)].copy()
    observed = train[train["avobs"].eq(1)]
    all_engines = sorted(set(train["engine_canonical"]))
    meta = engine_metadata.copy()
    if "engine_name" not in meta:
        meta = pd.DataFrame(columns=["engine_canonical", "active", "trusted"])
    else:
        meta["engine_canonical"] = meta["engine_name"].map(lambda item: canonicalize_engine_name(str(item), aliases))
    meta = meta.drop_duplicates("engine_canonical", keep="last").set_index("engine_canonical", drop=False)
    total_train = max(len(train_ids), 1)
    rows_out: list[dict[str, object]] = []
    for engine in all_engines:
        engine_observed = observed[observed["engine_canonical"].eq(engine)]
        scans = int(len(engine_observed))
        positives = int(engine_observed["avdet"].sum())
        coverage = 100.0 * scans / total_train
        detection = 100.0 * positives / scans if scans else 0.0
        metadata = meta.loc[engine] if engine in meta.index else pd.Series(dtype="object")
        active = _flag(metadata.get("active", metadata.get("is_active", True)))
        trusted = _flag(metadata.get("trusted", metadata.get("is_trusted", False)))
        gates = {
            "minimum_scans_gate": scans >= int(resolved["minimum_scans"]),
            "coverage_gate": coverage >= float(resolved["minimum_coverage_percentage"]),
            "minimum_positive_detections_gate": positives >= int(resolved["minimum_positive_detections"]),
            "detection_percentage_gate": detection >= float(resolved["minimum_detection_percentage"]),
            "zero_detection_gate": (positives > 0) if bool(resolved["exclude_zero_detections"]) else True,
            "active_gate": active if bool(resolved["active_only"]) else True,
            "trusted_gate": trusted if bool(resolved["trusted_only"]) else True,
        }
        rows_out.append({
            "canonical_engine": engine,
            "train_interpretable_observations": scans,
            "train_positive_detections": positives,
            "train_coverage_percentage": coverage,
            "train_detection_percentage": detection,
            "active_snapshot": active,
            "trusted_snapshot": trusted,
            **gates,
            "readiness_eligible_flag": all(gates.values()),
        })
    ledger = pd.DataFrame(rows_out).sort_values("canonical_engine").reset_index(drop=True) if rows_out else pd.DataFrame()
    eligible = tuple(ledger.loc[ledger["readiness_eligible_flag"], "canonical_engine"].tolist()) if not ledger.empty else ()
    train_id_hash = hash_payload(train_ids)
    policy_hash = hash_payload({"policy": resolved, "train_id_hash": train_id_hash})
    return AVReadinessContract(eligible, ledger, policy_hash, train_id_hash, hash_payload(list(eligible)))
