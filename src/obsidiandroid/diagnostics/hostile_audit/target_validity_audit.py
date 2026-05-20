"""Per-label-target summary from ablations + heuristic baselines."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.common import output_hygiene as oh


def write_target_validity_audit(
    *,
    diagnostics_dir: Path,
    run_id: str,
    samples_df: pd.DataFrame | None,
) -> tuple[Path, Path]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    abl = oh.resolve_ablation_summary_path(diagnostics_dir, run_id)

    rows: list[dict[str, Any]] = []

    tgt_support: dict[str, dict[str, int]] = {}
    if isinstance(samples_df, pd.DataFrame) and not samples_df.empty and "sample_id" in samples_df.columns:
        s = samples_df.copy()
        mappings = [
            ("family_canonical_default", "family_canonical"),
            ("family_id", "family_id"),
            ("type_slug", "type_slug"),
        ]
        if "family_within_type" in s.columns:
            mappings.append(("family_within_type", "family_within_type"))
        elif "family_canonical" in s.columns and "type_slug" in s.columns:
            s["_fw"] = (
                s["type_slug"].fillna("unknown").astype(str)
                + "::"
                + s["family_canonical"].fillna("unknown").astype(str)
            )
            mappings.append(("family_within_type", "_fw"))

        for slug, col in mappings:
            if col not in s.columns:
                continue
            vc = s[col].fillna("__NA__").astype(str).value_counts()
            tgt_support[slug] = {
                "class_count": int(s[col].fillna("__NA__").astype(str).nunique()),
                "min_class_support": int(vc.min()) if len(vc) else 0,
                "max_class_support": int(vc.max()) if len(vc) else 0,
                "majority_baseline_accuracy": round(float(vc.iloc[0] / max(len(s), 1)), 6) if len(vc) else None,
            }

    if abl.exists():
        df = pd.read_csv(abl)
        if "macro_f1_score" not in df.columns:
            df = pd.DataFrame()
        group_iter: list[tuple[Any, pd.DataFrame]]
        if "label_target" in df.columns:
            group_iter = [(str(slug), g) for slug, g in df.groupby("label_target")]
        else:
            group_iter = [("family_canonical_default", df)]
        for slug, sub in group_iter:
            for exp, grp in sub.groupby("experiment"):
                best = grp["macro_f1_score"].max()
                model = grp.loc[grp["macro_f1_score"].idxmax(), "model"] if len(grp) else ""
                maj_raw = tgt_support.get(str(slug), {}).get("majority_baseline_accuracy")
                try:
                    maj = float(maj_raw) if maj_raw is not None else None
                except (TypeError, ValueError):
                    maj = None
                delta_vs_maj_acc = (
                    round(float(best) - maj, 6) if maj is not None and pd.notna(best) else None
                )
                rows.append(
                    {
                        "label_target": str(slug),
                        "experiment": str(exp),
                        "best_macro_f1": round(float(best), 6) if pd.notna(best) else None,
                        "best_model": str(model),
                        "class_count_sample_frame": tgt_support.get(str(slug), {}).get("class_count"),
                        "min_support_class": tgt_support.get(str(slug), {}).get("min_class_support"),
                        "majority_class_accuracy_approx": tgt_support.get(str(slug), {}).get(
                            "majority_baseline_accuracy"
                        ),
                        "delta_macro_f1_minus_majority_accuracy": delta_vs_maj_acc,
                        "meaningful_for_permissions_raw": (
                            "often_low"
                            if str(exp) == "permissions_raw"
                            else "n/a"
                        ),
                        "notes": "macro_f1 vs majority accuracy mixes scales — use baseline_comparison Macro-F1 for strict Δ",
                    }
                )

    if not rows:
        rows.append(
            {
                "label_target": "stub",
                "experiment": "",
                "best_macro_f1": None,
                "best_model": "",
                "class_count_sample_frame": "",
                "min_support_class": "",
                "majority_class_accuracy_approx": "",
                "delta_macro_f1_minus_majority_accuracy": "",
                "meaningful_for_permissions_raw": "",
                "notes": "no_ablation_summary",
            }
        )

    csv_path = diagnostics_dir / "target_validity_audit.csv"
    fieldnames = list(rows[0].keys())
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    md = diagnostics_dir / "target_validity_audit.md"
    lines = [
        "# Target validity audit",
        "",
        "**Permission features** often track capability and therefore **may align better with `type_slug` or coarse clusters** ",
        "than fine family labels. Inspect `permissions_raw` / `permissions_grouped` Macro-F1 by `label_target`.",
        "",
        "## Summary CSV",
        "",
        f"- `{csv_path.name}`",
        "",
    ]
    if abl.exists():
        lines.append("Rows derive from **ablation_summary** stratified experiments (same deterministic split indices).")

    md.write_text("\n".join(lines), encoding="utf-8")
    return csv_path, md
