"""Exact A/B/C feature admission for the frozen Android family benchmark."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from obsidiandroid.common.hash_utils import hash_payload


SDK_COLUMNS = ("meta__target_min_version", "meta__target_sdk_version")
_PERMISSION_PREFIXES = ("perm__", "perm_grp__")
_BANNED_PREFIXES = ("meta__vt_", "parsed_", "threat_", "malware_type_", "family_", "package_", "av_consensus_", "av_risk_")
_BANNED_TOKENS = ("ratio", "reputation", "votes", "submissions", "tags", "sources", "collection")


@dataclass(frozen=True)
class ABCFeatureContracts:
    frames: dict[str, pd.DataFrame]
    column_hashes: dict[str, str]


def _validate_base(frame: pd.DataFrame) -> pd.DataFrame:
    expected = [column for column in frame.columns if column.startswith(_PERMISSION_PREFIXES)] + list(SDK_COLUMNS)
    if any(column not in frame.columns for column in SDK_COLUMNS):
        raise ValueError("Frozen A contract is missing an approved SDK column.")
    disallowed = set(frame.columns).difference({"sample_id", *expected})
    if disallowed:
        raise ValueError(f"Frozen A contract contains unregistered columns: {sorted(disallowed)}")
    return frame.loc[:, ["sample_id", *sorted(column for column in expected if column not in SDK_COLUMNS), *SDK_COLUMNS]].copy()


def _validate_av(frame: pd.DataFrame, base: pd.DataFrame, arm: str) -> pd.DataFrame:
    base_columns = list(base.columns)
    if any(column not in frame.columns for column in base_columns):
        raise ValueError(f"Frozen {arm} contract does not retain every A column.")
    non_av = [column for column in frame.columns if not column.startswith(("avdet__", "avobs__"))]
    if non_av != base_columns:
        raise ValueError(f"Frozen {arm} non-AV columns differ from A.")
    av = [column for column in frame.columns if column.startswith(("avdet__", "avobs__"))]
    engines_det = {column.removeprefix("avdet__") for column in av if column.startswith("avdet__")}
    engines_obs = {column.removeprefix("avobs__") for column in av if column.startswith("avobs__")}
    if not av or engines_det != engines_obs:
        raise ValueError(f"Frozen {arm} requires matched avdet/avobs engine pairs.")
    return frame.loc[:, [*base_columns, *sorted(av)]].copy()


def _validate_names(frame: pd.DataFrame) -> None:
    for column in frame.columns:
        lowered = str(column).lower()
        if lowered.startswith(_BANNED_PREFIXES) or any(token in lowered for token in _BANNED_TOKENS):
            raise ValueError(f"Prohibited frozen-benchmark feature: {column}")


def build_abc_feature_contracts(permission_features: pd.DataFrame, metadata: pd.DataFrame, av_b: pd.DataFrame, av_c: pd.DataFrame) -> ABCFeatureContracts:
    """Join approved sources and reject every unregistered predictive column."""
    metadata_allowed = metadata.loc[:, ["sample_id", *SDK_COLUMNS]].copy()
    base = permission_features.merge(metadata_allowed, on="sample_id", how="inner", validate="one_to_one")
    base = _validate_base(base)
    b = _validate_av(base.merge(av_b, on="sample_id", how="left", validate="one_to_one").fillna(0), base, "B")
    c = _validate_av(base.merge(av_c, on="sample_id", how="left", validate="one_to_one").fillna(0), base, "C")
    for frame in (base, b, c):
        _validate_names(frame)
    frames = {"A": base, "B": b, "C": c}
    return ABCFeatureContracts(frames, {arm: hash_payload(list(frame.columns)) for arm, frame in frames.items()})
