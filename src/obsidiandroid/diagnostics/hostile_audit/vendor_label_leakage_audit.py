"""Structured vendor semantic vs structural signal audit."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.common import output_hygiene as oh


def write_vendor_label_leakage_audit(
    *,
    diagnostics_dir: Path,
    run_id: str,
) -> tuple[Path, Path]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    csv_out = diagnostics_dir / "vendor_label_leakage_audit.csv"
    md_out = diagnostics_dir / "vendor_label_leakage_audit.md"

    abl = oh.resolve_ablation_summary_path(diagnostics_dir, run_id)

    rows: list[dict[str, Any]] = []

    contract_cols: dict[str, int] = {}
    contract_path = oh.resolve_feature_contract_path(diagnostics_dir, run_id)
    if contract_path.exists():
        try:
            payload = json.loads(contract_path.read_text(encoding="utf-8"))
            colnames = payload.get("columns") or payload.get("feature_names") or []
            if isinstance(colnames, list):
                for name in colnames:
                    s = str(name).lower()
                    if "parsed_family" in s:
                        contract_cols["parsed_family_like"] = contract_cols.get("parsed_family_like", 0) + 1
                    elif "malware_type" in s:
                        contract_cols["malware_type_like"] = contract_cols.get("malware_type_like", 0) + 1
                    elif "threat_class" in s:
                        contract_cols["threat_class_like"] = contract_cols.get("threat_class_like", 0) + 1
        except Exception:
            pass

    if contract_cols:
        for k, v in contract_cols.items():
            rows.append({"audit_row": "contract_prefix_count", "feature_group": k, "value": v, "notes": contract_path.name})

    if abl.exists():
        df = pd.read_csv(abl)
        if "label_target" in df.columns:
            df = df[df["label_target"] == "family_canonical_default"]
        piv = df.pivot_table(index="experiment", columns="model", values="macro_f1_score", aggfunc="mean")
        if "vendor_full" in piv.index or "vendor_only" in piv.index:
            base_idx = "vendor_full" if "vendor_full" in piv.index else "vendor_only"
            base_row = piv.loc[base_idx]
            for exp in piv.index.astype(str):
                if exp == base_idx:
                    continue
                delta = piv.loc[exp] - base_row
                for model in delta.index:
                    rows.append(
                        {
                            "audit_row": "macro_f1_drop_vs_vendor_full",
                            "feature_group": str(exp),
                            "value": round(float(delta[model]), 6),
                            "notes": str(model),
                        }
                    )

    experiment_interpretation = [
        ("vendor_full", "includes parsed_family_* + malware_type_* + threat_class_* (high semantic leakage risk)"),
        ("vendor_no_parsed_family", "drops Parsed Family semantics; measures threat/type-only vendor signal"),
        ("vendor_no_family_no_type", "attempts stripped vendor semantics — see Stage ablation builders"),
        ("vendor_detection_binary_only", "per-engine binary positives — behavioural / AV agreement signal"),
        ("vendor_consensus_scores_only", "aggregate scan scores without per-vendor lexical fields"),
        ("permissions_raw", "BoW permission flags — orthogonal to vendor naming unless correlated by campaign"),
        ("full_fused", "combined vendor lexical + metadata + permission fusion"),
    ]
    for name, interp in experiment_interpretation:
        rows.append({"audit_row": "experiment_definition", "feature_group": name, "value": "", "notes": interp})

    if not rows:
        rows.append(
            {"audit_row": "stub", "feature_group": "", "value": "", "notes": "no ablation/feature_contract inputs"}
        )

    keys = sorted({k for r in rows for k in r})
    with csv_out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in keys})

    md_lines = [
        "# Vendor label leakage audit",
        "",
        "## Key hostile question",
        "",
        "**Are we classifying behaviour, or re-encoding AV lexical family strings?**",
        "Interpret large Macro-F1 with `vendor_full` but collapse with `vendor_no_parsed_family` / "
        "`vendor_detection_binary_only` as evidence of **name-semantics leakage** dominating.",
        "",
        "## CSV artifact",
        "",
        f"- `{csv_out.name}`",
        "",
        "## Feature importances",
        "",
        "_Not exported in this audit pass_: tree importances live inside pickled models; ",
        "enable a diagnostics export hook if reviewers require per-split importance tables.",
        "",
    ]
    md_out.write_text("\n".join(md_lines), encoding="utf-8")
    return csv_out, md_out
