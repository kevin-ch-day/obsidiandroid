"""Temporal slicing sanity checks (random split ≠ temporal generalization)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.diagnostics.split_ledger_resolve import resolve_split_freeze_csv


def _sample_year(series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(series, errors="coerce", utc=True)
    return dt.dt.year


def write_temporal_validity_audit(
    *,
    diagnostics_dir: Path,
    run_id: str,
    manifest_context: dict[str, Any],
    samples_df: pd.DataFrame | None,
    profile_params: dict[str, Any] | None,
) -> tuple[Path | None, Path | None]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    md_path = diagnostics_dir / "temporal_validity_audit.md"
    fy_path = diagnostics_dir / "family_year_support.csv"

    if samples_df is None or samples_df.empty:
        fy_path.write_text("status,notes\nstub,no_samples\n", encoding="utf-8")
        md_path.write_text("# Temporal validity\n\n_No samples dataframe available._\n", encoding="utf-8")
        return fy_path, md_path

    s = samples_df.copy()
    time_cols = [
        col
        for col in (
            "vt_first_submission_at_utc",
            "effective_first_seen_at_utc",
            "vt_first_seen_itw_date",
        )
        if col in s.columns
    ]
    cohort_gates = (profile_params or {}).get("cohort_gates", {}) if isinstance(profile_params, dict) else {}
    win_start = str(cohort_gates.get("time_window_start_utc", "") or "")
    win_end = str(cohort_gates.get("time_window_end_utc", "") or "")

    year_series = None
    used_col = ""
    for col in time_cols:
        ys = _sample_year(s[col])
        if ys.notna().sum() >= max(10, len(s) // 10):
            year_series = ys
            used_col = col
            break
    fy_rows: list[dict[str, Any]] = []
    if year_series is not None and "family_canonical" in s.columns:
        tmp = pd.DataFrame(
            {"family_canonical": s["family_canonical"].astype(str), "year": year_series.astype("Int64")}
        ).dropna()
        grp = tmp.groupby("family_canonical")["year"]
        agg = grp.agg(["min", "max", "median", "count"]).reset_index()
        for _, row in agg.iterrows():
            fy_rows.append(
                {
                    "family_canonical": row["family_canonical"],
                    "year_min": int(row["min"]) if pd.notna(row["min"]) else "",
                    "year_max": int(row["max"]) if pd.notna(row["max"]) else "",
                    "year_median": float(row["median"]) if pd.notna(row["median"]) else "",
                    "sample_support": int(row["count"]),
                }
            )

    suspicious: list[str] = []
    if fy_rows:
        for r in fy_rows:
            ymin = r.get("year_min")
            ymax = r.get("year_max")
            if isinstance(ymin, int) and isinstance(ymax, int) and ymin > ymax:
                suspicious.append(str(r.get("family_canonical")))
        # 2026 in 2020-2025 window profile
        for r in fy_rows:
            ym = r.get("year_max")
            if isinstance(ym, int) and ym >= 2026:
                suspicious.append(f"{r['family_canonical']} max_year>=2026 while profile may cap 2025")

    split_path = resolve_split_freeze_csv(diagnostics_dir, run_id)
    mix_rows: list[dict[str, Any]] = []
    if split_path.exists() and year_series is not None and "sample_id" in s.columns:
        try:
            sp = pd.read_csv(split_path)
            sp["sample_id"] = pd.to_numeric(sp["sample_id"], errors="coerce")
            base = s[["sample_id"]].copy()
            base["_year"] = year_series
            m = sp.merge(base, on="sample_id", how="left")
            for role in ("train", "test"):
                sub = m[m["split_role"] == role]["_year"].dropna()
                if len(sub):
                    mix_rows.append(
                        {
                            "split_role": role,
                            "year_min": int(sub.min()),
                            "year_max": int(sub.max()),
                            "year_mean": round(float(sub.mean()), 4),
                            "notes": "",
                        }
                    )
        except Exception as exc:
            mix_rows.append({"split_role": "error", "year_min": "", "year_max": "", "year_mean": "", "notes": str(exc)})

    holdout_notes: list[str] = []
    if year_series is not None:
        try:
            yv = year_series.dropna().astype(int)
            hypothetical_train = sum(int(x) <= 2023 for x in yv.tolist())
            hypothetical_test = sum(int(x) >= 2024 for x in yv.tolist())
            holdout_notes.append(
                f"Temporal counterfactual sizing (whole cohort): would assign ~{hypothetical_train} train yrs<=2023, "
                f"~{hypothetical_test} test yrs>=2024 using column `{used_col}` (not executed — audit only)."
            )
        except Exception:
            holdout_notes.append("Could not approximate temporal counterfactual split.")

    with fy_path.open("w", encoding="utf-8", newline="") as fh:
        if fy_rows:
            w = csv.DictWriter(fh, fieldnames=list(fy_rows[0].keys()))
            w.writeheader()
            for r in fy_rows:
                w.writerow(r)
        else:
            w = csv.writer(fh)
            w.writerow(["status", "notes"])
            w.writerow(["stub", "insufficient temporal columns"])

    md = [
        "# Temporal validity audit",
        "",
        f"- **Declared window (profile cohort_gates):** `{win_start}` — `{win_end}`",
        f"- **Year derivation column:** `{used_col or 'unavailable'}`",
        "",
        "## Why this matters",
        "",
        "**Stratified random splits** stratify labels but still mix historic families across years.",
        "High test Macro-F1 does **not** establish prospective generalization absent time-based splits.",
        "",
        "## Train/test year envelope (split audit ∩ cohort)",
        "",
    ]
    if mix_rows:
        md.append("| Split | Year min | Year max | Mean | Notes |")
        md.append("|-------|----------|----------|------|-------|")
        for r in mix_rows:
            md.append(
                f"| {r.get('split_role')} | `{r.get('year_min')}` | `{r.get('year_max')}` | "
                f"`{r.get('year_mean')}` | {r.get('notes','')} |"
            )
    else:
        md.append("_Could not reconcile split_audit with cohort years._")

    md.append("")
    md.append("## Holdout suggestion (NOT applied)")
    md.extend(["- " + n for n in holdout_notes])
    md.extend(
        [
            "",
            "## Leakage check",
            "",
            "**vt_first_submission** and related timestamps **must not** appear as numeric training features ",
            "(verify feature_contract / modality contract prohibits them). Trends belong in descriptive reporting.",
            "",
        ]
    )
    md_path.write_text("\n".join(md), encoding="utf-8")
    return fy_path, md_path
