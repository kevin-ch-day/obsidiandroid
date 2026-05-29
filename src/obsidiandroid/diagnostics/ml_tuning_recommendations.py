"""ML tuning recommendations derived from run-scoped diagnostics."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.common import output_hygiene as oh


FAMILY_TARGETS = ("family_id", "family_canonical_default", "family_within_type")


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _normalize_ablation_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    out = df.copy()
    rename = {
        "feature_set_label": "experiment",
        "Feature Set": "experiment",
        "Model": "model",
        "MacroF1": "macro_f1_score",
        "macro_f1": "macro_f1_score",
        "weighted_f1": "weighted_f1_score",
    }
    out = out.rename(columns={k: v for k, v in rename.items() if k in out.columns})
    if "experiment" not in out.columns or "macro_f1_score" not in out.columns:
        return pd.DataFrame()
    if "label_target" not in out.columns:
        out["label_target"] = "family_id"
    if "model" not in out.columns:
        out["model"] = ""
    out["experiment"] = out["experiment"].fillna("").astype(str)
    out["label_target"] = out["label_target"].fillna("").astype(str)
    out["model"] = out["model"].fillna("").astype(str)
    out["macro_f1_score"] = pd.to_numeric(out["macro_f1_score"], errors="coerce")
    if "weighted_f1_score" in out.columns:
        out["weighted_f1_score"] = pd.to_numeric(out["weighted_f1_score"], errors="coerce")
    if "accuracy" in out.columns:
        out["accuracy"] = pd.to_numeric(out["accuracy"], errors="coerce")
    return out.dropna(subset=["macro_f1_score"])


def _best_by_experiment(df: pd.DataFrame, *, label_targets: tuple[str, ...]) -> dict[str, dict[str, Any]]:
    if df.empty:
        return {}
    target_df = df[df["label_target"].isin(label_targets)].copy()
    if target_df.empty:
        return {}
    idx = target_df.groupby("experiment", sort=False)["macro_f1_score"].idxmax()
    rows = target_df.loc[idx].to_dict(orient="records")
    return {str(row.get("experiment", "")): row for row in rows}


def _best_target(df: pd.DataFrame, label_target: str) -> dict[str, Any]:
    if df.empty:
        return {}
    target_df = df[df["label_target"] == label_target].copy()
    if target_df.empty:
        return {}
    row = target_df.loc[target_df["macro_f1_score"].idxmax()]
    return dict(row.to_dict())


def _best_target_from_family_vs_type(diagnostics_dir: Path, label_target: str) -> dict[str, Any]:
    df = _read_csv(diagnostics_dir / "family_vs_type_performance.csv")
    if df.empty:
        return {}
    df = df.rename(columns={"macro_f1": "macro_f1_score"})
    if "label_target" not in df.columns or "macro_f1_score" not in df.columns:
        return {}
    df["label_target"] = df["label_target"].fillna("").astype(str)
    df["macro_f1_score"] = pd.to_numeric(df["macro_f1_score"], errors="coerce")
    target_df = df[df["label_target"] == label_target].dropna(subset=["macro_f1_score"])
    if target_df.empty:
        return {}
    row = target_df.loc[target_df["macro_f1_score"].idxmax()].to_dict()
    if "experiment" not in row and "best_experiment" in row:
        row["experiment"] = row.get("best_experiment")
    if "model" not in row and "best_model" in row:
        row["model"] = row.get("best_model")
    return dict(row)


def _float(row: dict[str, Any] | None, key: str) -> float | None:
    if not row:
        return None
    try:
        value = row.get(key)
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None


def _recommendation(
    rows: list[dict[str, Any]],
    *,
    priority: str,
    area: str,
    finding: str,
    action: str,
    evidence: str,
) -> None:
    rows.append(
        {
            "priority": priority,
            "area": area,
            "finding": finding,
            "recommended_action": action,
            "evidence": evidence,
        }
    )


def _read_top_confusion(diagnostics_dir: Path) -> pd.DataFrame:
    path = diagnostics_dir / "top_confusion_pairs.csv"
    df = _read_csv(path)
    if df.empty:
        return df
    return df.rename(columns={c: c.strip() for c in df.columns})


def build_ml_tuning_recommendations(
    *,
    diagnostics_dir: Path,
    run_id: str,
) -> dict[str, Any]:
    """Build ML tuning recommendations from ablation/confusion diagnostics."""
    rid = oh.normalize_artifact_run_id(run_id)
    ablation_candidates = [
        diagnostics_dir / f"feature_set_ablation_summary_{rid}.csv",
        diagnostics_dir / "feature_set_ablation_summary.csv",
        diagnostics_dir / f"ablation_summary_{rid}.csv",
        diagnostics_dir / f"ablation_summary_partial_{rid}.csv",
    ]
    ablation_path = next((path for path in ablation_candidates if path.is_file()), ablation_candidates[0])
    if not ablation_path.is_file():
        ablation_path = oh.resolve_feature_set_ablation_summary_path(diagnostics_dir, run_id)
    if not ablation_path.is_file():
        ablation_path = oh.resolve_ablation_summary_path(diagnostics_dir, run_id, allow_partial=True)
    ablation = _normalize_ablation_frame(_read_csv(ablation_path))
    family_best = _best_by_experiment(ablation, label_targets=FAMILY_TARGETS)
    type_best = _best_target(ablation, "type_slug") or _best_target_from_family_vs_type(
        diagnostics_dir,
        "type_slug",
    )

    recommendations: list[dict[str, Any]] = []
    vendor_full = family_best.get("vendor_parsed_full") or family_best.get("vendor_full")
    vendor_safe = family_best.get("vendor_parsed_no_family") or family_best.get("vendor_no_parsed_family")
    full_fused = family_best.get("full_fused")
    permissions_raw = family_best.get("permissions_raw")
    permissions_grouped = family_best.get("permissions_grouped")

    vendor_full_f1 = _float(vendor_full, "macro_f1_score")
    vendor_safe_f1 = _float(vendor_safe, "macro_f1_score")
    full_fused_f1 = _float(full_fused, "macro_f1_score")
    perm_raw_f1 = _float(permissions_raw, "macro_f1_score")
    perm_grouped_f1 = _float(permissions_grouped, "macro_f1_score")
    type_f1 = _float(type_best, "macro_f1_score")

    if vendor_full_f1 is not None and vendor_safe_f1 is not None:
        delta = vendor_full_f1 - vendor_safe_f1
        if delta >= 0.12:
            _recommendation(
                recommendations,
                priority="high",
                area="vendor_feature_processing",
                finding=f"Parsed vendor-family semantics exceed safer vendor baseline by Macro-F1 {delta:.4f}.",
                action=(
                    "Do not use parsed family strings as the default headline family feature. "
                    "Tune with vendor_no_parsed_family, detection-binary, and consensus-score surfaces first."
                ),
                evidence=f"vendor_full={vendor_full_f1:.4f}; vendor_safe={vendor_safe_f1:.4f}",
            )

    if vendor_full_f1 is not None and full_fused_f1 is not None:
        delta = vendor_full_f1 - full_fused_f1
        if delta >= 0.05:
            _recommendation(
                recommendations,
                priority="high",
                area="fusion_policy",
                finding=f"Full fused underperforms parsed vendor full by Macro-F1 {delta:.4f}.",
                action=(
                    "Treat fusion as a separate experiment, not automatic improvement. "
                    "Compare exact feature hashes and tune permission/vendor fusion only after leakage-safe baselines improve."
                ),
                evidence=f"vendor_full={vendor_full_f1:.4f}; full_fused={full_fused_f1:.4f}",
            )

    best_family_f1 = max(
        [x for x in (vendor_safe_f1, full_fused_f1, perm_raw_f1, perm_grouped_f1) if x is not None],
        default=None,
    )
    if type_f1 is not None and best_family_f1 is not None and (type_f1 - best_family_f1) >= 0.20:
        _recommendation(
            recommendations,
            priority="high",
            area="target_strategy",
            finding=f"Type-level task is materially easier than leakage-safe family task by Macro-F1 {(type_f1 - best_family_f1):.4f}.",
            action=(
                "Process coarse type_slug and family_id as separate modeling tracks. "
                "Use type_slug for coarse claims and family_id for guarded tail-family analysis."
            ),
            evidence=f"type_best={type_f1:.4f}; best_leakage_safe_family={best_family_f1:.4f}",
        )

    best_perm = max([x for x in (perm_raw_f1, perm_grouped_f1) if x is not None], default=None)
    if best_perm is not None and full_fused_f1 is not None and abs(full_fused_f1 - best_perm) <= 0.10:
        _recommendation(
            recommendations,
            priority="medium",
            area="permission_processing",
            finding="Permission-only family performance is close enough to fused performance to deserve first-class tuning.",
            action=(
                "Tune permission grouping, rare-permission pruning, and type-conditioned permission models before expanding vendor lexical features."
            ),
            evidence=f"permission_best={best_perm:.4f}; full_fused={full_fused_f1:.4f}",
        )

    confusion = _read_top_confusion(diagnostics_dir)
    if not confusion.empty and {"count", "shared_type"} <= set(confusion.columns):
        total_conf = int(pd.to_numeric(confusion["count"], errors="coerce").fillna(0).sum())
        cross = confusion[confusion["shared_type"].fillna("").astype(str).str.lower().isin({"no", "false", "0"})]
        cross_conf = int(pd.to_numeric(cross["count"], errors="coerce").fillna(0).sum())
        if total_conf > 0 and cross_conf / total_conf >= 0.25:
            _recommendation(
                recommendations,
                priority="medium",
                area="hierarchical_modeling",
                finding=f"Cross-type family confusions account for {cross_conf}/{total_conf} top-confusion rows.",
                action=(
                    "Evaluate hierarchical prediction: first type_slug, then family-within-type. "
                    "Block or penalize cross-type family predictions in the resolver audit."
                ),
                evidence=f"top_confusion_cross_type_share={cross_conf / total_conf:.3f}",
            )

    payload = {
        "run_id": run_id,
        "ablation_source": str(ablation_path),
        "recommendation_count": len(recommendations),
        "recommendations": recommendations,
        "metrics": {
            "vendor_full_family_macro_f1": vendor_full_f1,
            "vendor_safe_family_macro_f1": vendor_safe_f1,
            "full_fused_family_macro_f1": full_fused_f1,
            "permissions_raw_family_macro_f1": perm_raw_f1,
            "permissions_grouped_family_macro_f1": perm_grouped_f1,
            "type_slug_macro_f1": type_f1,
        },
    }
    return payload


def write_ml_tuning_recommendations(
    *,
    diagnostics_dir: Path,
    run_id: str,
) -> tuple[Path, Path, Path, dict[str, Any]]:
    """Write JSON/CSV/Markdown ML tuning recommendations."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    payload = build_ml_tuning_recommendations(diagnostics_dir=diagnostics_dir, run_id=run_id)
    json_path = diagnostics_dir / f"ml_tuning_recommendations_{run_id}.json"
    csv_path = diagnostics_dir / f"ml_tuning_recommendations_{run_id}.csv"
    md_path = diagnostics_dir / f"ml_tuning_recommendations_{run_id}.md"

    json_text = json.dumps(payload, indent=2, sort_keys=True)
    json_path.write_text(json_text + "\n", encoding="utf-8")

    rows = list(payload.get("recommendations") or [])
    fieldnames = ["priority", "area", "finding", "recommended_action", "evidence"]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})

    lines = [
        f"# ML tuning recommendations — `{run_id}`",
        "",
        "These recommendations are derived from ablation, leakage-safe feature surfaces, and confusion diagnostics.",
        "",
        "## Metrics",
        "",
    ]
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    for key, value in metrics.items():
        display = "n/a" if value is None else f"{float(value):.4f}"
        lines.append(f"- `{key}`: {display}")
    lines.extend(["", "## Recommendations", ""])
    if rows:
        for row in rows:
            lines.extend(
                [
                    f"### {str(row.get('priority', '')).upper()} — {row.get('area', '')}",
                    "",
                    f"- Finding: {row.get('finding', '')}",
                    f"- Action: {row.get('recommended_action', '')}",
                    f"- Evidence: `{row.get('evidence', '')}`",
                    "",
                ]
            )
    else:
        lines.append("- No automatic tuning recommendations were triggered by current thresholds.")
    md_text = "\n".join(lines).rstrip() + "\n"
    md_path.write_text(md_text, encoding="utf-8")

    oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=json_path.name,
        text=json_text + "\n",
        global_latest_name="ml_tuning_recommendations.latest.json",
    )
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=csv_path.name,
        csv_text=csv_path.read_text(encoding="utf-8"),
        global_latest_name="ml_tuning_recommendations.latest.csv",
    )
    oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=md_path.name,
        text=md_text,
        global_latest_name="ml_tuning_recommendations.latest.md",
    )
    return md_path, csv_path, json_path, payload
