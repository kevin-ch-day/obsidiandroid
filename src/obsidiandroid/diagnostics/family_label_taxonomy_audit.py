"""Fast cohort-only audit of malware family label space (no model training).

Builds per-family tables, support-threshold previews, and label-quality heuristics
for research interpretation of supervised family classification scope.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

DEFAULT_THRESHOLDS: tuple[int, ...] = (3, 5, 10, 15, 20)

def _compact_type_distribution(sub: pd.DataFrame) -> str:
    if sub.empty or "type_slug" not in sub.columns:
        return ""
    vc = sub["type_slug"].fillna("unknown").astype(str).str.strip()
    vc = vc.replace("", "unknown").value_counts()
    parts = [f"{k}:{int(v)}" for k, v in vc.items()]
    return ";".join(parts[:24])


def _first_seen_min_max(sub: pd.DataFrame) -> tuple[str, str]:
    for col in ("effective_first_seen_at_utc", "vt_first_seen_itw_date", "vt_first_submission_at_utc"):
        if col not in sub.columns:
            continue
        ts = pd.to_datetime(sub[col], errors="coerce", utc=True)
        if ts.notna().any():
            mn = ts.min()
            mx = ts.max()
            return (mn.isoformat() if pd.notna(mn) else "", mx.isoformat() if pd.notna(mx) else "")
    return ("", "")


def classify_label_quality(
    canonical: str,
    *,
    sample_count: int,
    is_alias_duplicate: bool,
) -> str:
    """Single primary quality bucket (first-pass heuristics)."""
    if is_alias_duplicate:
        return "alias_candidate"
    c = (canonical or "").strip()
    cl = c.lower()
    if not c or cl in ("unknown", "unmapped", "other", "none", "nan"):
        return "unknown_or_unresolved"
    if sample_count <= 1:
        return "one_off_identifier"
    if any(
        x in cl
        for x in (
            "generic",
            "trojan/android",
            "/android.generic",
            "malware.android",
            "android.os.",
        )
    ):
        return "generic_av_label"
    type_words = {
        "banker",
        "adware",
        "stealer",
        "spyware",
        "trojan",
        "ransomware",
        "downloader",
        "worm",
        "rat",
        "sms-trojan",
        "sms_trojan",
    }
    if cl in type_words or cl.replace("-", "_") in type_words:
        return "type_like_label"
    if len(c) <= 2:
        return "ambiguous_family_label"
    if re.match(r"^[A-Za-z][A-Za-z0-9_-]{2,}$", c):
        return "canonical_named_family"
    return "needs_review"


def build_family_taxonomy_audit_frames(
    samples_df: pd.DataFrame,
    *,
    training_min_support: int,
    label_col: str = "family_id",
    thresholds: tuple[int, ...] = DEFAULT_THRESHOLDS,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Return (per_family_df, threshold_preview_df, summary_dict)."""
    if samples_df.empty:
        empty_f = pd.DataFrame()
        empty_t = pd.DataFrame()
        return empty_f, empty_t, {"error": "empty_samples_df"}

    if label_col not in samples_df.columns:
        raise ValueError(f"Missing label column {label_col!r} in samples_df")

    df = samples_df.copy()

    def _norm_fid(v: Any) -> str:
        if pd.isna(v):
            return ""
        if isinstance(v, (np.integer, int)):
            return str(int(v))
        if isinstance(v, float) and float(v).is_integer():
            return str(int(v))
        s = str(v).strip()
        if s.isdigit():
            return str(int(s))
        return s

    df["_lid"] = df[label_col].map(_norm_fid)
    df = df[df["_lid"].astype(str).str.len() > 0].copy()

    # Dominant canonical name per family id
    name_col = "family_canonical" if "family_canonical" in df.columns else None
    if not name_col:
        name_col = "family_name" if "family_name" in df.columns else None

    rows: list[dict[str, Any]] = []
    grp = df.groupby("_lid", dropna=False)
    canon_per_id: dict[str, str] = {}
    for fid, sub in grp:
        if name_col:
            mode = sub[name_col].fillna("").astype(str).str.strip()
            mode = mode[mode != ""]
            canon = str(mode.mode().iloc[0]) if len(mode.mode()) else ""
        else:
            canon = ""
        canon_per_id[str(fid)] = canon

    # Same canonical string mapping to multiple family ids → alias_candidate
    inv: dict[str, list[str]] = {}
    for fid, c in canon_per_id.items():
        if not (c or "").strip():
            continue
        inv.setdefault(c.lower(), []).append(fid)
    alias_ids: set[str] = set()
    for _cn, ids in inv.items():
        if len(ids) > 1:
            alias_ids.update(ids)

    governed_n = int(len(df))
    governed_families = int(df["_lid"].nunique())

    for fid, sub in grp:
        fid_s = str(fid)
        n = int(len(sub))
        canon = canon_per_id.get(fid_s, "")
        is_alias = fid_s in alias_ids
        lq = classify_label_quality(canon, sample_count=n, is_alias_duplicate=is_alias)
        tdist = _compact_type_distribution(sub)
        fs_min, fs_max = _first_seen_min_max(sub)
        survived_20 = n >= 20
        dropped_train = n < int(training_min_support)
        if dropped_train:
            status = "dropped_low_support"
            drop_reason = f"below_min_training_support_{training_min_support}"
        else:
            status = "retained_supervised"
            drop_reason = ""

        rows.append(
            {
                "family_id": fid_s,
                "family_canonical_name": canon,
                "sample_count": n,
                "type_slug_distribution": tdist,
                "first_seen_min": fs_min,
                "first_seen_max": fs_max,
                "survived_min_support_20": "yes" if survived_20 else "no",
                "training_drop": "yes" if dropped_train else "no",
                "support_status": status,
                "drop_reason": drop_reason,
                "label_quality": lq,
            }
        )

    per_family = pd.DataFrame(rows)
    per_family = per_family.sort_values(["training_drop", "sample_count"], ascending=[True, False])

    # Threshold preview (same governed cohort, vary min support)
    counts = df.groupby("_lid").size()
    retained_at: dict[int, int] = {}
    for t in sorted(set(thresholds) | {20}):
        retained_at[int(t)] = int((counts >= int(t)).sum())

    threshold_rows: list[dict[str, Any]] = []
    baseline_families_20 = retained_at.get(20, int((counts >= 20).sum()))
    for t in sorted(set(thresholds)):
        kept_mask = counts >= t
        retained_samples = int(counts[kept_mask].sum())
        retained_families = int(kept_mask.sum())
        fam_cov = round(100.0 * retained_families / governed_families, 4) if governed_families else 0.0
        samp_cov = round(100.0 * retained_samples / governed_n, 4) if governed_n else 0.0
        fam_added_vs_20 = retained_families - baseline_families_20
        dropped_f = governed_families - retained_families
        # canonical-named families retained at T
        kept_ids = counts[kept_mask].index.tolist()
        kc = 0
        for rid in kept_ids:
            r = per_family[per_family["family_id"] == str(rid)]
            if not r.empty and str(r.iloc[0]["label_quality"]) == "canonical_named_family":
                kc += 1

        threshold_rows.append(
            {
                "min_support_threshold": t,
                "retained_samples": retained_samples,
                "retained_families": retained_families,
                "sample_coverage_pct": samp_cov,
                "family_coverage_pct": fam_cov,
                "families_added_vs_20": fam_added_vs_20,
                "families_dropped_vs_governed": dropped_f,
                "canonical_named_family_count_retained": kc,
            }
        )

    threshold_df = pd.DataFrame(threshold_rows)

    dropped_df = per_family[per_family["training_drop"] == "yes"]
    def _vc(s: pd.Series) -> dict[str, int]:
        return {str(k): int(v) for k, v in s.value_counts().items()}

    summary = {
        "governed_samples": governed_n,
        "governed_distinct_families": governed_families,
        "training_min_support": int(training_min_support),
        "retained_families_supervised": int((per_family["training_drop"] == "no").sum()),
        "dropped_families_supervised": int(len(dropped_df)),
        "label_quality_counts_governed": _vc(per_family["label_quality"]),
        "label_quality_counts_dropped": _vc(dropped_df["label_quality"]) if len(dropped_df) else {},
    }

    return per_family, threshold_df, summary


def write_family_label_taxonomy_audit(
    samples_df: pd.DataFrame,
    *,
    diagnostics_dir: Path,
    profile_id: str,
    training_min_support: int,
    run_id: str | None = None,
    label_col: str = "family_id",
    artifact_prefix: str = "",
    print_fn: Callable[[str], None] | None = None,
) -> dict[str, Path]:
    """Write CSV/MD artifacts and optionally print terminal audit section."""
    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    rid = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "__taxonomy_audit"
    prefix = str(artifact_prefix or "").strip()

    fam_df, th_df, summary = build_family_taxonomy_audit_frames(
        samples_df,
        training_min_support=training_min_support,
        label_col=label_col,
    )

    csv_path = diagnostics_dir / f"{prefix}family_label_taxonomy_audit.csv"
    md_path = diagnostics_dir / f"{prefix}family_label_taxonomy_audit.md"
    th_csv = diagnostics_dir / f"{prefix}support_threshold_preview.csv"
    th_md = diagnostics_dir / f"{prefix}support_threshold_preview.md"

    fam_df.to_csv(csv_path, index=False)
    th_df.to_csv(th_csv, index=False)

    # Markdown narrative
    dropped = fam_df[fam_df["training_drop"] == "yes"].copy()
    retained_n = int((fam_df["training_drop"] == "no").sum())
    md_lines = [
        f"# Family label taxonomy audit — `{profile_id}`",
        "",
        f"- Run artifact id: `{rid}`",
        f"- Governed cohort samples: **{summary['governed_samples']}**",
        f"- Distinct family ids (governed): **{summary['governed_distinct_families']}**",
        f"- Training min-family support (supervised): **{training_min_support}**",
        f"- Families retained for supervised training: **{retained_n}**",
        f"- Families dropped before supervised training: **{summary['dropped_families_supervised']}**",
        "",
        "## Dropped families (human-readable)",
        "",
    ]
    if dropped.empty:
        md_lines.append("(none)")
    else:
        try:
            md_lines.append(dropped[["family_id", "family_canonical_name", "sample_count", "label_quality"]].to_markdown(index=False))
        except Exception:
            md_lines.append("(see CSV)")

    md_lines.extend(
        [
            "",
            "## Label quality (governed, all families)",
            "",
            json.dumps(summary.get("label_quality_counts_governed", {}), indent=2),
            "",
            "## Interpretation",
            "",
            "The headline supervised model is trained only on families meeting min support — ",
            "see `support_threshold_preview.*` for trade-offs at alternate thresholds.",
            "",
        ]
    )
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    th_md_lines = [
        "# Support threshold preview (no training)",
        "",
        f"- Profile: `{profile_id}`",
        f"- Governed samples: **{summary['governed_samples']}** | families: **{summary['governed_distinct_families']}**",
        "",
        "Preview applies the same row counts per `family_id` as the governed cohort; ",
        "each row varies only the minimum samples required per family to **retain** that label.",
        "",
    ]
    try:
        th_md_lines.append(th_df.to_markdown(index=False))
    except Exception:
        th_md_lines.append("(see support_threshold_preview.csv)")
    th_md_lines.append("")
    th_md.write_text("\n".join(th_md_lines) + "\n", encoding="utf-8")

    if print_fn:
        _print_family_label_space_audit_terminal(
            fam_df=fam_df,
            summary=summary,
            training_min_support=training_min_support,
            print_fn=print_fn,
        )

    return {
        "family_label_taxonomy_audit_csv": csv_path,
        "family_label_taxonomy_audit_md": md_path,
        "support_threshold_preview_csv": th_csv,
        "support_threshold_preview_md": th_md,
        "run_id": rid,
    }


def _print_family_label_space_audit_terminal(
    *,
    fam_df: pd.DataFrame,
    summary: dict[str, Any],
    training_min_support: int,
    print_fn: Callable[[str], None],
) -> None:
    """Emit FAMILY LABEL SPACE AUDIT block (caller supplies du.print_info or similar)."""
    gf = int(summary.get("governed_distinct_families", 0))
    retained = int(summary.get("retained_families_supervised", 0))
    dropped_n = int(summary.get("dropped_families_supervised", 0))
    surv20 = int((fam_df["survived_min_support_20"] == "yes").sum()) if not fam_df.empty else 0

    print_fn("")
    print_fn("=" * 80)
    print_fn("FAMILY LABEL SPACE AUDIT".center(80))
    print_fn("=" * 80)
    print_fn("")
    print_fn(f"Governed family labels: {gf}")
    print_fn(f"Supported at min_support={training_min_support} (supervised headline task): {retained}")
    print_fn(f"Dropped by training support threshold: {dropped_n}")
    print_fn(f"Families with ≥20 samples (cohort): {surv20}")
    print_fn("")
    dropped_df = fam_df[fam_df["training_drop"] == "yes"].sort_values("sample_count", ascending=False)
    if not dropped_df.empty:
        print_fn("Dropped families (id → canonical name, n):")
        for _, r in dropped_df.head(40).iterrows():
            print_fn(
                f"  {r['family_id']}: {r['family_canonical_name'] or '—'} "
                f"(n={int(r['sample_count'])}, quality={r['label_quality']})"
            )
        if len(dropped_df) > 40:
            print_fn(f"  … {len(dropped_df) - 40} more (see family_label_taxonomy_audit.csv)")
        print_fn("")

    print_fn("Dropped labels by quality:")
    dq = summary.get("label_quality_counts_dropped") or {}
    if not dq:
        print_fn("  (none)")
    else:
        canonical = int(dq.get("canonical_named_family", 0))
        generic = int(dq.get("generic_av_label", 0)) + int(dq.get("type_like_label", 0))
        unk = int(dq.get("unknown_or_unresolved", 0))
        alias = int(dq.get("alias_candidate", 0))
        amb = int(dq.get("ambiguous_family_label", 0))
        one_off = int(dq.get("one_off_identifier", 0))
        rev = int(dq.get("needs_review", 0))
        print_fn(f"  canonical_named_family: {canonical}")
        print_fn(f"  generic/type-like: {generic}")
        print_fn(f"  unknown/unresolved: {unk}")
        print_fn(f"  alias candidates: {alias}")
        print_fn(f"  ambiguous: {amb}")
        print_fn(f"  one-off (single sample): {one_off}")
        print_fn(f"  needs_review: {rev}")
    print_fn("")
    print_fn("Interpretation:")
    print_fn("  The headline family model is a supported-family benchmark on a semantic mix of labels.")
    print_fn("  The next research goal is to maximize defensible family coverage, not maximize accuracy.")
    print_fn("")
    print_fn("Artifacts: diagnostics/family_label_taxonomy_audit.csv, family_label_taxonomy_audit.md,")
    print_fn("           support_threshold_preview.csv, support_threshold_preview.md")
    print_fn("")
