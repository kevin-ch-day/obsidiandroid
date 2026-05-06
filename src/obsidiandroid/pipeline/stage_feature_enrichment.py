"""Feature matrix enrichment stage helpers.

Canonical implementation (**Pass 70**): ``obsidiandroid.pipeline.stage_feature_enrichment``;
``analysis.pipeline.stage_feature_enrichment`` is an identity shim.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.cli.ui import display as du

from obsidiandroid.orchestration.permission_features import build_permission_feature_frame
from obsidiandroid.pipeline.sample_preparation import build_metadata_feature_frame


def _coerce_sample_id_to_int64_rows(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """Keep only rows whose ``sample_id`` coerces to a finite integer (drops engine-metadata overlays).

    Engine metadata overlays (``meta::`` rows) are no longer concatenated onto the enriched matrix;
    they are written to a diagnostics CSV. Any legacy bottom rows still must not participate in
    ``sample_id`` joins.
    """
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df
    if "sample_id" not in df.columns:
        return df
    out = df.copy()
    sid = pd.to_numeric(out["sample_id"], errors="coerce")
    valid = sid.notna()
    out = out.loc[valid].copy()
    if out.empty:
        return out
    out["sample_id"] = sid.loc[valid].round().astype("int64")
    return out


def _perm_internet_probe_col(df: pd.DataFrame) -> str | None:
    for name in (
        "perm__android_permission_internet",
        "perm__android.permission.internet",
    ):
        if name in df.columns:
            return name
    for col in df.columns:
        if str(col).startswith("perm__") and "internet" in str(col).lower():
            return str(col)
    return None


def _fuse_stats_dict(
    label: str,
    base: pd.DataFrame | None,
    perm: pd.DataFrame | None,
    *,
    internet_col: str | None,
) -> dict[str, Any]:
    """Structured counts for audit JSON and manifest (flat keys with label prefix)."""
    out: dict[str, Any] = {}
    if not isinstance(base, pd.DataFrame) or base.empty or "sample_id" not in base.columns:
        out[f"{label}_base_rows"] = 0
        out[f"{label}_base_distinct_sample_id"] = 0
        return out
    sid_b = pd.to_numeric(base["sample_id"], errors="coerce").dropna().astype("int64")
    out[f"{label}_base_rows"] = int(len(base))
    out[f"{label}_base_distinct_sample_id"] = int(sid_b.nunique())
    out[f"{label}_base_sample_id_min"] = int(sid_b.min())
    out[f"{label}_base_sample_id_max"] = int(sid_b.max())
    if internet_col and internet_col in base.columns:
        ser = pd.to_numeric(base[internet_col], errors="coerce").fillna(0)
        out[f"{label}_base_{internet_col}_nonzero_rows"] = int((ser > 0).sum())

    # Omit overlap / permission-frame keys when ``perm`` is not passed (e.g. post-merge snapshot),
    # so logs and JSON are not misread as "zero overlap" after a successful join.
    if not isinstance(perm, pd.DataFrame) or perm.empty or "sample_id" not in perm.columns:
        return out
    sid_p = pd.to_numeric(perm["sample_id"], errors="coerce").dropna().astype("int64")
    out[f"{label}_permission_rows"] = int(len(perm))
    out[f"{label}_permission_distinct_sample_id"] = int(sid_p.nunique())
    out[f"{label}_permission_sample_id_min"] = int(sid_p.min())
    out[f"{label}_permission_sample_id_max"] = int(sid_p.max())
    bset = set(sid_b.tolist())
    pset = set(sid_p.tolist())
    out[f"{label}_overlap_sample_id"] = int(len(bset & pset))
    if internet_col and internet_col in perm.columns:
        serp = pd.to_numeric(perm[internet_col], errors="coerce").fillna(0)
        out[f"{label}_permission_frame_{internet_col}_nonzero_rows"] = int((serp > 0).sum())
    return out


def _log_perm_fuse_snapshot(
    label: str,
    base: pd.DataFrame | None,
    perm: pd.DataFrame | None,
    *,
    internet_col: str | None,
) -> None:
    """Detail-only: full counter map is written to ``permission_fuse_audit`` JSON."""
    del label, base, perm, internet_col


def _permission_fuse_terminal_summary(
    merged_out: pd.DataFrame,
    permission_features_df: pd.DataFrame | None,
    audit: dict[str, Any],
    *,
    internet_col: str | None,
) -> None:
    du.print_subheader("Permission feature coverage")
    cohort_n = int(len(merged_out))
    perm_rows = int(len(permission_features_df)) if isinstance(permission_features_df, pd.DataFrame) else 0
    perm_cols = sum(
        1
        for c in merged_out.columns
        if str(c).startswith("perm__") or str(c).startswith("perm_grp__")
    )
    sig_val = audit.get("post_fuse_enrichment_rows_with_any_perm_bag_column_positive")
    if sig_val is None:
        sig_val = audit.get("post_fuse_enrichment_rows_with_any_perm_grp_positive")
    try:
        signal_n = int(sig_val) if sig_val is not None else cohort_n
    except (TypeError, ValueError):
        signal_n = cohort_n

    inet_n = audit.get(
        "post_fuse_enrichment_perm_bag_internet_nonzero_rows",
    )
    if inet_n is None and internet_col and internet_col in merged_out.columns:
        ser = pd.to_numeric(merged_out[internet_col], errors="coerce").fillna(0)
        inet_n = int((ser > 0).sum())
    try:
        inet_display = str(int(inet_n)) if inet_n is not None else "—"
    except (TypeError, ValueError):
        inet_display = str(inet_n)

    def pct(a: float | int, b: float | int) -> str:
        return f"{100.0 * float(a) / float(b):.1f}%" if b else "n/a"
    du.print_info(f"  cohort rows                         : {cohort_n}")
    du.print_info(f"  permission frame rows               : {perm_rows or cohort_n}")
    du.print_info(
        f"  rows with permission-bag signal     : {signal_n} ({pct(signal_n, cohort_n)})"
    )
    du.print_info(f"  permission / grouped feature cols   : {perm_cols}")
    du.print_info(
        "  INTERNET-positive rows (merged frame): "
        f"{inet_display}"
    )


def _write_permission_fuse_audit(flat: dict[str, Any]) -> None:
    setattr(app_config, "RUNTIME_PERMISSION_FUSE_AUDIT", dict(flat))
    diag = str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "").strip()
    if not diag:
        return
    out_dir = Path(diag)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(flat, indent=2, sort_keys=True) + "\n"
    named = out_dir / f"permission_fuse_audit_{getattr(app_config, 'RUNTIME_RUN_ID', 'unknown')}.json"
    named.write_text(payload, encoding="utf-8")
    latest = out_dir / "permission_fuse_audit.latest.json"
    latest.write_text(payload, encoding="utf-8")


def _duplicate_sample_id_report_rows(df: pd.DataFrame) -> pd.DataFrame:
    """One row per ``sample_id`` with duplicate rows and which columns disagree."""
    if "sample_id" not in df.columns:
        return pd.DataFrame()
    vc = df["sample_id"].value_counts()
    dup_sids = vc[vc > 1].index.tolist()
    rows: list[dict[str, Any]] = []
    for sid in dup_sids:
        sub = df[df["sample_id"] == sid]
        varying: list[str] = []
        for c in sub.columns:
            if c == "sample_id":
                continue
            if sub[c].nunique(dropna=False) > 1:
                varying.append(str(c))
        hint = "unknown"
        if any(str(x).startswith("meta__") for x in varying):
            hint = "metadata_or_mixed_enrichment"
        if any(str(x).startswith("perm__") or str(x).startswith("perm_grp__") for x in varying):
            hint = "permission_or_mixed_enrichment"
        if any(str(x) in {"malicious_ratio", "detection_density", "risk_score"} for x in varying):
            hint = "av_enrichment_or_mixed"
        rows.append(
            {
                "sample_id": sid,
                "duplicate_row_count": int(len(sub)),
                "columns_with_divergent_values": ";".join(varying[:120]),
                "inferred_source_hint": hint,
            }
        )
    return pd.DataFrame(rows)


def _strict_enrichment_duplicate_sample_id_gate(dup_count: int) -> None:
    """In evidence/paper mode, refuse silent dedupe unless explicitly overridden."""
    if dup_count <= 0:
        return
    if bool(getattr(app_config, "ALLOW_DUPLICATE_SAMPLE_ID_ENRICHMENT_FUSE", False)):
        return
    strict = bool(getattr(app_config, "RUNTIME_EVIDENCE_MODE", False)) or bool(
        getattr(app_config, "PAPER_MODE_ENABLED", False)
    )
    if not strict:
        return
    csv_path = str(getattr(app_config, "RUNTIME_DUPLICATE_SAMPLE_ID_PRE_FUSE_CSV", "") or "")
    raise ValueError(
        "[PIPELINE] Duplicate sample_id rows detected before enrichment fuse in evidence/paper mode. "
        f"See duplicate_sample_id_pre_fuse drill-down CSV ({csv_path or 'not written — set RUNTIME_DIAGNOSTICS_DIR'}). "
        "Set app_config.ALLOW_DUPLICATE_SAMPLE_ID_ENRICHMENT_FUSE=True only after manual review."
    )


def _maybe_export_duplicate_sample_id_pre_fuse(merged: pd.DataFrame, dup_count: int) -> None:
    if dup_count <= 0:
        return
    diag = str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "").strip()
    if not diag:
        setattr(app_config, "RUNTIME_DUPLICATE_SAMPLE_ID_PRE_FUSE_CSV", "")
        _strict_enrichment_duplicate_sample_id_gate(dup_count)
        return
    rep = _duplicate_sample_id_report_rows(merged)
    if rep.empty:
        setattr(app_config, "RUNTIME_DUPLICATE_SAMPLE_ID_PRE_FUSE_CSV", "")
        _strict_enrichment_duplicate_sample_id_gate(dup_count)
        return
    rid = str(getattr(app_config, "RUNTIME_RUN_ID", "unknown"))
    path = Path(diag) / f"duplicate_sample_id_pre_fuse_{rid}.csv"
    rep.to_csv(path, index=False)
    latest = Path(diag) / "duplicate_sample_id_pre_fuse.latest.csv"
    rep.to_csv(latest, index=False)
    setattr(app_config, "RUNTIME_DUPLICATE_SAMPLE_ID_PRE_FUSE_CSV", str(path))
    du.print_info(f"[FEATURES] Duplicate sample_id drill-down: {path}")
    _strict_enrichment_duplicate_sample_id_gate(dup_count)


def _enrichment_modality_nonzero_counts(df: pd.DataFrame, prefix: str) -> dict[str, Any]:
    """Contrast VT-catalog permission counts vs Permission Intel bag columns on the enrichment frame."""
    out: dict[str, Any] = {}
    if "meta__permissions" in df.columns:
        s = pd.to_numeric(df["meta__permissions"], errors="coerce").fillna(0)
        out[f"{prefix}_meta__permissions_nonzero_rows"] = int((s > 0).sum())
    if "perm__total_count" in df.columns:
        s = pd.to_numeric(df["perm__total_count"], errors="coerce").fillna(0)
        out[f"{prefix}_perm__total_count_nonzero_rows"] = int((s > 0).sum())
    bag = [c for c in df.columns if str(c).startswith("perm__")]
    if bag:
        mat = df[bag].apply(pd.to_numeric, errors="coerce").fillna(0)
        out[f"{prefix}_rows_with_any_perm_bag_column_positive"] = int((mat.sum(axis=1) > 0).sum())
        internet = next((c for c in bag if "internet" in str(c).lower()), None)
        if internet:
            out[f"{prefix}_perm_bag_internet_nonzero_rows"] = int((mat[internet] > 0).sum())
    grp = [c for c in df.columns if str(c).startswith("perm_grp__")]
    if grp:
        gmat = df[grp].apply(pd.to_numeric, errors="coerce").fillna(0)
        out[f"{prefix}_rows_with_any_perm_grp_positive"] = int((gmat.sum(axis=1) > 0).sum())
    return out


def _apply_permission_fuse(
    merged: pd.DataFrame,
    permission_features_df: pd.DataFrame,
    *,
    internet_col: str | None,
) -> pd.DataFrame:
    perm_coerced = _coerce_sample_id_to_int64_rows(permission_features_df.copy())
    if perm_coerced is None or perm_coerced.empty:
        audit: dict[str, Any] = {}
        audit.update(_fuse_stats_dict("pre_permission_merge", merged, None, internet_col=internet_col))
        _write_permission_fuse_audit(audit)
        du.print_subheader("Permission feature coverage")
        du.print_warning("  Permission enrichment frame empty — fuse skipped (see diagnostics if unexpected).")
        return merged

    pre = _fuse_stats_dict("pre_permission_merge", merged, perm_coerced, internet_col=internet_col)
    pre_extra = _enrichment_modality_nonzero_counts(merged, "pre_fuse_enrichment")
    pre.update(pre_extra)
    _log_perm_fuse_snapshot("pre_permission_merge", merged, perm_coerced, internet_col=internet_col)

    merged_out = merged.merge(perm_coerced, on="sample_id", how="left", sort=False)
    perm_like = [c for c in merged_out.columns if str(c).startswith(("perm__", "perm_grp__"))]
    for col in perm_like:
        merged_out[col] = pd.to_numeric(merged_out[col], errors="coerce").fillna(0)

    post = _fuse_stats_dict("post_permission_merge", merged_out, None, internet_col=internet_col)
    post_extras = _enrichment_modality_nonzero_counts(merged_out, "post_fuse_enrichment")
    post.update(post_extras)
    audit = {**pre, **post}
    _write_permission_fuse_audit(audit)
    _log_perm_fuse_snapshot("post_permission_merge", merged_out, None, internet_col=internet_col)
    _permission_fuse_terminal_summary(
        merged_out,
        permission_features_df,
        audit,
        internet_col=internet_col,
    )
    return merged_out


def build_permission_enrichment_frame(
    samples_df: pd.DataFrame,
    feature_flags: dict,
    *,
    log_frame_built: bool = True,
) -> pd.DataFrame | None:
    """Optionally build permission feature frame from permission observations.

    Args:
        samples_df: Cohort samples for Permission Intel features.
        feature_flags: Feature toggles (e.g. enable_permission_features).
        log_frame_built: When False, suppress the standard info log (e.g. secondary
            callers that rebuild the same frame for figures).
    """
    enabled = bool(
        feature_flags.get(
            "enable_permission_features",
            getattr(app_config, "ENABLE_PERMISSION_FEATURES", True),
        )
    )
    if not enabled:
        return None

    min_support = int(getattr(app_config, "PERMISSION_MIN_SUPPORT", 2))
    max_features_cfg = getattr(app_config, "PERMISSION_MAX_FEATURES", 0)
    max_features = int(max_features_cfg) if int(max_features_cfg) > 0 else None
    permission_df = build_permission_feature_frame(
        samples_df=samples_df,
        min_permission_support=min_support,
        max_permission_features=max_features,
    )
    if permission_df.empty:
        return None
    if log_frame_built:
        du.print_info(
            "[FEATURES] Added permission feature frame: "
            f"{permission_df.shape[1] - 1} feature column(s)."
        )
    return permission_df


def merge_sample_metadata_features(
    extra_features_df: pd.DataFrame | None,
    samples_df: pd.DataFrame,
    feature_flags: dict,
    permission_features_df: pd.DataFrame | None = None,
) -> pd.DataFrame | None:
    """Optionally merge sample metadata-derived features and permission columns by ``sample_id``."""
    setattr(app_config, "RUNTIME_PERMISSION_FUSE_AUDIT", {})
    setattr(app_config, "RUNTIME_DUPLICATE_SAMPLE_ID_PRE_FUSE_CSV", "")

    meta_enabled = bool(
        feature_flags.get(
            "enable_sample_metadata_features",
            getattr(app_config, "ENABLE_SAMPLE_METADATA_FEATURES", True),
        )
    )
    perm_has = isinstance(permission_features_df, pd.DataFrame) and not permission_features_df.empty
    internet_col = _perm_internet_probe_col(
        permission_features_df if isinstance(permission_features_df, pd.DataFrame) else pd.DataFrame()
    )

    if not meta_enabled:
        if not perm_has:
            return extra_features_df
        merged = _coerce_sample_id_to_int64_rows(
            extra_features_df if isinstance(extra_features_df, pd.DataFrame) else None
        )
        if merged is None or merged.empty:
            merged = _coerce_sample_id_to_int64_rows(
                pd.DataFrame({"sample_id": samples_df["sample_id"].drop_duplicates().reset_index(drop=True)})
            )
        if merged is None or merged.empty:
            _write_permission_fuse_audit({"error": "permission_only_fuse_empty_base"})
            return merged
        if "sample_id" in merged.columns:
            dupes = int(merged["sample_id"].duplicated().sum())
            if dupes:
                _maybe_export_duplicate_sample_id_pre_fuse(merged, dupes)
                merged = merged.drop_duplicates("sample_id", keep="first")
                du.print_warning(
                    "[FEATURES] Dropped duplicate sample_id row(s) before permission fuse: "
                    f"removed={dupes}"
                )
        merged = _apply_permission_fuse(merged, permission_features_df, internet_col=internet_col)
        du.print_info(
            "[FEATURES] Fused permission features (metadata features disabled): "
            f"{permission_features_df.shape[1] - 1} feature column(s)."
        )
        return merged

    metadata_features_df = build_metadata_feature_frame(samples_df)
    if metadata_features_df.empty:
        if not perm_has:
            return extra_features_df
        merged = _coerce_sample_id_to_int64_rows(
            extra_features_df if isinstance(extra_features_df, pd.DataFrame) else None
        )
        if merged is None or merged.empty:
            merged = _coerce_sample_id_to_int64_rows(
                pd.DataFrame({"sample_id": samples_df["sample_id"].drop_duplicates().reset_index(drop=True)})
            )
        if merged is None or merged.empty:
            return merged
        if "sample_id" in merged.columns:
            dupes = int(merged["sample_id"].duplicated().sum())
            if dupes:
                _maybe_export_duplicate_sample_id_pre_fuse(merged, dupes)
                merged = merged.drop_duplicates("sample_id", keep="first")
                du.print_warning(
                    "[FEATURES] Dropped duplicate sample_id row(s) before permission fuse: "
                    f"removed={dupes}"
                )
        merged = _apply_permission_fuse(merged, permission_features_df, internet_col=internet_col)
        du.print_info(
            "[FEATURES] Fused permission features (empty metadata frame): "
            f"{permission_features_df.shape[1] - 1} feature column(s)."
        )
        return merged

    metadata_features_df = _coerce_sample_id_to_int64_rows(metadata_features_df.copy())
    if metadata_features_df is None or metadata_features_df.empty:
        return extra_features_df

    merged = extra_features_df if isinstance(extra_features_df, pd.DataFrame) else None
    if isinstance(merged, pd.DataFrame) and not merged.empty:
        merged = _coerce_sample_id_to_int64_rows(merged)
        if merged is None or merged.empty:
            merged = None
    if isinstance(merged, pd.DataFrame) and not merged.empty:
        merged = merged.merge(metadata_features_df, on="sample_id", how="left", sort=False)
    else:
        merged = metadata_features_df.copy()

    merged = _coerce_sample_id_to_int64_rows(merged)
    if merged is None or merged.empty:
        return merged

    if "sample_id" in merged.columns:
        dupes = int(merged["sample_id"].duplicated().sum())
        if dupes:
            _maybe_export_duplicate_sample_id_pre_fuse(merged, dupes)
            merged = merged.drop_duplicates("sample_id", keep="first")
            du.print_warning(
                "[FEATURES] Dropped duplicate sample_id row(s) before permission fuse: "
                f"removed={dupes}"
            )

    du.print_info(
        "[FEATURES] Added metadata feature frame: "
        f"{metadata_features_df.shape[1] - 1} feature column(s)."
    )

    if perm_has:
        merged = _apply_permission_fuse(merged, permission_features_df, internet_col=internet_col)
        du.print_info(
            "[FEATURES] Fused permission features into enrichment frame: "
            f"{permission_features_df.shape[1] - 1} feature column(s)."
        )
    else:
        _write_permission_fuse_audit(_fuse_stats_dict("pre_permission_merge", merged, None, internet_col=None))
    return merged
