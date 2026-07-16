"""Train-fitted governed Android permission feature contract.

This module is deliberately dataframe-only.  Database retrieval remains in the
existing permission stage; a frozen benchmark passes the retrieved rows here so
vocabulary fitting cannot inspect held-out rows.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.orchestration.permission_features import PERMISSION_GROUP_DEFINITIONS


CONTRACT_ID = "android_permissions_governed_known_v1"
NORMALIZATION_VERSION = "permission_norm_v2"
MIN_TRAIN_SUPPORT = 5
MAX_RAW_TOKEN_COLUMNS = 256
_TOKEN = re.compile(r"[^a-z0-9]+")


def normalize_permission_token(value: object, aliases: dict[str, str] | None = None) -> str:
    """Normalize a permission token using the frozen v2 rule."""
    if value is None or pd.isna(value):
        return ""
    token = unicodedata.normalize("NFKC", str(value)).strip().lower()
    token = (aliases or {}).get(token, token)
    return token


def _column_name(token: str) -> str:
    return "perm__" + (_TOKEN.sub("_", token).strip("_") or "unknown")


def group_definition_payload() -> list[dict[str, str]]:
    return [
        {"name": name, "pattern": pattern.pattern, "flags": str(pattern.flags)}
        for name, pattern in PERMISSION_GROUP_DEFINITIONS
    ]


def load_primary_allowlist(path: Path | None = None) -> dict[str, dict[str, str]]:
    """Load exact approved non-AOSP permission tokens."""
    if path is None:
        path = Path(__file__).resolve().parents[3] / "config" / "permission_primary_allowlist_v1.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, dict[str, str]] = {}
    for row in payload.get("tokens", []) or []:
        if not isinstance(row, dict):
            continue
        token = normalize_permission_token(row.get("token"))
        authority = str(row.get("authority", "")).strip().upper()
        if token and authority in {"GOOGLE", "OEM"}:
            out[token] = {"authority": authority, "rationale": str(row.get("rationale", ""))}
    return out


def _prepare_rows(rows: pd.DataFrame, *, allowlist: dict[str, dict[str, str]], aliases: dict[str, str]) -> pd.DataFrame:
    required = {"sample_id", "permission_string"}
    missing = required.difference(rows.columns)
    if missing:
        raise ValueError(f"Permission rows missing required columns: {sorted(missing)}")
    out = rows.copy()
    raw = out.get("permission_string_norm", out["permission_string"])
    out["permission_token"] = raw.map(lambda value: normalize_permission_token(value, aliases))
    permission_source = (
        out["permission_source"]
        if "permission_source" in out
        else pd.Series("UNKNOWN", index=out.index, dtype="object")
    )
    out["permission_source"] = permission_source.fillna("UNKNOWN").astype(str).str.upper()
    aosp = pd.to_numeric(out.get("is_aosp_dict_match", 0), errors="coerce").fillna(0).astype(int).gt(0)
    explicit = out["permission_token"].isin(allowlist)
    allowed_source = out["permission_source"].isin({"AOSP", "GOOGLE", "OEM"})
    out["permission_allowed"] = out["permission_token"].ne("") & (aosp | (explicit & allowed_source))
    out = out[out["permission_allowed"]].copy()
    # One canonical observation per sample/token; no extraction-run multiplicity.
    out = out.sort_values(["sample_id", "permission_token", "permission_source"]).drop_duplicates(
        ["sample_id", "permission_token"], keep="first"
    )
    return out


@dataclass(frozen=True)
class PermissionVocabularyContract:
    payload: dict[str, Any]

    @property
    def tokens(self) -> list[str]:
        return list(self.payload["ordered_tokens"])

    @property
    def contract_hash(self) -> str:
        return str(self.payload["contract_hash"])


def fit_permission_vocabulary(
    rows: pd.DataFrame,
    train_ids: list[int],
    *,
    aliases: dict[str, str] | None = None,
    allowlist: dict[str, dict[str, str]] | None = None,
    min_support: int = MIN_TRAIN_SUPPORT,
    max_tokens: int = MAX_RAW_TOKEN_COLUMNS,
) -> PermissionVocabularyContract:
    """Fit a known-permission vocabulary from training IDs only."""
    aliases = dict(aliases or {})
    allowlist = dict(allowlist or {})
    ids = sorted({int(value) for value in train_ids})
    prepared = _prepare_rows(rows, allowlist=allowlist, aliases=aliases)
    train = prepared[prepared["sample_id"].astype(int).isin(ids)].copy()
    support = train.groupby("permission_token")["sample_id"].nunique().to_dict()
    tokens = [token for token, count in support.items() if int(count) >= int(min_support)]
    tokens.sort(key=lambda token: (-int(support[token]), token))
    tokens = tokens[: int(max_tokens)]
    payload: dict[str, Any] = {
        "contract_id": CONTRACT_ID,
        "normalization_version": NORMALIZATION_VERSION,
        "min_train_support": int(min_support),
        "max_raw_token_columns": int(max_tokens),
        "train_sample_ids": ids,
        "train_sample_id_hash": hash_payload(ids),
        "ordered_tokens": tokens,
        "token_support": {token: int(support[token]) for token in tokens},
        "allowlist": allowlist,
        "allowlist_hash": hash_payload(allowlist),
        "alias_map": aliases,
        "alias_map_hash": hash_payload(aliases),
        "group_definitions": group_definition_payload(),
        "group_definition_hash": hash_payload(group_definition_payload()),
        "authority_policy": "aosp_dictionary_or_explicit_google_oem_allowlist",
        "app_defined_policy": "excluded",
        "known_missing_protection_level": "retained_as_unknown_protection",
    }
    payload["contract_hash"] = hash_payload(payload)
    return PermissionVocabularyContract(payload)


def transform_permission_features(
    rows: pd.DataFrame,
    sample_ids: list[int],
    contract: PermissionVocabularyContract,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply an ordered train-fitted vocabulary without adding test columns."""
    payload = contract.payload
    aliases = dict(payload.get("alias_map") or {})
    allowlist = dict(payload.get("allowlist") or {})
    ids = sorted({int(value) for value in sample_ids})
    prepared = _prepare_rows(rows, allowlist=allowlist, aliases=aliases)
    prepared = prepared[prepared["sample_id"].astype(int).isin(ids)].copy()
    token_set = set(contract.tokens)
    output = pd.DataFrame({"sample_id": ids})
    for token in contract.tokens:
        present = set(prepared.loc[prepared["permission_token"] == token, "sample_id"].astype(int))
        output[_column_name(token)] = output["sample_id"].isin(present).astype("int8")
    protection = prepared.get("protection_level", pd.Series("UNKNOWN", index=prepared.index)).fillna("UNKNOWN").astype(str).str.upper()
    prepared["_dangerous"] = protection.str.contains("DANGEROUS", regex=False).astype(int)
    prepared["_normal"] = protection.str.contains("NORMAL", regex=False).astype(int)
    source = prepared["permission_source"]
    count_frame = prepared.groupby("sample_id").agg(
        perm__known_dangerous_count=("_dangerous", "sum"),
        perm__known_normal_count=("_normal", "sum"),
        perm__known_total_count=("permission_token", "nunique"),
        perm__approved_oem_count=("permission_source", lambda value: int((value == "OEM").sum())),
    ).reset_index()
    output = output.merge(count_frame, on="sample_id", how="left")
    for name, pattern in PERMISSION_GROUP_DEFINITIONS:
        matched = prepared.loc[prepared["permission_token"].str.contains(pattern, na=False), "sample_id"].value_counts()
        output[f"perm_grp__{name}"] = output["sample_id"].map(matched).fillna(0).astype(int)
    feature_cols = [column for column in output.columns if column != "sample_id"]
    output[feature_cols] = output[feature_cols].fillna(0).astype(int)
    unseen = prepared[~prepared["permission_token"].isin(token_set)]["permission_token"].drop_duplicates().sort_values().tolist()
    audit = {
        "contract_hash": contract.contract_hash,
        "transform_sample_id_hash": hash_payload(ids),
        "unseen_token_count": len(unseen),
        "unseen_token_hash": hash_payload(unseen),
        "unseen_tokens": unseen,
        "allowed_observation_count": int(len(prepared)),
    }
    return output, audit
