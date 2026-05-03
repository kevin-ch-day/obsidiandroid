"""Cohort population truth table and mismatch flags."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any


def _safe_int(x: Any) -> int | None:
    try:
        if x is None or (isinstance(x, float) and str(x) == "nan"):
            return None
        return int(x)
    except (TypeError, ValueError):
        return None


def _read_funnel_rows(diagnostics_dir: Path) -> list[dict[str, Any]]:
    p = diagnostics_dir / "cohort_funnel.csv"
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with p.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(dict(row))
    return rows


def _scan_text_for_suspicious_claims(diagnostics_dir: Path, known_counts: dict[str, int]) -> list[dict[str, Any]]:
    """Find markdown/json that mention a population N that contradicts known stage maxima."""
    flags: list[dict[str, Any]] = []
    inverse = {v: k for k, v in known_counts.items() if v > 0}
    if not inverse:
        return flags
    suspicious = []
    skip_name_prefixes = (
        "cohort_population_audit",
        "baseline_comparison",
        "figure_validity_audit",
        "permission_signal_quality_report",
        "vendor_label_leakage_audit",
        "target_validity_audit",
        "temporal_validity_audit",
        "taxonomy_label_quality_audit",
        "recommended_findings",
        "paper_claim_audit",
    )
    for path in sorted(diagnostics_dir.glob("*.md")):
        name = path.name
        if any(name.startswith(pref) for pref in skip_name_prefixes):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        nums = {int(m.group(1)) for m in re.finditer(r"\b(\d{3,5})\b", text)}
        max_truth = max(known_counts.values()) if known_counts.values() else 0
        min_truth = min(v for v in known_counts.values() if v > 0) if any(
            v > 0 for v in known_counts.values()
        ) else 0
        for n in nums:
            if max_truth and n > max_truth + 5:
                suspicious.append((path.name, n, f"mentions {n} rows > max declared stage {max_truth}"))
            elif min_truth and abs(n - max_truth) > 200 and n not in known_counts.values():
                # heuristic: common paper typos
                if n > min_truth and n != max_truth:
                    suspicious.append(
                        (path.name, n, f"mentions {n}; check against governed_cohort={known_counts.get('governed_cohort')}")
                    )
    for name, n, note in suspicious[:40]:
        flags.append({"artifact": name, "population_number": n, "flag": "REVIEW_MENTION", "notes": note})
    return flags


def write_cohort_population_audit(
    *,
    diagnostics_dir: Path,
    run_id: str,
    manifest: dict[str, Any],
    manifest_context: dict[str, Any],
    samples_df: Any,
) -> tuple[Path, Path]:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    man = manifest if isinstance(manifest, dict) else {}
    mctx = manifest_context if isinstance(manifest_context, dict) else {}

    gov = _safe_int(mctx.get("governed_cohort_rows") or man.get("cohort_size"))
    fused = _safe_int(mctx.get("fused_feature_rows"))
    aligned = _safe_int(mctx.get("aligned_supervised_rows"))
    vendor_m = _safe_int(mctx.get("vendor_merge_row_count"))
    post_ls = _safe_int(mctx.get("post_low_support_training_rows"))
    train_n = _safe_int(mctx.get("train_sample_count") or (man.get("split") or {}).get("train_sample_count"))
    test_n = _safe_int(mctx.get("test_sample_count") or (man.get("split") or {}).get("test_sample_count"))
    split_meta = man.get("split") if isinstance(man.get("split"), dict) else {}
    if train_n is None:
        train_n = _safe_int(split_meta.get("train_sample_count"))
    if test_n is None:
        test_n = _safe_int(split_meta.get("test_sample_count"))

    fam_canon_cohort = None
    fam_id_cohort = None
    type_cohort = None
    try:
        import pandas as pd

        if samples_df is not None and isinstance(samples_df, pd.DataFrame) and not samples_df.empty:
            if "family_canonical" in samples_df.columns:
                fam_canon_cohort = int(samples_df["family_canonical"].nunique(dropna=True))
            if "family_id" in samples_df.columns:
                fam_id_cohort = int(samples_df["family_id"].nunique(dropna=True))
            if "type_slug" in samples_df.columns:
                type_cohort = int(samples_df["type_slug"].nunique(dropna=True))
    except Exception:
        pass

    funnel = _read_funnel_rows(diagnostics_dir)
    funnel_map = {}
    for row in funnel:
        st = str(row.get("stage", "")).strip()
        rc = row.get("row_count", "")
        try:
            funnel_map[st] = int(float(rc)) if str(rc).strip() not in {"", "nan"} else None
        except (TypeError, ValueError):
            funnel_map[st] = None

    rows: list[dict[str, Any]] = [
        {
            "metric": "governed_cohort_rows",
            "value": gov,
            "source": "manifest_context / manifest.cohort_size",
            "interpretation": "Prepared cohort (samples_df) before train-time filters",
        },
        {
            "metric": "vendor_feature_rows",
            "value": vendor_m,
            "source": "manifest_context.vendor_merge_row_count",
            "interpretation": "Row authority for vendor-encoded block (extras join left)",
        },
        {
            "metric": "fused_feature_rows",
            "value": fused,
            "source": "manifest_context.fused_feature_rows",
            "interpretation": "Feature matrix height before supervised alignment",
        },
        {
            "metric": "aligned_supervised_rows",
            "value": aligned,
            "source": "manifest_context.aligned_supervised_rows",
            "interpretation": "Intersection(feature index, label sample_id)",
        },
        {
            "metric": "post_low_support_training_rows",
            "value": post_ls,
            "source": "RUNTIME_POST_LOW_SUPPORT_TRAINING_ROWS",
            "interpretation": "Rows entering train_models after min-family support",
        },
        {
            "metric": "train_eval_rows",
            "value": train_n,
            "source": "split_audit / RUNTIME_SPLIT_METADATA",
            "interpretation": "Train shard (split freeze audit)",
        },
        {
            "metric": "test_eval_rows",
            "value": test_n,
            "source": "split_audit",
            "interpretation": "Test shard",
        },
        {
            "metric": "distinct_families_canonical_governed_cohort",
            "value": fam_canon_cohort,
            "source": "samples_df.family_canonical",
            "interpretation": "Unique family_canonical in governed cohort",
        },
        {
            "metric": "distinct_family_ids_governed_cohort",
            "value": fam_id_cohort,
            "source": "samples_df.family_id",
            "interpretation": "Unique family_id in governed cohort (if column present)",
        },
        {
            "metric": "distinct_types_governed_cohort",
            "value": type_cohort,
            "source": "samples_df",
            "interpretation": "Unique type_slug values",
        },
    ]

    mismatches: list[dict[str, Any]] = []
    if gov and aligned and gov > aligned + 5:
        mismatches.append(
            {
                "flag": "COHORT_SUPERSET_GT_ALIGNED",
                "severity": "HIGH",
                "notes": (
                    f"Governed cohort ({gov}) exceeds aligned supervised ({aligned}); "
                    "any figure titled 'cohort N' without naming the stage mis-states population."
                ),
            }
        )
    if post_ls and train_n and post_ls != train_n + (test_n or 0):
        # train+test equals aligned after split only if aligned==post_ls; heuristic warn
        if aligned and train_n + (test_n or 0) > aligned:
            mismatches.append(
                {
                    "flag": "SPLIT_ROWS_EXCEED_ALIGNED",
                    "severity": "HIGH",
                    "notes": "train_n + test_n > aligned_supervised_rows (impossible)",
                }
            )

    cov_path = diagnostics_dir / f"feature_build_coverage_{run_id}.json"
    if not cov_path.exists():
        cov_path = diagnostics_dir / "feature_build_coverage.latest.json"
    if cov_path.exists():
        try:
            payload = json.loads(cov_path.read_text(encoding="utf-8"))
            rows.append(
                {
                    "metric": "cohort_missing_from_feature_matrix",
                    "value": payload.get("cohort_rows_missing_from_feature_matrix"),
                    "source": str(cov_path.name),
                    "interpretation": "Cohort ids without vendor feature row",
                }
            )
        except Exception:
            pass

    known_counts = {
        "governed_cohort": gov or 0,
        "aligned": aligned or 0,
        "post_low_support": post_ls or 0,
        "train": train_n or 0,
        "test": test_n or 0,
    }
    mismatches.extend(_scan_text_for_suspicious_claims(diagnostics_dir, known_counts))

    csv_path = diagnostics_dir / "cohort_population_audit.csv"
    fieldnames = ["metric", "value", "source", "interpretation"]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})

    flags_path = diagnostics_dir / "cohort_population_audit_flags.csv"
    with flags_path.open("w", encoding="utf-8", newline="") as ff:
        wf = csv.DictWriter(ff, fieldnames=["flag", "severity", "notes", "artifact", "population_number"])
        wf.writeheader()
        for m in mismatches:
            wf.writerow(
                {
                    "flag": m.get("flag", ""),
                    "severity": m.get("severity", ""),
                    "notes": m.get("notes", ""),
                    "artifact": m.get("artifact", ""),
                    "population_number": m.get("population_number", ""),
                }
            )

    md_path = diagnostics_dir / "cohort_population_audit.md"
    md_lines = [
        "# Cohort & population audit",
        "",
        "Use these counts when wording any headline N; **never** silently substitute governed cohort ",
        "for aligned rows, train rows, or test rows.",
        "",
        "## Declared populations",
        "",
        "| Metric | Value | Source | Interpretation |",
        "|--------|-------|--------|----------------|",
    ]
    for r in rows:
        md_lines.append(
            f"| {r.get('metric')} | `{r.get('value')}` | {r.get('source')} | {r.get('interpretation')} |"
        )

    md_lines.extend(["", "## Mismatch flags", ""])
    if mismatches:
        md_lines.append("| Flag | Severity | Notes |")
        md_lines.append("|------|----------|-------|")
        for m in mismatches:
            if "flag" in m:
                md_lines.append(f"| {m.get('flag')} | {m.get('severity', '')} | {m.get('notes', '')} |")
    else:
        md_lines.append("_No automated high-severity population contradictions detected._")

    md_lines.extend(
        [
            "",
            "## Funnel cross-check (cohort_funnel.csv)",
            "",
            "If present, compare each `stage` row_count to the table above; figures must name the stage.",
            "",
        ]
    )
    for st, val in sorted(funnel_map.items()):
        md_lines.append(f"- **{st}:** `{val}`")

    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return csv_path, md_path
