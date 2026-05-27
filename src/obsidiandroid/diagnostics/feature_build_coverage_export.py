"""Export cohort vs feature-matrix row coverage for alignment-gap debugging."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from config import app_config
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common import output_hygiene as oh


def _perm_bag_positive_mask(
    permission_features_df: pd.DataFrame | None,
    cohort_ids: list[int],
) -> dict[int, bool]:
    """Return sample_id -> any permission-bag column positive (Permission Intel signal)."""
    out: dict[int, bool] = {int(s): False for s in cohort_ids}
    if (
        not isinstance(permission_features_df, pd.DataFrame)
        or permission_features_df.empty
        or "sample_id" not in permission_features_df.columns
    ):
        return out
    bag_cols = [
        c
        for c in permission_features_df.columns
        if str(c).startswith("perm__") or str(c).startswith("perm_grp__")
    ]
    if not bag_cols:
        return out
    sid = pd.to_numeric(permission_features_df["sample_id"], errors="coerce").round().astype("int64")
    cohort_set = set(cohort_ids)
    sub = permission_features_df.loc[sid.isin(cohort_set)].copy()
    sub["_sid"] = pd.to_numeric(sub["sample_id"], errors="coerce").round().astype("int64")
    mat = sub[bag_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    any_pos = (mat.sum(axis=1) > 0).to_numpy()
    ids = sub["_sid"].to_numpy()
    for i, sid_val in enumerate(ids):
        out[int(sid_val)] = bool(any_pos[i])
    return out


def export_feature_modality_coverage_audit(
    *,
    cohort_sample_ids: Iterable[Any],
    feature_df: pd.DataFrame,
    permission_features_df: pd.DataFrame | None,
    output_dir: str | Path,
    run_id: str,
    samples_df: pd.DataFrame | None = None,
    enabled: bool | None = None,
) -> tuple[Path | None, Path | None]:
    """Write per-sample modality flags and training-context drops (optional).

    Separates governed-cohort membership (fused matrix rows) from supervised-training cuts
    (missing label, low-support family) when ``samples_df`` is provided.

    Returns:
        Tuple of canonical run-scoped (csv_path, json_path), or (None, None).
    """
    if enabled is None:
        enabled = bool(getattr(app_config, "ENABLE_FEATURE_BUILD_COVERAGE_EXPORT", True))
    if not enabled:
        return None, None
    if not isinstance(feature_df, pd.DataFrame) or feature_df.empty:
        return None, None

    cohort_ids = sorted(_normalize_sample_ids(cohort_sample_ids))
    if not cohort_ids:
        return None, None

    vendor_ids = set()
    vm = feature_df.attrs.get("vendor_merge_sample_ids")
    if isinstance(vm, list):
        vendor_ids = _normalize_sample_ids(vm)

    perm_pi_positive = _perm_bag_positive_mask(permission_features_df, cohort_ids)

    idx_ids = _matrix_row_sample_ids(feature_df)
    work = feature_df.copy()
    if (
        "sample_id" in work.columns
        and isinstance(work.index, pd.RangeIndex)
        and work.index.equals(pd.RangeIndex(stop=len(work)))
    ):
        work["_audit_sid"] = pd.to_numeric(work["sample_id"], errors="coerce").astype("int64")
    else:
        work["_audit_sid"] = pd.to_numeric(work.index, errors="coerce").astype("int64")

    perm_cols = [
        c
        for c in work.columns
        if str(c).startswith(("perm__", "perm_grp__")) or str(c) == "meta__permissions"
    ]
    meta_cols = [
        c
        for c in work.columns
        if str(c).startswith("meta__") and str(c) != "meta__permissions"
    ]
    vendor_cols = list(feature_df.attrs.get("vendor_feature_column_names") or [])
    if not vendor_cols:
        vendor_cols = [
            c
            for c in work.columns
            if c != "_audit_sid"
            and not str(c).startswith(("perm__", "perm_grp__", "meta__"))
        ]

    enc_maps: dict[str, Any] = feature_df.attrs.get("encoder_mappings") or {}

    rows: list[dict[str, Any]] = []
    for sid in cohort_ids:
        sub = work.loc[work["_audit_sid"] == sid]
        pi_signal = perm_pi_positive.get(sid, False)
        in_vm = sid in vendor_ids
        if sub.empty:
            rows.append(
                {
                    "sample_id": sid,
                    "in_governed_cohort": True,
                    "in_vendor_feature_matrix": in_vm,
                    "in_permission_feature_matrix": pi_signal,
                    "in_final_fused_matrix": sid in idx_ids,
                    "has_vendor_features": False,
                    "has_permission_features": False,
                    "has_metadata_features": False,
                    "has_any_feature": pi_signal,
                    "vendor_parser_gate_passed": in_vm,
                    "permission_signal_positive": pi_signal,
                    "dropped_reason_supervised_training": "missing_fused_row",
                }
            )
            continue

        r = sub.iloc[0]
        vhit = False
        for c in vendor_cols:
            if c not in r.index or c == "_audit_sid":
                continue
            mv = float(pd.to_numeric(r[c], errors="coerce") or 0.0)
            if abs(mv - _column_unknown_code(c, enc_maps)) > 1e-9:
                vhit = True
                break
        phit = False
        if perm_cols:
            pm = pd.to_numeric(r[perm_cols], errors="coerce").fillna(0)
            phit = bool((pm > 0).any())
        mhit = False
        if meta_cols:
            mm = pd.to_numeric(r[meta_cols], errors="coerce").fillna(0)
            mhit = bool((mm > 0).any())

        has_any = bool(vhit or phit or mhit or pi_signal)
        drop_reason = ""
        if isinstance(samples_df, pd.DataFrame) and not samples_df.empty and "sample_id" in samples_df.columns:
            sid_series = pd.to_numeric(samples_df["sample_id"], errors="coerce")
            match = samples_df.loc[sid_series == float(sid)]
            if match.empty:
                drop_reason = "missing_from_samples_metadata"
            else:
                lbl_cols = [c for c in ("family_canonical", "family_id", "family_name") if c in match.columns]
                if lbl_cols:
                    lv = match.iloc[0].get(lbl_cols[0])
                    if lv is None or (isinstance(lv, float) and pd.isna(lv)) or str(lv).strip() == "":
                        drop_reason = "missing_supervised_label"

        rows.append(
            {
                "sample_id": sid,
                "in_governed_cohort": True,
                "in_vendor_feature_matrix": in_vm,
                "in_permission_feature_matrix": pi_signal,
                "in_final_fused_matrix": sid in idx_ids,
                "has_vendor_features": bool(vhit),
                "has_permission_features": bool(phit),
                "has_metadata_features": bool(mhit),
                "has_any_feature": bool(has_any),
                "vendor_parser_gate_passed": bool(in_vm),
                "permission_signal_positive": bool(pi_signal),
                "dropped_reason_supervised_training": drop_reason,
            }
        )

    audit_df = pd.DataFrame(rows)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rid = str(run_id)
    csv_named = out_dir / f"feature_modality_coverage_audit_{rid}.csv"
    csv_text = audit_df.to_csv(index=False)
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=out_dir,
        run_filename=csv_named.name,
        csv_text=csv_text,
        global_latest_name="feature_modality_coverage_audit.latest.csv",
    )

    summary = {
        "run_id": rid,
        "governed_cohort_n": len(cohort_ids),
        "fused_matrix_row_n": len(idx_ids),
        "vendor_merge_n": len(vendor_ids),
        "vendor_merge_n_note": (
            "vendor_merge_n is the inner vendor-authority slice count before cohort expansion; "
            "fused_matrix_row_n remains governed-cohort-authoritative (see feature_build_coverage JSON)."
        ),
        "permission_pi_signal_positive_n": int(sum(perm_pi_positive.values())),
        "matrix_authority": feature_df.attrs.get("feature_matrix_row_authority", ""),
    }
    json_named = out_dir / f"feature_modality_coverage_summary_{rid}.json"
    oh.mirror_json_text_run_then_global(
        diagnostics_dir=out_dir,
        run_filename=json_named.name,
        payload=summary,
        global_latest_name="feature_modality_coverage_summary.latest.json",
    )

    du.print_debug(
        "[COVERAGE] Modality audit (detail): "
        f"governed_n={summary['governed_cohort_n']} fused_n={summary['fused_matrix_row_n']} "
        f"vendor_merge_n={summary['vendor_merge_n']} pi_signal_n={summary['permission_pi_signal_positive_n']}"
    )
    return csv_named, json_named


def _column_unknown_code(col: str, encoder_mappings: dict[str, Any]) -> float:
    """Encoded value used for missing / unknown vendor fields after cohort expansion."""
    col_map = encoder_mappings.get(col) or {}
    for key in ("unknown", "Unknown"):
        if key in col_map:
            return float(col_map[key])
    return 0.0


def gap_permission_bag_strata(
    missing_sample_ids: list[int],
    permission_features_df: pd.DataFrame | None,
) -> dict[str, Any]:
    """Summarize Permission Intel bag signal on cohort ids missing from the vendor feature matrix.

    Helps distinguish "vendor gap" samples that still carry PI permission mass from those that do not.
    """
    out: dict[str, Any] = {}
    if not missing_sample_ids:
        out["gap_missing_sample_id_count"] = 0
        return out
    out["gap_missing_sample_id_count"] = int(len(missing_sample_ids))
    if not isinstance(permission_features_df, pd.DataFrame) or permission_features_df.empty:
        out["gap_permission_frame_unavailable"] = True
        return out
    if "sample_id" not in permission_features_df.columns:
        out["gap_permission_frame_missing_sample_id_column"] = True
        return out

    miss = _normalize_sample_ids(missing_sample_ids)
    bag_cols = [
        c
        for c in permission_features_df.columns
        if str(c).startswith("perm__") or str(c).startswith("perm_grp__")
    ]
    if not bag_cols:
        out["gap_permission_bag_columns"] = 0
        return out

    sid_series = pd.to_numeric(permission_features_df["sample_id"], errors="coerce").round().astype("int64")
    sub = permission_features_df.loc[sid_series.isin(sorted(miss))].copy()
    out["gap_missing_rows_in_permission_frame"] = int(len(sub))
    if sub.empty:
        out["gap_missing_with_permission_frame_row"] = 0
        out["gap_missing_with_any_perm_bag_positive"] = 0
        return out

    mat = sub[bag_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
    any_pos = (mat.sum(axis=1) > 0).astype(bool)
    out["gap_missing_with_any_perm_bag_positive"] = int(any_pos.sum())
    internet = next((c for c in bag_cols if "internet" in str(c).lower()), None)
    if internet and internet in mat.columns:
        out["gap_missing_perm_internet_nonzero"] = int((mat[internet] > 0).sum())
    return out


def _normalize_sample_ids(values: Iterable[Any]) -> set[int]:
    out: set[int] = set()
    for v in values:
        try:
            x = float(v)
            if pd.isna(x):
                continue
            i = int(x)
            if float(i) == x:
                out.add(i)
        except (TypeError, ValueError):
            continue
    return out


def _index_sample_ids(index: Any) -> set[int]:
    return _normalize_sample_ids(list(index))


def _matrix_row_sample_ids(feature_df: pd.DataFrame) -> set[int]:
    """Unique sample ids represented by the matrix (column wins over default positional index)."""
    if (
        isinstance(feature_df, pd.DataFrame)
        and not feature_df.empty
        and "sample_id" in feature_df.columns
    ):
        idx = feature_df.index
        if isinstance(idx, pd.RangeIndex) and idx.equals(pd.RangeIndex(stop=len(feature_df))):
            return _normalize_sample_ids(feature_df["sample_id"])
    return _index_sample_ids(feature_df.index)


def export_feature_build_coverage(
    *,
    cohort_sample_ids: Iterable[Any],
    feature_df: pd.DataFrame,
    output_dir: str | Path,
    run_id: str,
    enabled: bool | None = None,
    permission_features_df: pd.DataFrame | None = None,
) -> tuple[Path | None, Path | None]:
    """Write JSON summary + CSV of cohort ids absent from the built feature matrix index.

    Uses ``feature_df.attrs["vendor_merge_sample_ids"]`` when present (row authority before
    extras join); otherwise falls back to the final matrix index.

    When ``permission_features_df`` is provided, adds gap strata counts for missing ids
    (PI permission bag nonzero mass on vendor-gap rows).

    Returns:
        Tuple of canonical run-scoped (json_path, csv_path), or (None, None) when skipped.
    """
    if enabled is None:
        enabled = bool(getattr(app_config, "ENABLE_FEATURE_BUILD_COVERAGE_EXPORT", True))
    if not enabled:
        return None, None
    if not isinstance(feature_df, pd.DataFrame) or feature_df.empty:
        du.print_warning("[COVERAGE] Feature matrix empty — skipping coverage export.")
        return None, None

    cohort_set = _normalize_sample_ids(cohort_sample_ids)
    final_set = _matrix_row_sample_ids(feature_df)
    vendor_attrs = feature_df.attrs.get("vendor_merge_sample_ids")
    if isinstance(vendor_attrs, list) and vendor_attrs:
        vendor_set = _normalize_sample_ids(vendor_attrs)
    else:
        vendor_set = set(final_set)

    missing_from_feature = sorted(cohort_set - final_set)
    extra_in_feature = sorted(final_set - cohort_set)

    payload: dict[str, Any] = {
        "run_id": str(run_id),
        "cohort_unique_sample_count": len(cohort_set),
        "feature_matrix_unique_row_count": len(final_set),
        "vendor_merge_authority_unique_count": len(vendor_set),
        "cohort_rows_missing_from_feature_matrix": len(missing_from_feature),
        "feature_rows_not_in_cohort": len(extra_in_feature),
        "vendor_merge_equals_final_index": vendor_set == final_set,
        "row_authority_note": (
            "Fused matrix index is governed-cohort-authoritative when cohort_sample_ids are passed to "
            "build_feature_vector (vendor-only rows are unknown/zero-filled; permissions/metadata come "
            "from the enrichment frame). See feature_vector_builder._expand_to_cohort_authoritative and "
            "_merge_extra_features."
        ),
        "vendor_merge_n_semantics": (
            "vendor_merge_authority_unique_count (operator logs: vendor_merge_n) counts distinct sample_id "
            "values that appear in the inner vendor-feature merge *before* cohort-authoritative reindex. "
            "The fused feature matrix still emits one row per governed cohort sample_id; samples without a "
            "vendor merge row keep vendor columns at unknown/zero-fill while permission/metadata columns "
            "are joined from the enrichment frame."
        ),
    }
    auth = str(feature_df.attrs.get("feature_matrix_row_authority", "") or "")
    if auth:
        payload["feature_matrix_row_authority"] = auth
    payload.update(gap_permission_bag_strata(missing_from_feature, permission_features_df))

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rid = str(run_id)

    json_named = out_dir / f"feature_build_coverage_{rid}.json"
    oh.mirror_json_text_run_then_global(
        diagnostics_dir=out_dir,
        run_filename=json_named.name,
        payload=payload,
        global_latest_name="feature_build_coverage.latest.json",
    )

    csv_named = out_dir / f"cohort_missing_from_feature_matrix_{rid}.csv"
    if missing_from_feature:
        missing_df = pd.DataFrame({"sample_id": missing_from_feature})
        oh.mirror_csv_text_run_then_global(
            diagnostics_dir=out_dir,
            run_filename=csv_named.name,
            csv_text=missing_df.to_csv(index=False),
            global_latest_name="cohort_missing_from_feature_matrix.latest.csv",
        )
    else:
        csv_named.unlink(missing_ok=True)

    gpp = payload.get("gap_missing_with_any_perm_bag_positive")
    gap_extra = ""
    if (
        isinstance(gpp, int)
        and gpp > 0
        and len(missing_from_feature) > 0
        and payload.get("gap_missing_sample_id_count")
    ):
        gap_extra = (
            f" | gap_rows_with_perm_bag_signal={gpp}/"
            f"{payload.get('gap_missing_sample_id_count')}"
        )
    du.print_info(
        "[COVERAGE] Cohort vs fused matrix: "
        f"missing_from_matrix={len(missing_from_feature)} "
        f"(cohort={len(cohort_set)}, matrix_rows={len(final_set)}){gap_extra}"
    )
    return json_named, csv_named


def export_feature_matrix_lineage_gate(
    *,
    samples_df: pd.DataFrame,
    feature_df: pd.DataFrame,
    output_dir: str | Path,
    run_id: str,
    enabled: bool | None = None,
) -> Path | None:
    """Emit a JSON gate: fused matrix unique rows vs governed distinct ``sample_id`` values.

    Hard equality holds when every governed id appears exactly once in the fused matrix index and
    the fused matrix introduces no extra ids (document duplicate table rows or policy separately).

    Args:
        samples_df: Prepared cohort table (must include ``sample_id``).
        feature_df: Built fused feature matrix.
        output_dir: Diagnostics directory root.
        run_id: Run identifier for filenames.
        enabled: When False, skip export.

    Returns:
        Path to canonical run-scoped ``feature_matrix_lineage_gate_<run_id>.json``, or None when skipped.
    """
    if enabled is None:
        enabled = bool(getattr(app_config, "ENABLE_FEATURE_BUILD_COVERAGE_EXPORT", True)) and bool(
            getattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", True)
        )
    if not enabled:
        return None
    if (
        not isinstance(samples_df, pd.DataFrame)
        or samples_df.empty
        or "sample_id" not in samples_df.columns
    ):
        return None
    if not isinstance(feature_df, pd.DataFrame) or feature_df.empty:
        return None

    table_rows = int(len(samples_df))
    gov_set = _normalize_sample_ids(samples_df["sample_id"])
    distinct = len(gov_set)
    dup_surplus = max(0, table_rows - distinct)
    fused_set = _matrix_row_sample_ids(feature_df)
    gap = len(gov_set - fused_set)
    extra = len(fused_set - gov_set)
    auth = str(feature_df.attrs.get("feature_matrix_row_authority", "") or "")
    passes = gap == 0 and extra == 0
    expl: list[str] = []
    if dup_surplus:
        expl.append(f"duplicate_sample_id_table_rows={dup_surplus}")
    if gap:
        expl.append(f"governed_ids_missing_from_fused_matrix={gap}")
    if extra:
        expl.append(f"fused_rows_not_in_governed_set={extra}")

    payload = {
        "run_id": str(run_id),
        "governed_distinct_sample_ids": distinct,
        "prepared_cohort_table_rows": table_rows,
        "fused_feature_matrix_unique_rows": len(fused_set),
        "feature_matrix_row_authority": auth,
        "hard_equality_governed_fused_passes": passes,
        "gap_explanation": "; ".join(expl) if expl else "none",
    }

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    named = out_dir / f"feature_matrix_lineage_gate_{run_id}.json"
    oh.mirror_json_text_run_then_global(
        diagnostics_dir=out_dir,
        run_filename=named.name,
        payload=payload,
        global_latest_name="feature_matrix_lineage_gate.latest.json",
    )
    du.print_info(
        "[LINEAGE_GATE] "
        f"governed_distinct={distinct} fused_unique={len(fused_set)} "
        f"authority={auth or 'n/a'} pass={passes}"
    )
    return named


def export_sample_stage_lineage_audit(
    *,
    cohort_sample_ids: Iterable[Any],
    output_dir: str | Path,
    run_id: str,
    enabled: bool | None = None,
) -> Path | None:
    """Write per-sample survival flags across vendor merge, enrichment, fusion, and training cuts.

    Expects ``app_config`` runtime sets populated by the pipeline (vendor merge, fused matrix,
    permission frame, aligned supervised ids, post–family-support trainable ids).

    Args:
        cohort_sample_ids: Governed cohort ids (typically ``samples_df['sample_id']``).
        output_dir: Diagnostics directory root.
        run_id: Run identifier for filenames.
        enabled: When False, skip export.

    Returns:
        Path to canonical run-scoped ``sample_stage_lineage_<run_id>.csv``, or None when skipped or empty cohort.
    """
    if enabled is None:
        enabled = bool(getattr(app_config, "ENABLE_FEATURE_BUILD_COVERAGE_EXPORT", True)) and bool(
            getattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", True)
        )
    if not enabled:
        return None
    gov = sorted(_normalize_sample_ids(cohort_sample_ids))
    if not gov:
        return None

    def _optional_sid_set(attr: str) -> set[int] | None:
        raw = getattr(app_config, attr, None)
        if raw is None:
            return None
        return set(_normalize_sample_ids(raw))

    vm = _optional_sid_set("RUNTIME_VENDOR_MERGE_SAMPLE_IDS")
    perm = _optional_sid_set("RUNTIME_PERMISSION_FRAME_SAMPLE_IDS")
    fused = _optional_sid_set("RUNTIME_FUSED_MATRIX_SAMPLE_IDS")
    aligned = _optional_sid_set("RUNTIME_ALIGNED_SUPERVISED_SAMPLE_IDS")
    post_fam = _optional_sid_set("RUNTIME_POST_FAMILY_SUPPORT_TRAINABLE_SAMPLE_IDS")

    rows: list[dict[str, Any]] = []
    for sid in gov:
        in_vm = sid in vm if vm is not None else None
        in_perm = sid in perm if perm is not None else None
        in_fused = sid in fused if fused is not None else None
        in_al = sid in aligned if aligned is not None else None
        in_post = sid in post_fam if post_fam is not None else None
        dropped_fam: bool | None
        if aligned is None or post_fam is None:
            dropped_fam = None
        else:
            dropped_fam = bool(in_al and not in_post)
        rows.append(
            {
                "sample_id": sid,
                "in_governed_cohort": True,
                "in_vendor_merge": in_vm,
                "in_permission_enrichment_frame": in_perm,
                "in_fused_feature_matrix": in_fused,
                "in_aligned_supervised_pool": in_al,
                "dropped_by_family_support_filter": dropped_fam,
                "in_post_family_support_trainable_pool": in_post,
                "row_retained_after_low_information_column_prune": in_post,
                "row_retained_after_leakage_column_prune": in_post,
            }
        )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    named = out_dir / f"sample_stage_lineage_{run_id}.csv"
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=out_dir,
        run_filename=named.name,
        csv_text=df.to_csv(index=False),
        global_latest_name="sample_stage_lineage.latest.csv",
    )
    du.print_debug(f"[LINEAGE] sample_stage_lineage rows={len(df)} → {named.name}")
    return named


__all__ = [
    "export_feature_build_coverage",
    "export_feature_matrix_lineage_gate",
    "export_feature_modality_coverage_audit",
    "export_sample_stage_lineage_audit",
    "gap_permission_bag_strata",
    "_normalize_sample_ids",
]
