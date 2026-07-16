"""Frozen, train-fitted AV detection feature contracts.

This module intentionally distinguishes an engine observation from an engine
detection.  It also selects one coherent report snapshot per sample before
any engine feature is derived, preventing per-engine "latest row" joins.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import pandas as pd

from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.pipeline.engine_normalization import canonicalize_engine_name, load_engine_aliases


CONTRACT_ID = "av_detection_observation_frozen_v1"
OBSERVED_MIN_TRAIN_ROWS = 1
_NON_OBSERVATIONS = frozenset({"", "missing", "timeout", "confirmed_timeout", "failure", "unsupported", "type_unsupported"})
_OBSERVED_NON_DETECTIONS = frozenset({"undetected", "clean", "benign", "harmless", "safe", "approved", "verified", "none", "null", "n/a"})
_DETECTIONS = frozenset({"malicious", "suspicious", "detected", "positive"})
_IDENTITY_COLUMNS = ("report_id", "analysis_id", "retrieval_batch", "report_timestamp", "updated_at")


@dataclass(frozen=True)
class AVDetectionContract:
    engine_columns: tuple[str, ...]
    scope: str
    snapshot_policy: str
    policy_hash: str
    report_selection: pd.DataFrame


def _text(value: object) -> str:
    return str(value or "").strip().lower()


def classify_av_row(row: pd.Series) -> tuple[int, int, str]:
    """Return ``(avobs, avdet, normalized_status)`` under the frozen policy.

    A structured ``status`` must be one of the documented values.  A free-text
    ``result`` is a vendor detection label when nonempty and not a known
    non-observation/non-detection token.  This makes novel vendor labels
    explicit positive detections without treating timeout/failure as observed.
    """
    status_present = "status" in row.index and pd.notna(row.get("status"))
    value = _text(row.get("status") if status_present else row.get("result"))
    if value in _NON_OBSERVATIONS:
        return 0, 0, value or "missing"
    if value in _OBSERVED_NON_DETECTIONS:
        return 1, 0, value
    if value in _DETECTIONS:
        return 1, 1, value
    if status_present:
        raise ValueError(f"Unknown structured AV status: {value!r}")
    # ``result`` is a vendor label (for example, a family or generic verdict).
    return 1, 1, "vendor_detection_label"


def select_coherent_report_snapshot(rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Select a single report identity per sample, never per engine.

    The priority order is report ID, analysis ID, retrieval batch, and then a
    common report timestamp.  Rows without any report-level identity are only
    accepted when there is a single undifferentiated batch for that sample;
    otherwise the input is ambiguous and fails closed.
    """
    required = {"sample_id", "engine_name"}
    missing = required.difference(rows.columns)
    if missing:
        raise ValueError(f"AV rows missing columns: {sorted(missing)}")
    work = rows.copy()
    work["sample_id"] = pd.to_numeric(work["sample_id"], errors="raise").astype(int)
    identity = pd.Series("", index=work.index, dtype="object")
    identity_kind = pd.Series("", index=work.index, dtype="object")
    for column in _IDENTITY_COLUMNS:
        if column not in work:
            continue
        values = work[column].fillna("").astype(str).str.strip()
        choose = identity.eq("") & values.ne("")
        identity.loc[choose] = values.loc[choose]
        identity_kind.loc[choose] = column
    work["_snapshot_identity"] = identity
    work["_snapshot_kind"] = identity_kind
    if work["_snapshot_identity"].eq("").any():
        counts = work.groupby("sample_id")["_snapshot_identity"].nunique(dropna=False)
        ambiguous = counts[counts > 1]
        if not ambiguous.empty:
            raise ValueError("AV snapshot identity unavailable for a multi-snapshot sample.")
        work.loc[work["_snapshot_identity"].eq(""), "_snapshot_identity"] = "single_undifferentiated_batch"
        work.loc[work["_snapshot_kind"].eq(""), "_snapshot_kind"] = "deterministic_single_batch_fallback"
    # Use report time as a deterministic selection ordering; absent time falls
    # back to lexical identity, which is recorded in the report-selection ledger.
    order_time = pd.Series("", index=work.index, dtype="object")
    for column in ("report_timestamp", "updated_at", "retrieved_at"):
        if column in work:
            values = work[column].fillna("").astype(str)
            order_time = order_time.where(order_time.ne(""), values)
    work["_snapshot_order"] = order_time
    candidates = work[["sample_id", "_snapshot_identity", "_snapshot_kind", "_snapshot_order"]].drop_duplicates()
    selected = candidates.sort_values(["sample_id", "_snapshot_order", "_snapshot_identity"]).groupby("sample_id", as_index=False).tail(1)
    selected = selected.rename(columns={"_snapshot_identity": "selected_snapshot_id", "_snapshot_kind": "selection_basis"})
    selected = selected[["sample_id", "selected_snapshot_id", "selection_basis", "_snapshot_order"]]
    kept = work.merge(selected[["sample_id", "selected_snapshot_id"]], left_on=["sample_id", "_snapshot_identity"], right_on=["sample_id", "selected_snapshot_id"], how="inner")
    return kept.drop(columns=["_snapshot_identity", "_snapshot_kind", "_snapshot_order"]), selected.sort_values("sample_id").reset_index(drop=True)


def fit_av_detection_contract(
    rows: pd.DataFrame,
    train_sample_ids: Iterable[int],
    *,
    scope: str,
    readiness_eligible_engines: Iterable[str] | None = None,
) -> AVDetectionContract:
    """Fit the engine schema on outer-train observations only."""
    if scope not in {"all_observed", "readiness_eligible"}:
        raise ValueError(f"Unsupported AV contract scope: {scope}")
    selected, selection = select_coherent_report_snapshot(rows)
    aliases = load_engine_aliases()
    selected["engine_canonical"] = selected["engine_name"].map(lambda value: canonicalize_engine_name(str(value), aliases))
    if selected["engine_canonical"].eq("").any():
        raise ValueError("AV contract contains an empty canonical engine name.")
    status = selected.apply(classify_av_row, axis=1, result_type="expand")
    selected[["avobs", "avdet", "normalized_status"]] = status
    train_ids = {int(value) for value in train_sample_ids}
    train = selected[selected["sample_id"].isin(train_ids)]
    observed = set(train.loc[train["avobs"].eq(1), "engine_canonical"])
    if scope == "readiness_eligible":
        eligible = {canonicalize_engine_name(str(value), aliases) for value in (readiness_eligible_engines or ())}
        observed &= eligible
    engines = tuple(sorted(observed))
    policy = {
        "contract_id": CONTRACT_ID,
        "scope": scope,
        "observed_min_train_rows": OBSERVED_MIN_TRAIN_ROWS,
        "observation_semantics": "avobs=1 only for a report with a non-timeout/non-failure/non-unsupported verdict",
        "snapshot_policy": "report_id>analysis_id>retrieval_batch>report_timestamp>deterministic_single_batch_fallback",
        "engine_columns": list(engines),
        "active_only_temporal_meaning": "frozen_vendor_engine_metadata_snapshot_not_historical_observation_time",
    }
    return AVDetectionContract(engines, scope, policy["snapshot_policy"], hash_payload(policy), selection)


def transform_av_detection_features(rows: pd.DataFrame, contract: AVDetectionContract, sample_ids: Iterable[int]) -> pd.DataFrame:
    """Build fixed ``avdet``/``avobs`` columns with all absent cells zero."""
    selected, _ = select_coherent_report_snapshot(rows)
    aliases = load_engine_aliases()
    selected["engine_canonical"] = selected["engine_name"].map(lambda value: canonicalize_engine_name(str(value), aliases))
    selected[["avobs", "avdet", "_status"]] = selected.apply(classify_av_row, axis=1, result_type="expand")
    selected = selected[selected["engine_canonical"].isin(contract.engine_columns)]
    index = pd.Index([int(value) for value in sample_ids], name="sample_id")
    matrix = selected.pivot_table(index="sample_id", columns="engine_canonical", values=["avdet", "avobs"], aggfunc="max", fill_value=0)
    matrix.columns = [f"{prefix}__{engine}" for prefix, engine in matrix.columns]
    expected = [f"{prefix}__{engine}" for prefix in ("avdet", "avobs") for engine in contract.engine_columns]
    return matrix.reindex(index=index, columns=expected, fill_value=0).astype("int8").reset_index()
