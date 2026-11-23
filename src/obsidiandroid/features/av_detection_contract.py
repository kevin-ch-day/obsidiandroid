"""Frozen, train-fitted AV detection feature contracts.

This module intentionally distinguishes an engine observation from an engine
detection.  It also selects one coherent report snapshot per sample before
any engine feature is derived, preventing per-engine "latest row" joins.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import repeat
from typing import Iterable

import pandas as pd

from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.pipeline.engine_normalization import canonicalize_engine_name, load_engine_aliases


CONTRACT_ID = "av_detection_observation_frozen_v1"
OBSERVED_MIN_TRAIN_ROWS = 1
_NON_OBSERVATIONS = frozenset({"", "missing", "none", "null", "n/a", "timeout", "confirmed_timeout", "failure", "unsupported", "type_unsupported"})
_OBSERVED_NON_DETECTIONS = frozenset({"undetected", "harmless"})
_DETECTIONS = frozenset({"malicious", "suspicious", "detected", "positive"})
_IDENTITY_COLUMNS = ("report_id", "analysis_id", "retrieval_batch", "report_timestamp", "snapshot_row_id")
_ORDER_COLUMNS = ("report_timestamp", "updated_at", "record_created_at", "record_id")
_PREPARATION_COLUMNS = {"sample_id", "engine_name", "status", "result", *_IDENTITY_COLUMNS, *_ORDER_COLUMNS}


@dataclass(frozen=True)
class AVDetectionContract:
    engine_columns: tuple[str, ...]
    scope: str
    snapshot_policy: str
    policy_hash: str
    report_selection: pd.DataFrame

    @property
    def feature_columns(self) -> list[str]:
        """Return feature columns in frozen export order."""
        return [
            f"{prefix}__{engine}"
            for prefix in ("avdet", "avobs")
            for engine in self.engine_columns
        ]


@dataclass(frozen=True)
class PreparedAVReports:
    """Coherent verdicts and provenance reusable within a single run."""

    verdicts: pd.DataFrame
    report_selection: pd.DataFrame
    engine_aliases: dict[str, str]


def _text(value: object) -> str:
    return str(value or "").strip().lower()


def classify_av_result(result: object, *, status: object = None) -> tuple[int, int, str]:
    """Return ``(avobs, avdet, normalized_status)`` under the frozen policy.

    A structured ``status`` must be one of the documented values.  A free-text
    ``result`` is a vendor detection label when nonempty and not a known
    non-observation/non-detection token.  This makes novel vendor labels
    explicit positive detections without treating timeout/failure as observed.
    """
    status_present = status is not None and pd.notna(status)
    value = _text(status if status_present else result)
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


def classify_av_row(row: pd.Series) -> tuple[int, int, str]:
    """Apply the frozen verdict policy to a single pandas row."""
    return classify_av_result(row.get("result"), status=row.get("status"))


def classify_av_rows(rows: pd.DataFrame) -> pd.DataFrame:
    """Classify verdict columns without constructing a Series per input row."""
    results = rows.get("result", repeat(None, len(rows)))
    statuses = rows.get("status", repeat(None, len(rows)))
    return pd.DataFrame(
        (classify_av_result(result, status=status) for result, status in zip(results, statuses)),
        index=rows.index,
        columns=["avobs", "avdet", "normalized_status"],
    )


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
        # A live source without coherent report-level identity cannot prove
        # that all engine rows originate from one report.  Synthetic fixtures
        # must provide the same identity fields; no per-engine fallback exists.
        raise ValueError("LIVE_REPORT_IDENTITY_UNVERIFIED")
    # Use report time as a deterministic selection ordering; absent time falls
    # back to lexical identity, which is recorded in the report-selection ledger.
    order_time = pd.Series("", index=work.index, dtype="object")
    for column in _ORDER_COLUMNS:
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


def prepare_av_reports(
    rows: pd.DataFrame | PreparedAVReports, *, require_engine_names: bool = True
) -> PreparedAVReports:
    """Select coherent reports and normalize verdicts without fitting to a split."""
    if isinstance(rows, PreparedAVReports):
        if require_engine_names and rows.verdicts["engine_canonical"].eq("").any():
            raise ValueError("AV contract contains an empty canonical engine name.")
        return rows

    selected, selection = select_coherent_report_snapshot(
        rows.loc[:, rows.columns.isin(_PREPARATION_COLUMNS)]
    )
    aliases = load_engine_aliases()
    names = selected["engine_name"].map(str)
    canonical_by_name = {name: canonicalize_engine_name(name, aliases) for name in names.unique()}
    canonical_names = names.map(canonical_by_name)
    if require_engine_names and canonical_names.eq("").any():
        raise ValueError("AV contract contains an empty canonical engine name.")

    classified = classify_av_rows(selected)
    verdicts = pd.DataFrame({
        "sample_id": selected["sample_id"],
        "engine_canonical": canonical_names,
        "avobs": classified["avobs"].astype("int8"),
        "avdet": classified["avdet"].astype("int8"),
    })
    return PreparedAVReports(verdicts, selection, aliases)


def fit_av_detection_contract(
    rows: pd.DataFrame | PreparedAVReports,
    train_sample_ids: Iterable[int],
    *,
    scope: str,
    readiness_eligible_engines: Iterable[str] | None = None,
) -> AVDetectionContract:
    """Fit the engine schema on outer-train observations only."""
    if scope not in {"all_observed", "readiness_eligible"}:
        raise ValueError(f"Unsupported AV contract scope: {scope}")
    reports = prepare_av_reports(rows)
    verdicts = reports.verdicts
    train_ids = {int(value) for value in train_sample_ids}
    train_observed = verdicts["sample_id"].isin(train_ids) & verdicts["avobs"].eq(1)
    observed = set(verdicts.loc[train_observed, "engine_canonical"])
    if scope == "readiness_eligible":
        eligible = {
            canonicalize_engine_name(str(value), reports.engine_aliases)
            for value in (readiness_eligible_engines or ())
        }
        observed &= eligible
    engines = tuple(sorted(observed))
    policy = {
        "contract_id": CONTRACT_ID,
        "scope": scope,
        "observed_min_train_rows": OBSERVED_MIN_TRAIN_ROWS,
        "observation_semantics": "avobs=1 only for a report with a non-timeout/non-failure/non-unsupported verdict",
        "snapshot_policy": "report_id>analysis_id>retrieval_batch>report_timestamp>snapshot_row_id; order=report_timestamp>updated_at>record_created_at>record_id",
        "status_truth_table": {
            "missing_or_unavailable": "avobs=0,avdet=0",
            "timeout_failure_unsupported": "avobs=0,avdet=0",
            "harmless_undetected": "avobs=1,avdet=0",
            "suspicious_malicious_or_free_text": "avobs=1,avdet=1",
        },
        "engine_columns": list(engines),
        "active_only_temporal_meaning": "frozen_vendor_engine_metadata_snapshot_not_historical_observation_time",
    }
    return AVDetectionContract(
        engines, scope, policy["snapshot_policy"], hash_payload(policy), reports.report_selection.copy()
    )


def transform_av_detection_features(
    rows: pd.DataFrame | PreparedAVReports, contract: AVDetectionContract, sample_ids: Iterable[int]
) -> pd.DataFrame:
    """Build fixed ``avdet``/``avobs`` columns with all absent cells zero."""
    verdicts = prepare_av_reports(rows, require_engine_names=False).verdicts
    selected = verdicts[verdicts["engine_canonical"].isin(contract.engine_columns)]
    index = pd.Index([int(value) for value in sample_ids], name="sample_id")
    matrix = selected.pivot_table(index="sample_id", columns="engine_canonical", values=["avdet", "avobs"], aggfunc="max", fill_value=0)
    matrix.columns = [f"{prefix}__{engine}" for prefix, engine in matrix.columns]
    return matrix.reindex(index=index, columns=contract.feature_columns, fill_value=0).astype("int8").reset_index()
