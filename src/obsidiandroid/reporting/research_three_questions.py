"""End-of-run research skeleton: dataset validity, modality contribution, model/family failures.

Writes compact diagnostics (markdown/json/csv) and supplies terminal blocks for the three
core science questions. Heavy evidence stays in existing artifacts; these files summarize.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np
import pandas as pd

from config import app_config

from obsidiandroid.common.json_io import read_json_dict
from obsidiandroid.reporting import operator_dashboard


def _safe_pct(num: float, den: float) -> float:
    if den <= 0:
        return 0.0
    return round(100.0 * float(num) / float(den), 4)


def _vendor_merge_coverage_label(pct: float) -> str:
    """Human-readable vendor-merge coverage label for operator summaries."""
    try:
        value = float(pct)
    except (TypeError, ValueError):
        return "unknown"
    if value >= 99.5:
        return "full"
    if value >= 90.0:
        return "broad"
    if value >= 40.0:
        return "partial"
    if value > 0.0:
        return "sparse"
    return "absent"


def _permission_signal_quality_metric(diagnostics_dir: Path, metric: str) -> int | None:
    """Read one integer metric from permission-signal-quality CSV when present."""
    path = diagnostics_dir / "permission_signal_quality.csv"
    if not path.is_file():
        return None
    try:
        df = pd.read_csv(path)
    except Exception:
        return None
    if "metric" not in df.columns or "value" not in df.columns:
        return None
    match = df[df["metric"].astype(str) == str(metric)]
    if match.empty:
        return None
    try:
        return int(float(match.iloc[0]["value"]))
    except (TypeError, ValueError):
        return None


def _raw_permission_observation_count(samples_df: pd.DataFrame | None) -> int | None:
    """Count cohort samples with at least one raw permission observation from the DB."""
    if samples_df is None or samples_df.empty or "sample_id" not in samples_df.columns:
        return None
    try:
        from obsidiandroid.orchestration.permission_features import (  # pylint: disable=protected-access
            _fetch_permission_rows,
        )
    except Exception:
        return None

    sample_ids: list[int] = []
    for value in samples_df["sample_id"].tolist():
        if pd.isna(value):
            continue
        try:
            sample_ids.append(int(float(value)))
        except (TypeError, ValueError):
            continue
    if not sample_ids:
        return None

    try:
        perm_long = _fetch_permission_rows(sorted(set(sample_ids)))
    except Exception:
        return None
    if perm_long is None or perm_long.empty or "sample_id" not in perm_long.columns:
        return 0

    pl = perm_long.copy()
    if "permission_string" in pl.columns:
        pl["permission_string"] = pl["permission_string"].fillna("").astype(str).str.strip()
        pl = pl[pl["permission_string"] != ""]
    if pl.empty:
        return 0
    try:
        return int(pl["sample_id"].nunique(dropna=True))
    except Exception:
        return None


def _load_ablation_df(diagnostics_dir: Path, run_id: str) -> pd.DataFrame:
    for name in (
        f"ablation_summary_{run_id}.csv",
        "ablation_summary.latest.csv",
        f"ablation_summary_partial_{run_id}.csv",
    ):
        p = diagnostics_dir / name
        if p.is_file():
            try:
                return pd.read_csv(p)
            except Exception:
                return pd.DataFrame()
    return pd.DataFrame()


def _build_family_type_lookup(samples_df: pd.DataFrame | None) -> dict[str, str]:
    if samples_df is None or samples_df.empty or "type_slug" not in samples_df.columns:
        return {}
    out: dict[str, str] = {}
    ts = samples_df["type_slug"].fillna("unknown").astype(str).str.strip()
    if "family_canonical" in samples_df.columns:
        fc = samples_df["family_canonical"].fillna("").astype(str).str.strip()
        for fam in fc.unique():
            if not fam:
                continue
            mask = fc == fam
            if mask.any():
                out[fam] = str(ts.loc[mask].mode().iloc[0]) if len(ts.loc[mask].mode()) else "unknown"
    if "family_id" in samples_df.columns:
        fid = samples_df["family_id"].apply(lambda x: str(x).strip() if pd.notna(x) else "")
        for id_str in fid.unique():
            if not id_str:
                continue
            mask = fid == id_str
            if mask.any():
                out[id_str] = str(ts.loc[mask].mode().iloc[0]) if len(ts.loc[mask].mode()) else "unknown"
    return out


def _top_confusion_pairs_labeled(
    model_results: dict[str, Any],
    model_key: str,
    *,
    top_n: int = 5,
    type_lookup: dict[str, str],
) -> list[dict[str, Any]]:
    pairs = operator_dashboard.top_confusion_pairs_for_model(model_results, model_key, top_n=top_n)
    rows: list[dict[str, Any]] = []
    for true_l, pred_l, cnt in pairs:
        tt = type_lookup.get(str(true_l), "")
        tp = type_lookup.get(str(pred_l), "")
        shared = "yes" if tt and tp and tt == tp else ("no" if tt and tp else "")
        rows.append(
            {
                "true_label": str(true_l),
                "predicted_label": str(pred_l),
                "count": int(cnt),
                "true_type_slug": tt,
                "pred_type_slug": tp,
                "shared_malware_type": shared,
                "notes": "",
            }
        )
    return rows


def _classification_table_rows(model_results: dict[str, Any], model_key: str) -> list[dict[str, Any]]:
    res = model_results.get(model_key) if isinstance(model_results, dict) else None
    if not isinstance(res, dict):
        return []
    creport = res.get("metadata", {}).get("classification_report")
    if not isinstance(creport, dict):
        return []
    rows: list[dict[str, Any]] = []
    for label, stats in creport.items():
        if not isinstance(stats, dict):
            continue
        if label in {"accuracy", "macro avg", "weighted avg"}:
            continue
        try:
            rows.append(
                {
                    "family": str(label),
                    "precision": float(stats.get("precision", 0)),
                    "recall": float(stats.get("recall", 0)),
                    "f1_score": float(stats.get("f1-score", 0)),
                    "support": int(float(stats.get("support", 0))),
                }
            )
        except (TypeError, ValueError):
            continue
    return rows


def write_research_question_artifacts(
    *,
    diagnostics_dir: Path,
    run_id: str,
    profile_id: str,
    manifest_context: Mapping[str, Any],
    samples_df: pd.DataFrame | None,
    model_results: dict[str, Any] | None,
    top_model: str | None,
) -> dict[str, Any]:
    """Write dataset / modality / model summary files; return a bundle for terminal rendering."""
    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    mr = model_results if isinstance(model_results, dict) else {}
    mk = str(top_model or "random_forest").strip().lower().replace("-", "_")
    cf = read_json_dict(diagnostics_dir / "cohort_foundation.json")
    fts = cf.get("family_type_summary") if isinstance(cf.get("family_type_summary"), dict) else {}
    gate = cf.get("gate_stats") if isinstance(cf.get("gate_stats"), dict) else {}

    gov = int(
        cf.get("cohort_prepared_row_count")
        or manifest_context.get("cohort_prepared_row_count")
        or (len(samples_df) if samples_df is not None else 0)
        or 0
    )
    aligned = manifest_context.get("aligned_supervised_rows")
    trainable = manifest_context.get("post_low_support_training_rows")
    if trainable is None:
        trainable = getattr(app_config, "RUNTIME_POST_LOW_SUPPORT_TRAINING_ROWS", None)

    fam_count = int(fts.get("family_count") or 0)
    type_count = int(fts.get("type_count") or 0)
    top_fam = str(fts.get("top_family") or "")
    top_n = int(fts.get("top_family_count") or 0)
    top_share = float(fts.get("top_family_share_pct") or 0)
    t3_share = float(fts.get("top3_share_pct") or 0)
    t5_share = float(fts.get("top5_share_pct") or 0)
    t3_n = int(round(gov * t3_share / 100.0)) if gov else 0
    t5_n = int(round(gov * t5_share / 100.0)) if gov else 0

    low_retained = cf.get("low_support_families_retained_in_cohort")
    if not isinstance(low_retained, list):
        low_retained = []

    drop_detail = getattr(app_config, "RUNTIME_LOW_SUPPORT_FAMILY_DROP_DETAIL", None)
    if not isinstance(drop_detail, list):
        drop_detail = []

    missing_pkg = float(cf.get("missing_package_rate_pct") or 0)
    missing_vt = float(cf.get("missing_vt_timestamp_rate_pct") or 0)
    unmapped_sql = int(gate.get("excluded_unmapped_family") or 0)
    missing_sha_sql = int(gate.get("excluded_missing_sha256") or 0)

    msum = read_json_dict(diagnostics_dir / f"feature_modality_coverage_summary_{run_id}.json")
    if not msum:
        msum = read_json_dict(diagnostics_dir / "feature_modality_coverage_summary.latest.json")
    pi_n = msum.get("permission_pi_signal_positive_n")
    vmerge = msum.get("vendor_merge_n")
    perm_cols_fused = msum.get("permission_feature_columns_in_fused_matrix")
    if perm_cols_fused is None:
        modality = read_json_dict(diagnostics_dir / "modality_method_contract.json")
        if not modality:
            modality = read_json_dict(diagnostics_dir / "modality_method_contract.latest.json")
        perm_cols_fused = (
            (modality.get("fusion_modality") or {}).get("feature_count_permission")
            if modality
            else None
        )
        if perm_cols_fused is None and modality:
            perm_cols_fused = (modality.get("permission_modality") or {}).get("feature_count_raw")

    fc_contract = read_json_dict(diagnostics_dir / "feature_contract.json")
    if not fc_contract:
        fc_contract = read_json_dict(diagnostics_dir / "feature_contract.latest.json")
    eng_in = int(
        fc_contract.get("engine_included_count")
        or getattr(app_config, "RUNTIME_ENGINE_COUNT_INCLUDED_AFTER_GATING", 0)
        or 0
    )
    eng_ex = int(
        fc_contract.get("engine_excluded_count")
        or getattr(app_config, "RUNTIME_ENGINE_COUNT_EXCLUDED_AFTER_GATING", 0)
        or 0
    )
    eng_obs = eng_in + eng_ex

    raw_perm_n = _permission_signal_quality_metric(diagnostics_dir, "samples_with_any_permission_observation")
    if raw_perm_n is None:
        raw_perm_n = _raw_permission_observation_count(samples_df)
    denom_pi = float(gov) or 1.0
    raw_perm_pct = _safe_pct(float(raw_perm_n or 0), denom_pi) if gov else 0.0
    pi_pct = _safe_pct(float(pi_n or 0), denom_pi)
    vm_pct = _safe_pct(float(vmerge or 0), denom_pi)

    concentration_warn = top_share > 25.0 or t5_share > 60.0
    sparse_vendor = vm_pct < 10.0
    broad_perm = pi_pct >= 90.0

    if concentration_warn:
        operator_dashboard.record_operator_issue(
            tag="DATASET",
            title="High family concentration",
            lines=[
                f"Top family ≈ {top_share:.2f}%; top-5 ≈ {t5_share:.2f}%.",
                "Accuracy / weighted F1 may overstate tail-family behavior — emphasize Macro-F1.",
            ],
        )

    # --- Q1 files ---
    fam_dist = fts.get("family_distribution") if isinstance(fts.get("family_distribution"), dict) else {}
    pd.DataFrame([{"family": k, "sample_count": int(v)} for k, v in fam_dist.items()]).to_csv(
        diagnostics_dir / "family_distribution.csv", index=False
    )
    type_dist = fts.get("type_distribution") if isinstance(fts.get("type_distribution"), dict) else {}
    pd.DataFrame([{"type_slug": k, "sample_count": int(v)} for k, v in type_dist.items()]).to_csv(
        diagnostics_dir / "type_distribution.csv", index=False
    )
    pd.DataFrame(
        [
            {
                "metric": "top_family_share_pct",
                "value": top_share,
                "top_family": top_fam,
                "top_family_count": top_n,
            },
            {
                "metric": "top3_share_pct",
                "value": t3_share,
                "approximate_samples": t3_n,
            },
            {
                "metric": "top5_share_pct",
                "value": t5_share,
                "approximate_samples": t5_n,
            },
        ]
    ).to_csv(diagnostics_dir / "family_concentration.csv", index=False)

    low_rows: list[dict[str, Any]] = []
    for row in low_retained:
        if isinstance(row, dict):
            low_rows.append(
                {
                    "family": row.get("family"),
                    "rows_in_cohort": row.get("rows_in_cohort"),
                    "below_threshold": row.get("below_threshold"),
                    "source": "retained_in_cohort_below_sql_threshold",
                }
            )
    for row in drop_detail:
        if isinstance(row, dict):
            low_rows.append(
                {
                    "family": row.get("family"),
                    "rows_in_cohort": row.get("aligned_support"),
                    "below_threshold": getattr(app_config, "RUNTIME_MIN_FAMILY_SUPPORT", None),
                    "source": "dropped_before_training_min_family_support",
                }
            )
    pd.DataFrame(low_rows).to_csv(diagnostics_dir / "low_support_families.csv", index=False)

    quality_rows = [
        {"gate": "unmapped_labels_excluded_at_sql", "count_or_rate": unmapped_sql, "unit": "count"},
        {"gate": "missing_sha256_excluded_at_sql", "count_or_rate": missing_sha_sql, "unit": "count"},
        {"gate": "missing_package_name_prepared_cohort_rate_pct", "count_or_rate": missing_pkg, "unit": "pct"},
        {"gate": "missing_vt_timestamp_prepared_cohort_rate_pct", "count_or_rate": missing_vt, "unit": "pct"},
        {
            "gate": "permission_signal_positive_rows",
            "count_or_rate": int(pi_n or 0),
            "unit": f"count_of_{gov}",
        },
    ]
    pd.DataFrame(quality_rows).to_csv(diagnostics_dir / "dataset_quality_gates.csv", index=False)

    sup_ok = (
        unmapped_sql == 0
        and aligned is not None
        and int(aligned) > 0
        and trainable is not None
        and int(trainable) > 0
    )
    lineage_loss = ""
    if gov and trainable is not None and aligned is not None:
        if int(aligned) < int(gov):
            lineage_loss += f"governed→aligned: −{int(gov) - int(aligned)}. "
        if int(trainable) < int(aligned):
            lineage_loss += f"aligned→trainable: −{int(aligned) - int(trainable)} (family support filter)."

    q1_payload = {
        "run_id": run_id,
        "profile_id": profile_id,
        "governed_samples": gov,
        "aligned_supervised_samples": aligned,
        "trainable_after_support_filter": trainable,
        "families_represented": fam_count,
        "malware_types_represented": type_count,
        "concentration": {
            "top_family": top_fam,
            "top_family_count": top_n,
            "top_family_share_pct": top_share,
            "top3_share_pct": t3_share,
            "top5_share_pct": t5_share,
        },
        "quality_gates": {r["gate"]: r["count_or_rate"] for r in quality_rows},
        "concentration_warning": concentration_warn,
        "supervised_family_claims_suitable": bool(sup_ok),
        "sample_lineage_loss_summary": lineage_loss.strip(),
    }
    (diagnostics_dir / "dataset_foundation_summary.json").write_text(
        json.dumps(q1_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    q1_md_lines = [
        f"# Dataset foundation — `{run_id}`",
        "",
        f"- Governed cohort: **{gov}**",
        f"- Aligned supervised: **{aligned if aligned is not None else '—'}**",
        f"- Trainable after family-support filter: **{trainable if trainable is not None else '—'}**",
        f"- Families / types: **{fam_count}** / **{type_count}**",
        f"- Top family: **{top_fam}** — {top_n} samples ({top_share:.2f}%)",
        f"- Top-3 / top-5 share: **{t3_share:.2f}%** / **{t5_share:.2f}%**",
        "",
        "## Quality gates",
        "",
        f"- Unmapped labels excluded (SQL): {unmapped_sql}",
        f"- Missing SHA256 excluded (SQL): {missing_sha_sql}",
        f"- Missing package name (prepared cohort): {missing_pkg:.2f}%",
        f"- Missing VT-related timestamp (prepared cohort): {missing_vt:.2f}%",
        "",
        "## Interpretation",
        "",
        "- Prefer **Macro-F1** and per-family recall when concentration is high.",
        "- See `family_distribution.csv`, `low_support_families.csv`.",
        "",
    ]
    (diagnostics_dir / "dataset_foundation_summary.md").write_text(
        "\n".join(q1_md_lines) + "\n", encoding="utf-8"
    )

    # --- Q2 modality ---
    ab_df = _load_ablation_df(diagnostics_dir, run_id)
    primary_lt = "family_id"
    if not ab_df.empty and "label_target" in ab_df.columns:
        if primary_lt not in set(ab_df["label_target"].astype(str).unique()) and "family_canonical_default" in set(
            ab_df["label_target"].astype(str).unique()
        ):
            primary_lt = "family_canonical_default"

    ablation_display = pd.DataFrame()
    interpret_q2: list[str] = []
    perm_vs_fused_note = ""
    vendor_leak_hint = ""

    if not ab_df.empty and "macro_f1_score" in ab_df.columns:
        ab_df = ab_df.copy()
        ab_df["macro_f1_score"] = pd.to_numeric(ab_df["macro_f1_score"], errors="coerce")
        ab_df["weighted_f1_score"] = pd.to_numeric(
            ab_df.get("weighted_f1_score", ab_df.get("f1_score")), errors="coerce"
        )
        ab_df["accuracy"] = pd.to_numeric(ab_df["accuracy"], errors="coerce")
        ab_df["delta_vs_full_fused"] = pd.to_numeric(ab_df.get("delta_vs_full_fused"), errors="coerce")
        sub = ab_df[ab_df["label_target"].astype(str) == primary_lt].copy()
        if sub.empty:
            sub = ab_df.copy()
        sub = sub.dropna(subset=["macro_f1_score", "experiment"])
        if sub.empty:
            interpret_q2.append("Ablation CSV has no usable macro_f1_score rows for this run.")
        else:
            idx = sub.groupby(sub["experiment"].astype(str), sort=False)["macro_f1_score"].idxmax()
            best_per_exp = sub.loc[idx].copy()
            best_per_exp["feature_set_label"] = best_per_exp["experiment"].astype(str).map(
                operator_dashboard.format_feature_set_label
            )
            ablation_display = best_per_exp[
                [
                    "feature_set_label",
                    "model",
                    "label_target",
                    "macro_f1_score",
                    "weighted_f1_score",
                    "accuracy",
                    "delta_vs_full_fused",
                ]
            ].rename(
                columns={
                    "macro_f1_score": "macro_f1",
                    "weighted_f1_score": "weighted_f1",
                }
            )
            ablation_display.to_csv(diagnostics_dir / "feature_set_ablation_summary.csv", index=False)

            fused_row = best_per_exp[best_per_exp["experiment"].astype(str) == "full_fused"]
            perm_rows = best_per_exp[
                best_per_exp["experiment"].astype(str).isin(["permissions_raw", "permissions_grouped"])
            ]
            if not fused_row.empty and not perm_rows.empty:
                try:
                    fm = float(fused_row.iloc[0]["macro_f1_score"])
                    pm = float(perm_rows["macro_f1_score"].max())
                    delta = fm - pm
                    perm_vs_fused_note = (
                        f"Full fused Macro-F1 − best permission-only Macro-F1 ≈ {delta:+.4f} "
                        f"(fused={fm:.4f}, perm_best={pm:.4f})."
                    )
                    if delta < 0.02:
                        interpret_q2.append(
                            "Fused stack is within ~0.02 Macro-F1 of permission-only — do not oversell fused lift."
                        )
                except (TypeError, ValueError, IndexError):
                    perm_vs_fused_note = ""

            vfull = best_per_exp[best_per_exp["experiment"].astype(str) == "vendor_full"]
            vnof = best_per_exp[best_per_exp["experiment"].astype(str) == "vendor_no_parsed_family"]
            if not vfull.empty and not vnof.empty:
                try:
                    if float(vfull.iloc[0]["macro_f1_score"]) - float(vnof.iloc[0]["macro_f1_score"]) > 0.08:
                        vendor_leak_hint = (
                            "Large gap vendor_parsed_full vs vendor_parsed_no_family — review parsed-field leakage."
                        )
                except (TypeError, ValueError, IndexError):
                    pass

            ab_md = [
                "# Feature-set ablation (best Macro-F1 per feature set)",
                "",
                f"Label target filter: `{primary_lt}`",
                "",
            ]
            try:
                ab_md.append(ablation_display.to_markdown(index=False))
            except Exception:
                ab_md.append("(Markdown table unavailable — see CSV.)")
            ab_md.append("")
            (diagnostics_dir / "feature_set_ablation_summary.md").write_text("\n".join(ab_md) + "\n", encoding="utf-8")
    else:
        interpret_q2.append("Ablation summary missing or empty — modality comparison not interpretable this run.")
        pd.DataFrame(
            [{"status": "ablation_summary_unavailable_or_empty", "run_id": run_id}]
        ).to_csv(diagnostics_dir / "feature_set_ablation_summary.csv", index=False)

    if sparse_vendor:
        interpret_q2.append("Parsed vendor metadata merge coverage is sparse — treat as partial enrichment.")
    if broad_perm:
        interpret_q2.append("Permission signal covers most of the governed cohort — primary broad modality.")
    if (
        int(pi_n or 0) == 0
        and int(perm_cols_fused or 0) == 0
        and isinstance(raw_perm_n, int)
        and raw_perm_n > 0
    ):
        interpret_q2.append(
            "Raw permission observations exist in the DB, but permission features were disabled for the fused matrix in this run."
        )

    pd.DataFrame(
        [
            {
                "metric": "permission_signal_positive_n",
                "value": int(pi_n or 0),
                "denominator": gov,
                "pct": pi_pct,
            },
            {
                "metric": "permission_feature_columns_fused",
                "value": perm_cols_fused if perm_cols_fused is not None else "",
                "denominator": "",
                "pct": "",
            },
        ]
    ).to_csv(diagnostics_dir / "permission_coverage_summary.csv", index=False)

    pd.DataFrame(
        [
            {
                "metric": "vendor_merge_authority_n",
                "value": int(vmerge or 0),
                "denominator": gov,
                "pct": vm_pct,
            },
            {
                "metric": "av_engines_observed_feature_contract",
                "value": eng_obs,
                "denominator": "",
                "pct": "",
            },
            {
                "metric": "av_engines_included_feature_contract",
                "value": eng_in,
                "denominator": "",
                "pct": "",
            },
        ]
    ).to_csv(diagnostics_dir / "vendor_feature_coverage_summary.csv", index=False)

    leak_txt = diagnostics_dir / "leakage_assessment.latest.txt"
    leak_rows = [{"artifact": "leakage_assessment", "path": leak_txt.name, "notes": ""}]
    if leak_txt.is_file():
        leak_rows[0]["notes"] = leak_txt.read_text(encoding="utf-8", errors="replace")[:1200]
    pd.DataFrame(leak_rows).to_csv(diagnostics_dir / "vendor_leakage_safety_audit.csv", index=False)

    surv_path = operator_dashboard.resolve_feature_column_survival_path(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
    )
    if surv_path.is_file():
        try:
            sdf = pd.read_csv(surv_path)
            if "modality" in sdf.columns and "feature_name" in sdf.columns:
                vc = sdf.groupby(sdf["modality"].astype(str), dropna=False).size().reset_index(name="n_features")
                vc.to_csv(diagnostics_dir / "feature_group_survival.csv", index=False)
        except Exception:
            pd.DataFrame([{"note": "feature_column_survival_unreadable"}]).to_csv(
                diagnostics_dir / "feature_group_survival.csv", index=False
            )
    else:
        pd.DataFrame([{"note": "feature_column_survival_missing"}]).to_csv(
            diagnostics_dir / "feature_group_survival.csv", index=False
        )

    q2_payload = {
        "run_id": run_id,
        "governed_cohort_n": int(gov),
        "permission_signal_n": int(pi_n or 0),
        "permission_signal_pct": pi_pct,
        "permission_raw_observation_n": int(raw_perm_n or 0),
        "permission_raw_observation_pct": raw_perm_pct,
        "permission_feature_columns": perm_cols_fused,
        "vendor_merge_n": int(vmerge or 0),
        "vendor_merge_pct": vm_pct,
        "av_engines_observed": eng_obs,
        "av_engines_included": eng_in,
        "ablation_primary_label_target": primary_lt,
        "interpretation_notes": interpret_q2 + ([perm_vs_fused_note] if perm_vs_fused_note else []) + ([vendor_leak_hint] if vendor_leak_hint else []),
    }
    (diagnostics_dir / "modality_contribution_summary.json").write_text(
        json.dumps(q2_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    q2_md = [
        f"# Modality contribution — `{run_id}`",
        "",
        f"- Permission signal: **{int(pi_n or 0)} / {gov}** ({pi_pct:.2f}%)",
        f"- Permission feature columns (fused / contract): **{perm_cols_fused if perm_cols_fused is not None else '—'}**",
        f"- Parsed vendor merge authority: **{int(vmerge or 0)} / {gov}** ({vm_pct:.2f}%)",
        f"- AV engines (observed / included): **{eng_obs}** / **{eng_in}**",
        "",
        "See `feature_set_ablation_summary.csv` and `.md`.",
        "",
    ]
    (diagnostics_dir / "modality_contribution_summary.md").write_text("\n".join(q2_md) + "\n", encoding="utf-8")

    # --- Q3 model / family ---
    type_lookup = _build_family_type_lookup(samples_df)
    cls_rows = _classification_table_rows(mr, mk)
    cls_df = pd.DataFrame(cls_rows)
    if not cls_df.empty:
        cls_df.to_csv(diagnostics_dir / "family_precision_recall.csv", index=False)
        low_r = cls_df.sort_values("recall", ascending=True).head(10)
        low_p = cls_df.sort_values("precision", ascending=True).head(10)
        low_r.to_csv(diagnostics_dir / "lowest_recall_families.csv", index=False)
        low_p.to_csv(diagnostics_dir / "lowest_precision_families.csv", index=False)

        sup_med = float(cls_df["support"].median()) if not cls_df.empty else 0.0
        cls_df["metric_unstable_low_support"] = cls_df["support"] < max(3.0, sup_med * 0.1)
        cls_df.to_csv(diagnostics_dir / "family_support_vs_performance.csv", index=False)
    else:
        _cols = ["family", "precision", "recall", "f1_score", "support"]
        pd.DataFrame(columns=_cols).to_csv(diagnostics_dir / "family_precision_recall.csv", index=False)
        pd.DataFrame(columns=_cols).to_csv(diagnostics_dir / "lowest_recall_families.csv", index=False)
        pd.DataFrame(columns=_cols).to_csv(diagnostics_dir / "lowest_precision_families.csv", index=False)
        pd.DataFrame(columns=_cols + ["metric_unstable_low_support"]).to_csv(
            diagnostics_dir / "family_support_vs_performance.csv", index=False
        )

    conf_rows = _top_confusion_pairs_labeled(mr, mk, top_n=8, type_lookup=type_lookup)
    # top_confusion_pairs.csv is written by high_score_skeptic_audits (holdout CM + shared type).

    ft_perf_rows: list[dict[str, Any]] = []
    if not ab_df.empty and "label_target" in ab_df.columns and "macro_f1_score" in ab_df.columns:
        ab_ft = ab_df.copy()
        ab_ft["macro_f1_score"] = pd.to_numeric(ab_ft["macro_f1_score"], errors="coerce")
        if "weighted_f1_score" in ab_ft.columns:
            ab_ft["weighted_f1_score"] = pd.to_numeric(ab_ft["weighted_f1_score"], errors="coerce")
        elif "f1_score" in ab_ft.columns:
            ab_ft["weighted_f1_score"] = pd.to_numeric(ab_ft["f1_score"], errors="coerce")
        else:
            ab_ft["weighted_f1_score"] = np.nan
        ab_ft["accuracy"] = pd.to_numeric(ab_ft["accuracy"], errors="coerce")
        for lt in sorted(ab_ft["label_target"].dropna().unique()):
            sub = ab_ft[ab_ft["label_target"] == lt].dropna(subset=["macro_f1_score"])
            if sub.empty:
                continue
            best_i = sub["macro_f1_score"].idxmax()
            r = sub.loc[best_i]
            ft_perf_rows.append(
                {
                    "label_target": str(lt),
                    "best_model": str(r.get("model", "")),
                    "best_experiment": str(r.get("experiment", "")),
                    "macro_f1": float(r["macro_f1_score"]) if pd.notna(r.get("macro_f1_score")) else None,
                    "weighted_f1": float(r["weighted_f1_score"]) if pd.notna(r.get("weighted_f1_score")) else None,
                    "accuracy": float(r["accuracy"]) if pd.notna(r.get("accuracy")) else None,
                }
            )
        pd.DataFrame(ft_perf_rows).to_csv(diagnostics_dir / "family_vs_type_performance.csv", index=False)
    else:
        pd.DataFrame(
            [{"note": "family_vs_type_performance requires ablation_summary with label_target and macro_f1_score"}]
        ).to_csv(diagnostics_dir / "family_vs_type_performance.csv", index=False)

    pd.DataFrame(
        [
            {
                "note": "Per-class type precision/recall: train a type_slug headline model or inspect ablation exports."
            }
        ]
    ).to_csv(diagnostics_dir / "type_precision_recall.csv", index=False)

    ev = {}
    if mk in mr and isinstance(mr[mk], dict):
        ev = mr[mk].get("evaluation", {}) if isinstance(mr[mk].get("evaluation"), dict) else {}
    macro_f1 = float(ev.get("macro_f1_score") or 0.0)
    wf1 = float(ev.get("f1_score") or 0.0)
    acc = float(ev.get("accuracy") or 0.0)
    gap_w_m = wf1 - macro_f1

    fam_macro = None
    type_macro = None
    fwt_macro = None
    for row in ft_perf_rows:
        lt = str(row["label_target"])
        if lt in ("family_id", "family_canonical_default"):
            fam_macro = row.get("macro_f1")
        elif lt == "type_slug":
            type_macro = row.get("macro_f1")
        elif lt == "family_within_type":
            fwt_macro = row.get("macro_f1")

    type_easier = ""
    if fam_macro is not None and type_macro is not None:
        if type_macro > fam_macro + 0.05:
            type_easier = "Type-level Macro-F1 is markedly higher than family_id — family attribution remains harder."
        elif type_macro < fam_macro - 0.02:
            type_easier = "Family-level Macro-F1 meets or exceeds type-level on this run (unusual; verify label targets)."

    q3_payload = {
        "run_id": run_id,
        "headline_model": mk,
        "macro_f1": macro_f1,
        "weighted_f1": wf1,
        "accuracy": acc,
        "weighted_minus_macro_f1": gap_w_m,
        "weighted_macro_gap_warning": gap_w_m > 0.05,
        "type_vs_family_note": type_easier,
        "family_within_type_macro_f1": fwt_macro,
        "family_vs_type_rows": ft_perf_rows,
    }
    (diagnostics_dir / "model_and_family_failure_summary.json").write_text(
        json.dumps(q3_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    q3_md = [
        f"# Model and family failure — `{run_id}`",
        "",
        f"- Headline model: **{mk}**",
        f"- Macro-F1 / weighted F1 / accuracy: **{macro_f1:.4f}** / **{wf1:.4f}** / **{acc:.4f}**",
        f"- Weighted − Macro: **{gap_w_m:+.4f}**",
        "",
    ]
    if type_easier:
        q3_md.extend(["## Target comparison (ablation grid)", "", type_easier, ""])
    q3_md.append("See `family_precision_recall.csv`, `top_confusion_pairs.csv`, `family_vs_type_performance.csv`.")
    q3_md.extend(
        [
            "",
            "## High-score skepticism (Q3 extension)",
            "",
            "- Why might Macro-F1 look **very high**? See `high_score_audit.md` and `headline_score_scope.md`.",
            "- What was **removed** before training? See `headline_score_scope.md` and `low_support_families.csv`.",
            "- Are **wrong predictions** concentrated? See `false_attribution_audit.md` and `high_confidence_wrong_predictions.csv`.",
            "- Is the **random split** too easy? See `split_contamination_audit.md` and package overlap CSVs.",
            "- Is **SMOTE** inflating training rows? See `smote_effect_check.md` / `RUNTIME_SMOTE_AUDIT_BY_MODEL`.",
            "- Are **label-like features** driving RF? See `top_feature_modality_audit.md` and `suspicious_label_like_features.csv`.",
            "",
        ]
    )
    (diagnostics_dir / "model_and_family_failure_summary.md").write_text("\n".join(q3_md) + "\n", encoding="utf-8")

    from obsidiandroid.reporting import high_score_skeptic_audits as _hssa

    _hssa.write_all_skeptic_audits(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id=profile_id,
        q1_payload=q1_payload,
        manifest_context=dict(manifest_context),
        model_results=mr,
        top_model_key=mk,
        samples_df=samples_df,
        headline_macro_f1=macro_f1,
        headline_acc=acc,
        headline_weighted_f1=wf1,
        drop_detail=drop_detail,
        primary_label_target=str(primary_lt),
        type_lookup=type_lookup,
    )

    written_paths: list[str] = []
    for name in (
        "dataset_foundation_summary.json",
        "dataset_foundation_summary.md",
        "family_distribution.csv",
        "type_distribution.csv",
        "family_concentration.csv",
        "low_support_families.csv",
        "dataset_quality_gates.csv",
        "modality_contribution_summary.json",
        "modality_contribution_summary.md",
        "feature_set_ablation_summary.csv",
        "feature_set_ablation_summary.md",
        "permission_coverage_summary.csv",
        "vendor_feature_coverage_summary.csv",
        "vendor_leakage_safety_audit.csv",
        "feature_group_survival.csv",
        "model_and_family_failure_summary.json",
        "model_and_family_failure_summary.md",
        "family_precision_recall.csv",
        "lowest_recall_families.csv",
        "lowest_precision_families.csv",
        "top_confusion_pairs.csv",
        "family_vs_type_performance.csv",
        "type_precision_recall.csv",
        "family_support_vs_performance.csv",
        "headline_score_scope.json",
        "headline_score_scope.md",
        "high_score_audit.json",
        "high_score_audit.md",
        "false_attribution_audit.json",
        "false_attribution_audit.md",
        "false_positive_by_predicted_family.csv",
        "false_negative_by_true_family.csv",
        "high_confidence_wrong_predictions.csv",
        "split_contamination_audit.json",
        "split_contamination_audit.md",
        "train_test_package_overlap.csv",
        "train_test_family_package_overlap.csv",
        "smote_effect_check.csv",
        "smote_effect_check.md",
        "smote_effect_check.json",
        "leakage_safe_score_comparison.csv",
        "leakage_safe_score_comparison.md",
        "leakage_safe_score_comparison.json",
        "top_feature_modality_audit.csv",
        "top_feature_modality_audit.md",
        "top_feature_modality_audit.json",
        "suspicious_label_like_features.csv",
        "recommended_validation_plan.md",
    ):
        p = diagnostics_dir / name
        if p.is_file():
            written_paths.append(str(p))
    if written_paths:
        operator_dashboard.bump_artifact_counter("research_summaries", len(written_paths))

    return {
        "q1": q1_payload,
        "q2": q2_payload,
        "q3": q3_payload,
        "ablation_display": ablation_display,
        "classification_df": cls_df,
        "confusion_rows": conf_rows,
        "primary_label_target": primary_lt,
        "model_key": mk,
        "interpret_q2": interpret_q2,
        "perm_vs_fused_note": perm_vs_fused_note,
        "vendor_leak_hint": vendor_leak_hint,
        "type_easier": type_easier,
        "gap_w_m": gap_w_m,
        "macro_f1": macro_f1,
        "wf1": wf1,
        "acc": acc,
        "concentration_warn": concentration_warn,
        "_written_paths": written_paths,
    }


def print_research_questions_terminal(
    bundle: dict[str, Any],
    *,
    pr: Callable[[str], None],
    du: Any,
) -> None:
    """Print DATASET FOUNDATION, MODALITY CONTRIBUTION, MODEL FAILURE, and RESEARCH RUN SUMMARY."""
    from obsidiandroid.reporting import high_score_skeptic_audits as _hssa

    sk = bundle.get("skeptic_audits")
    if isinstance(sk, dict) and sk:
        _hssa.print_scope_of_headline_score_terminal(sk, pr=pr, du=du)

    q1 = bundle.get("q1") or {}
    du.print_section("DATASET FOUNDATION")
    pr("Cohort:")
    pr(f"  Governed samples: {q1.get('governed_samples', '—')}")
    pr(f"  Aligned supervised: {q1.get('aligned_supervised_samples', '—')}")
    pr(f"  Trainable after support filter: {q1.get('trainable_after_support_filter', '—')}")
    pr(f"  Families: {q1.get('families_represented', '—')}")
    pr(f"  Malware types: {q1.get('malware_types_represented', '—')}")
    pr("")
    conc = q1.get("concentration") or {}
    pr("Concentration:")
    pr(
        f"  Top family: {conc.get('top_family', '—')} — {conc.get('top_family_count', '—')} samples "
        f"({float(conc.get('top_family_share_pct') or 0):.2f}%)"
    )
    pr(f"  Top-3 share: {float(conc.get('top3_share_pct') or 0):.2f}%")
    pr(f"  Top-5 share: {float(conc.get('top5_share_pct') or 0):.2f}%")
    if bundle.get("concentration_warn"):
        pr("  ⚠ High concentration — prefer Macro-F1 / per-family metrics over accuracy.")
    pr("")
    pr("Quality gates (see dataset_quality_gates.csv):")
    qg = q1.get("quality_gates") or {}
    pr(f"  Unmapped labels excluded (SQL): {qg.get('unmapped_labels_excluded_at_sql', '—')}")
    pr(f"  Missing SHA256 excluded (SQL): {qg.get('missing_sha256_excluded_at_sql', '—')}")
    pr(f"  Missing package (prepared cohort): {qg.get('missing_package_name_prepared_cohort_rate_pct', '—')}%")
    pr(f"  Missing VT timestamp (prepared cohort): {qg.get('missing_vt_timestamp_prepared_cohort_rate_pct', '—')}%")
    pr("")
    if q1.get("sample_lineage_loss_summary"):
        pr(f"Sample loss: {q1['sample_lineage_loss_summary']}")
        pr("")
    if not q1.get("supervised_family_claims_suitable"):
        pr("⚠ Supervised family claims may be weak — check labels and alignment.")
        pr("")
    pr("Interpretation:")
    pr("  Cohort structure drives interpretability; Macro-F1 and recall tails are primary evidence.")
    pr("  Files: dataset_foundation_summary.md, family_distribution.csv, low_support_families.csv")
    pr("")

    q2 = bundle.get("q2") or {}
    du.print_section("FEATURE MODALITY CONTRIBUTION")
    gov = int(q1.get("governed_samples") or 0) or 1
    pr("Coverage:")
    pr(
        f"  Permission signal: {q2.get('permission_signal_n', '—')} / {gov} "
        f"({float(q2.get('permission_signal_pct') or 0):.2f}%)"
    )
    pr(f"  Permission feature columns: {q2.get('permission_feature_columns', '—')}")
    pr(
        f"  Parsed vendor metadata (merge authority): {q2.get('vendor_merge_n', '—')} / {gov} "
        f"({float(q2.get('vendor_merge_pct') or 0):.2f}%)"
    )
    pr(
        f"  AV engines observed / included: {q2.get('av_engines_observed', '—')} / "
        f"{q2.get('av_engines_included', '—')}"
    )
    pr("")
    adf = bundle.get("ablation_display")
    if isinstance(adf, pd.DataFrame) and not adf.empty:
        pr(f"Ablation (best Macro-F1 per feature set, label_target≈{bundle.get('primary_label_target')}):")
        du.print_table(adf, show_index=False)
    else:
        pr("Ablation: (no compact table — see feature_set_ablation_summary.csv or enable ablations)")
    pr("")
    for line in bundle.get("interpret_q2") or []:
        pr(f"  • {line}")
    if bundle.get("perm_vs_fused_note"):
        pr(f"  • {bundle['perm_vs_fused_note']}")
    if bundle.get("vendor_leak_hint"):
        pr(f"  ⚠ {bundle['vendor_leak_hint']}")
    pr("")
    pr("Files: modality_contribution_summary.md, feature_set_ablation_summary.csv")
    pr("")

    mk = str(bundle.get("model_key") or "random_forest")
    du.print_section("MODEL AND FAMILY FAILURE SUMMARY")
    pr("Best model (headline):")
    pr(f"  Model: {mk}")
    pr(f"  Macro-F1: {float(bundle.get('macro_f1') or 0):.4f}")
    pr(f"  Weighted F1: {float(bundle.get('wf1') or 0):.4f}")
    pr(f"  Accuracy: {float(bundle.get('acc') or 0):.4f}")
    pr(f"  Gap weighted F1 − Macro-F1: {float(bundle.get('gap_w_m') or 0):+.4f}")
    if float(bundle.get("gap_w_m") or 0) > 0.05:
        pr("  ⚠ Gap > 0.05 — dominant families likely easier than tail families.")
    pr("")
    cdf = bundle.get("classification_df")
    if isinstance(cdf, pd.DataFrame) and not cdf.empty:
        pr("Lowest recall families (holdout):")
        tail = cdf.sort_values("recall", ascending=True).head(5)
        for _, r in tail.iterrows():
            unst = " (unstable support)" if int(r.get("support", 0)) < 5 else ""
            pr(
                f"  • {r.get('family')}: support={int(r['support'])} recall={float(r['recall']):.3f} "
                f"precision={float(r['precision']):.3f}{unst}"
            )
        pr("")
    for row in (bundle.get("confusion_rows") or [])[:5]:
        pr(
            f"  Confusion: true={row.get('true_label')} → pred={row.get('predicted_label')} "
            f"n={row.get('count')} same_type={row.get('shared_malware_type') or '?'}"
        )
    pr("")
    if bundle.get("type_easier"):
        pr(f"Target comparison: {bundle['type_easier']}")
        pr("")
    pr("Interpretation:")
    pr("  Lead with Macro-F1 and confusion structure; qualify accuracy when concentration is high.")
    pr("Files: model_and_family_failure_summary.md, top_confusion_pairs.csv, family_vs_type_performance.csv")
    pr("")
    pr("Q3 — skepticism (why high / what was removed / split & SMOTE):")
    pr("  See terminal blocks below and diagnostics: headline_score_scope.*, high_score_audit.*, ")
    pr("  false_attribution_audit.*, split_contamination_audit.*, smote_effect_check.*, leakage_safe_score_comparison.*")
    pr("")

    sk2 = bundle.get("skeptic_audits")
    if isinstance(sk2, dict) and sk2:
        _hssa.print_skeptic_audit_followup_terminal(sk2, pr=pr, du=du)

    du.print_section("RESEARCH RUN SUMMARY")
    gov_n = q1.get("governed_samples", "—")
    fam_n = q1.get("families_represented", "—")
    typ_n = q1.get("malware_types_represented", "—")
    t5 = float((q1.get("concentration") or {}).get("top5_share_pct") or 0)
    pr("1. Dataset:")
    pr(
        f"   Governed cohort {gov_n}; {fam_n} families, {typ_n} types; "
        f"top-5 share ≈ {t5:.2f}% — Macro-F1 is primary."
    )
    pr("2. Feature signal:")
    raw_perm_n = int(q2.get("permission_raw_observation_n") or 0)
    raw_perm_pct = float(q2.get("permission_raw_observation_pct") or 0)
    fused_perm_n = int(q2.get("permission_signal_n") or 0)
    fused_perm_pct = float(q2.get("permission_signal_pct") or 0)
    vendor_merge_pct = float(q2.get("vendor_merge_pct") or 0)
    vendor_merge_label = _vendor_merge_coverage_label(vendor_merge_pct)
    if fused_perm_n == 0 and raw_perm_n > 0:
        pr(
            f"   Raw permission observations cover {raw_perm_pct:.1f}% of the cohort, "
            f"but fused permission features are disabled/absent for this run; "
            f"parsed vendor merge {vendor_merge_label} ({vendor_merge_pct:.1f}%)."
        )
    else:
        pr(
            f"   Permissions broad ({fused_perm_pct:.1f}% rows with PI signal); "
            f"parsed vendor merge {vendor_merge_label} ({vendor_merge_pct:.1f}%)."
        )
    pr("3. Model behavior:")
    pr(
        f"   {mk}: Macro-F1={float(bundle.get('macro_f1') or 0):.4f}, "
        f"weighted F1={float(bundle.get('wf1') or 0):.4f}."
    )
    pr("   Treat very high headline scores as **promising but not final proof** until support filtering, split ")
    pr("   contamination, SMOTE effect, leakage-safe ablations, and false-attribution audits are reviewed.")
    pr("")
    gov_n = q1.get("governed_samples", "—")
    fam_gov = q1.get("families_represented", "—")
    train_n = q1.get("trainable_after_support_filter", "—")
    fam_tr = getattr(app_config, "RUNTIME_TRAINING_LABEL_CLASS_COUNT", None)
    try:
        drop_s = (
            int(q1.get("aligned_supervised_samples") or 0) - int(q1.get("trainable_after_support_filter") or 0)
            if q1.get("aligned_supervised_samples") is not None and q1.get("trainable_after_support_filter") is not None
            else None
        )
    except Exception:
        drop_s = None
    pr("4. Headline task boundary:")
    pr(
        f"   Governed cohort ≈ {gov_n} samples / {fam_gov} families; headline training applies to "
        f"≈ {train_n} samples / {fam_tr} supported families"
        + (f" after dropping ≈{drop_s} samples from low-support families." if drop_s else ".")
    )
    pr("")
