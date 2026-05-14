"""Permission-token audit CSV for reviewer-facing lineage."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.common.cv_fold_config import safe_int_config_value
from obsidiandroid.orchestration.permission_features import PERMISSION_GROUP_DEFINITIONS
from obsidiandroid.orchestration.permission_features import _fetch_permission_rows  # pylint: disable=protected-access


def _classify_perm_row(source: str, protection: str) -> tuple[str, str]:
    prot = str(protection or "").strip().upper()
    src_u = str(source or "").strip().upper()
    if "DANGEROUS" in prot:
        tier = "dangerous"
    elif "NORMAL" in prot:
        tier = "normal"
    elif src_u == "CUSTOM":
        tier = "custom"
    elif src_u in {"OEM", "APP_DEFINED"}:
        tier = "oem_vendor"
    else:
        tier = "unknown"
    return tier, src_u or "UNKNOWN"


def _feature_group_bucket(permission_string: str) -> str:
    text = permission_string.lower()
    for name, pattern in PERMISSION_GROUP_DEFINITIONS:
        if pattern.search(text):
            return name.replace("_count", "")
    return "ungrouped"


def build_permission_feature_audit_rows(
    samples_df: pd.DataFrame,
    *,
    min_support_cfg: int = 2,
) -> list[dict[str, Any]]:
    """Produce one CSV row per permission token."""
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty or "sample_id" not in samples_df.columns:
        return []

    ids = sorted({int(float(sid)) for sid in samples_df["sample_id"].tolist() if pd.notna(sid)})
    permission_df = _fetch_permission_rows(ids)
    if permission_df.empty:
        return []

    prune_names: set[str] = set()
    prune_rows = getattr(app_config, "RUNTIME_LEAKAGE_PRUNING_AUDIT", None)
    if isinstance(prune_rows, list):
        for row in prune_rows:
            if isinstance(row, dict):
                cn = row.get("column_name")
                if cn:
                    prune_names.add(str(cn))

    merged = samples_df.copy()
    if "family_canonical" not in merged.columns:
        merged["family_canonical"] = "unknown"
    if "type_slug" not in merged.columns:
        merged["type_slug"] = "unknown"

    pdf = permission_df.copy()
    pdf["permission_string"] = pdf["permission_string"].fillna("").astype(str).str.strip().str.lower()
    pdf = pdf[pdf["permission_string"] != ""]
    global_counts = pdf.groupby("permission_string")["sample_id"].nunique()

    fam_support = pdf.merge(merged[["sample_id", "family_canonical"]], on="sample_id", how="left")
    family_max = (
        fam_support.groupby(["permission_string", "family_canonical"])["sample_id"]
        .nunique()
        .groupby(level=0)
        .max()
    )

    typ_support = pdf.merge(merged[["sample_id", "type_slug"]], on="sample_id", how="left")
    type_max = (
        typ_support.groupby(["permission_string", "type_slug"])["sample_id"]
        .nunique()
        .groupby(level=0)
        .max()
    )

    rows: list[dict[str, Any]] = []
    token_rows = pdf.drop_duplicates("permission_string")
    for _, trow in token_rows.iterrows():
        perm_token = str(trow.get("permission_string", "")).strip().lower()
        if not perm_token:
            continue
        gc = int(global_counts.get(perm_token, 0))
        tier, _pis = _classify_perm_row(str(trow.get("permission_source", "")), str(trow.get("protection_level", "")))

        sanitized = re.sub(r"[^a-z0-9]+", "_", perm_token).strip("_") or "unknown"
        col_name = f"perm__{sanitized}"
        pi_src_col = ""
        try:
            if "permission_source" in pdf.columns:
                pi_src_col = str(
                    pdf.loc[pdf["permission_string"] == perm_token, "permission_source"].iloc[0]
                )
        except Exception:
            pi_src_col = ""

        retained = gc >= int(min_support_cfg)

        rows.append(
            {
                "permission_string": perm_token,
                "feature_column": col_name,
                "global_support": gc,
                "max_family_support": int(family_max.loc[perm_token])
                if perm_token in family_max.index
                else 0,
                "max_type_support": int(type_max.loc[perm_token])
                if perm_token in type_max.index
                else 0,
                "retained_after_pruning": "yes" if retained else "no",
                "pruned_as_leakage": "yes" if col_name in prune_names else "no",
                "pi_bucket_source": pi_src_col,
                "dangerous_bucket": tier,
                "feature_group": _feature_group_bucket(perm_token),
            }
        )

    rows.sort(key=lambda r: (-int(r.get("global_support", 0)), str(r.get("permission_string"))))
    return rows


def write_permission_feature_audit_csv(
    *,
    diagnostics_dir: Path,
    samples_df: pd.DataFrame | None,
) -> Path | None:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    cfg = safe_int_config_value(getattr(app_config, "PERMISSION_MIN_SUPPORT", 2), default=2)
    target = diagnostics_dir / "permission_feature_audit.csv"
    if samples_df is None or samples_df.empty:
        target.write_text("status,notes\nstub,empty_samples\n", encoding="utf-8")
        return target
    audit_rows = build_permission_feature_audit_rows(samples_df, min_support_cfg=cfg)
    if not audit_rows:
        target.write_text("status,notes\nempty,no_permission_rows\n", encoding="utf-8")
        return target
    fieldnames = sorted({key for row in audit_rows for key in row.keys()})
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(audit_rows)
    return target
