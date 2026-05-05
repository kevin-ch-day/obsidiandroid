"""Permission coverage, sparsity, and crude discriminability diagnostics."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import pandas as pd

from analysis.orchestration.permission_features import _fetch_permission_rows  # pylint: disable=protected-access
from obsidiandroid.pipeline import stage_feature_enrichment

build_permission_enrichment_frame = stage_feature_enrichment.build_permission_enrichment_frame


def write_permission_signal_quality(
    *,
    diagnostics_dir: Path,
    samples_df: pd.DataFrame | None,
) -> tuple[Path | None, Path | None]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    csv_path = diagnostics_dir / "permission_signal_quality.csv"
    md_path = diagnostics_dir / "permission_signal_quality_report.md"

    if samples_df is None or samples_df.empty or "sample_id" not in samples_df.columns:
        msg = "No samples dataframe — skipping permission signal quality."
        md_path.write_text(f"# Permission signal quality\n\n{msg}\n", encoding="utf-8")
        csv_path.write_text("status,notes\nstub,{msg}\n", encoding="utf-8")
        return csv_path, md_path

    sids = sorted(
        {int(float(x)) for x in samples_df["sample_id"].tolist() if pd.notna(x)},
    )
    perm_long = _fetch_permission_rows(sids)
    enrichment = build_permission_enrichment_frame(
        samples_df,
        feature_flags={"enable_permission_features": True},
    )
    leakage_pruned = set()
    try:
        from config import app_config

        lr = getattr(app_config, "RUNTIME_LEAKAGE_PRUNING_AUDIT", [])
        if isinstance(lr, list):
            leakage_pruned = {
                str(x.get("column_name")) for x in lr if isinstance(x, dict) and x.get("column_name")
            }
    except Exception:
        pass

    rows: list[dict[str, Any]] = []
    cohort_n = len(sids)

    if perm_long.empty:
        rows.append(
            {
                "metric": "permission_db_rows",
                "value": 0,
                "notes": "no permission observations returned",
            }
        )
    else:
        pl = perm_long.copy()
        pl["permission_string"] = pl["permission_string"].fillna("").astype(str).str.strip().str.lower()
        pl = pl[pl["permission_string"] != ""]
        per_sid = pl.groupby("sample_id").size()
        zeros = cohort_n - int(per_sid.shape[0])
        rows.extend(
            [
                {"metric": "cohort_samples", "value": cohort_n, "notes": "governed cohort sample ids passed"},
                {
                    "metric": "samples_with_any_permission_observation",
                    "value": int(per_sid.shape[0]),
                    "notes": "",
                },
                {"metric": "samples_zero_permission_rows_db", "value": max(zeros, 0), "notes": ""},
                {
                    "metric": "mean_permissions_per_nonempty_sample",
                    "value": round(float(per_sid.mean()), 6) if len(per_sid) else 0.0,
                    "notes": "raw DB observation rows/sample",
                },
            ]
        )
        tops = per_sid.nlargest(min(25, len(per_sid)))
        for sid, ct in tops.items():
            rows.append({"metric": f"heavy_sample_sid_{sid}", "value": int(ct), "notes": "top permissive counts"})

        gs = pl.groupby("permission_string")["sample_id"].nunique().sort_values(ascending=False)
        for tok, ct in gs.head(30).items():
            rows.append(
                {
                    "metric": "global_support_token",
                    "value": int(ct),
                    "notes": str(tok),
                }
            )

        if "permission_source" in pl.columns:
            src = pl["permission_source"].fillna("UNKNOWN").astype(str).str.upper()
            rows.append(
                {
                    "metric": "rate_oem_or_app_defined_source",
                    "value": round(float(src.isin({"OEM", "APP_DEFINED"}).mean()), 6),
                    "notes": "",
                }
            )
        if "protection_level" in pl.columns:
            prot = pl["protection_level"].fillna("UNKNOWN").astype(str).str.upper()
            rows.append(
                {
                    "metric": "rate_dangerous_prot_token",
                    "value": round(float(prot.str.contains("DANGEROUS", regex=False).mean()), 6),
                    "notes": "",
                }
            )
            rows.append(
                {
                    "metric": "rate_unknown_prot",
                    "value": round(float((prot.str.strip() == "UNKNOWN").mean()), 6),
                    "notes": "",
                }
            )

    merged = samples_df.copy()
    if (
        isinstance(enrichment, pd.DataFrame)
        and not enrichment.empty
        and "family_canonical" in merged.columns
    ):
        em = enrichment.merge(merged[["sample_id", "family_canonical"]], on="sample_id", how="inner")
        raw_cols = [
            c
            for c in em.columns
            if str(c).startswith("perm__")
            and not str(c).startswith("perm_grp__")
            and c
            not in {
                "perm__dangerous_count",
                "perm__normal_count",
                "perm__oem_count",
                "perm__total_count",
                "family_canonical",
            }
        ]
        fam_means = []
        if raw_cols:
            vc = merged["family_canonical"].astype(str).value_counts()
            top_fams = vc.head(min(15, vc.shape[0])).index.astype(str).tolist()
            em_tf = em[em["family_canonical"].astype(str).isin(top_fams)]
            for col in raw_cols[: min(80, len(raw_cols))]:
                if em[col].sum() < 5:
                    continue
                pivot = em_tf.groupby("family_canonical")[col].mean()
                fam_means.append((col, float(pivot.var()), int(em[col].sum())))
            fam_means.sort(key=lambda t: -t[1])
            for col, var_bt, supp in fam_means[:25]:
                rows.append(
                    {
                        "metric": "discriminability_between_top_families_var_mean",
                        "value": round(var_bt, 6),
                        "notes": f"col={col}, perm_sum={supp}",
                    }
                )
        grp_cols = [c for c in em.columns if str(c).startswith("perm_grp__")]
        for col in grp_cols:
            rows.append(
                {
                    "metric": "grouped_feature_total_mass",
                    "value": int(pd.to_numeric(em[col], errors="coerce").fillna(0).sum()),
                    "notes": col,
                }
            )

    for col in sorted(leakage_pruned):
        if col.startswith("perm__"):
            rows.append({"metric": "leakage_pruned_perm_feature", "value": 1, "notes": col})

    fieldnames = ["metric", "value", "notes"]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})

    interpret = (
        "# Permission signal quality\n\n"
        "- **Zeros / coverage**: inspect `samples_zero_permission_rows_db` vs cohort — weak permissions may reflect DB gaps.\n"
        "- **Representation**: sparse high-dim BoW + pruning can erase rare discriminators; grouped features stabilize counts.\n"
        "- **Discriminability column**: coarse between-family variance of per-family mean presence for top-frequency families;\n"
        "  chi-square MI is preferable but omitted here to avoid heavy scipy deps in all environments.\n"
        "- **Dangerous totals**: validated against DB `protection_level`; see `dangerous_bucket` counts in permission_feature_audit.\n"
        "\n## CSV\n\n"
        f"- `{csv_path.name}`\n"
    )
    md_path.write_text(interpret, encoding="utf-8")
    return csv_path, md_path
