"""Phase-2 pairwise permission co-occurrence for malware types.

Read-only. Uses run-scoped aligned feature/label matrices and
``permission_feature_audit.csv`` vocabulary metadata. Does not query
production databases.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from obsidiandroid.reporting.permission_governance_lanes import (
    DEFAULT_THRESHOLDS,
    PROTECTION_LANE_CONTRACT_VERSION,
    classify_headline_strength,
    classify_protection_lane,
    contract_metadata,
    lane_pair_class,
    ordered_lane_pair,
)
from obsidiandroid.reporting.type_permission_pattern_report import (
    detect_source_run_status,
    resolve_git_commit,
    sha256_file,
)

PAIRWISE_COMPOSER_VERSION = "1.2.0"
PAIRWISE_SCHEMA_VERSION = "type_permission_pairwise_v3"

HEADLINE_VOCAB_LANES = frozenset({"AOSP", "OEM", "GOOGLE"})
UNKNOWN_LANE = "UNKNOWN"

DEFAULT_NO_HEADLINE_TYPES = frozenset(
    {
        "backdoor",
        "dropper",
        "sms-trojan",
        "pua",
        "riskware",
        "worm",
        "ransomware",
        "rootkit",
        "subscription-fraud",
        "unknown",
    }
)


def _bh_fdr(p_values: Iterable[float]) -> list[float]:
    """Benjamini-Hochberg FDR q-values (aligned to input order)."""
    vals = list(p_values)
    n = len(vals)
    if n == 0:
        return []
    order = sorted(
        range(n),
        key=lambda i: (
            math.inf
            if vals[i] is None or (isinstance(vals[i], float) and math.isnan(vals[i]))
            else float(vals[i])
        ),
    )
    ranked = [0.0] * n
    prev = 1.0
    for rank, idx in enumerate(reversed(order), start=1):
        p = vals[idx]
        if p is None or (isinstance(p, float) and math.isnan(p)):
            ranked[idx] = float("nan")
            continue
        q = min(prev, float(p) * n / (n - rank + 1))
        prev = q
        ranked[idx] = min(1.0, q)
    return ranked


def _fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p-value via scipy when available."""
    try:
        from scipy.stats import fisher_exact

        _, p = fisher_exact([[a, b], [c, d]], alternative="two-sided")
        return float(p)
    except Exception:
        n = a + b + c + d
        if n == 0:
            return 1.0
        num = abs(a * d - b * c) - n / 2.0
        den = math.sqrt(max((a + b) * (c + d) * (a + c) * (b + d), 1e-12))
        if den <= 0:
            return 1.0
        z = num * math.sqrt(n) / den
        from math import erfc

        return float(min(1.0, erfc(abs(z) / math.sqrt(2.0))))


def _odds_ratio(a: int, b: int, c: int, d: int, *, haldane: float = 0.5) -> float:
    aa, bb, cc, dd = a + haldane, b + haldane, c + haldane, d + haldane
    return float((aa * dd) / (bb * cc))


def _wilson_ci(successes: int, n: int, *, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    phat = successes / n
    denom = 1.0 + z * z / n
    center = (phat + z * z / (2.0 * n)) / denom
    half = (z / denom) * math.sqrt((phat * (1.0 - phat) + z * z / (4.0 * n)) / n)
    return (max(0.0, center - half), min(1.0, center + half))


def resolve_pairwise_inputs(run_root: Path, run_id: str) -> dict[str, Path]:
    """Resolve aligned matrices + permission audit for pairwise mining."""
    run_root = Path(run_root)
    paths = {
        "aligned_features": run_root / "diagnostics" / f"aligned_features_{run_id}.csv.gz",
        "aligned_labels": run_root / "diagnostics" / f"aligned_labels_{run_id}.csv",
        "permission_feature_audit": run_root / "diagnostics" / "permission_feature_audit.csv",
        "coverage": run_root
        / "bundles"
        / "permission_trends"
        / "tables"
        / f"permission_coverage_report_{run_id}.csv",
    }
    missing = [key for key, path in paths.items() if key != "coverage" and not path.is_file()]
    if missing:
        raise FileNotFoundError(f"pairwise inputs missing: {missing}")
    return {key: path for key, path in paths.items() if path.is_file()}


def load_vocab_table(
    audit_path: Path,
    *,
    feature_columns: Iterable[str],
    lanes: frozenset[str] | set[str],
    min_global_support: int,
    retained_only: bool = True,
) -> pd.DataFrame:
    """Select governed permission vocabulary for pairwise mining."""
    audit = pd.read_csv(audit_path)
    feat = set(feature_columns)
    frame = audit[audit["feature_column"].astype(str).isin(feat)].copy()
    if retained_only and "retained_after_pruning" in frame.columns:
        frame = frame[frame["retained_after_pruning"].astype(str).str.lower().eq("yes")].copy()
    frame = frame[frame["pi_bucket_source"].astype(str).isin(set(lanes))].copy()
    frame["global_support"] = pd.to_numeric(frame["global_support"], errors="coerce").fillna(0).astype(int)
    frame = frame[frame["global_support"] >= int(min_global_support)].copy()
    frame = frame.sort_values(["global_support", "permission_string"], ascending=[False, True])
    return frame.reset_index(drop=True)


def classify_pair_reportability(
    *,
    type_slug: str,
    positive_samples: int,
    families_with_pair: int,
    families_used: int,
    largest_family_share_of_positives: float,
    q_value: float | None,
    effect_odds_ratio: float | None,
    min_sample_support: int,
    min_family_support: int,
    no_headline_types: frozenset[str],
    dominance_threshold: float = 0.85,
    min_effect_odds: float = 1.5,
    fdr_alpha: float = 0.05,
    lane_a: str = "",
    lane_b: str = "",
    family_balanced_prevalence: float | None = None,
    min_family_balanced_prevalence: float | None = None,
) -> str:
    """Explicit reportability / suppression class."""
    slug = str(type_slug).strip().lower()
    unresolved = {"unknown_unresolved"}
    if str(lane_a) in unresolved or str(lane_b) in unresolved:
        return "protection_level_unresolved"
    if str(lane_a) == "app_defined" or str(lane_b) == "app_defined":
        return "app_defined_high_cardinality"
    if positive_samples < min_sample_support:
        return "insufficient_sample_support"
    if families_used < min_family_support or families_with_pair < min_family_support:
        return "insufficient_family_support"
    if largest_family_share_of_positives >= dominance_threshold:
        return "single_family_dominated"
    fb_floor = (
        float(min_family_balanced_prevalence)
        if min_family_balanced_prevalence is not None
        else float(DEFAULT_THRESHOLDS["min_family_balanced_prevalence"])
    )
    if (
        family_balanced_prevalence is not None
        and not math.isnan(family_balanced_prevalence)
        and family_balanced_prevalence < fb_floor
    ):
        return "effect_too_small"
    if slug in no_headline_types:
        return (
            "descriptive_type_enriched"
            if (effect_odds_ratio or 0) >= min_effect_odds
            else "exploratory_only"
        )
    if effect_odds_ratio is not None and effect_odds_ratio < min_effect_odds:
        return "effect_too_small"
    if q_value is not None and not math.isnan(q_value) and q_value > fdr_alpha:
        return "not_significant_after_fdr"
    if effect_odds_ratio is not None and effect_odds_ratio >= min_effect_odds:
        return "family_balanced_supported"
    return "descriptive_common"


def compute_type_pairwise_table(
    *,
    matrix: np.ndarray,
    permission_names: list[str],
    type_slugs: np.ndarray,
    family_labels: np.ndarray,
    vocab_meta: pd.DataFrame,
    min_sample_support: int = 30,
    min_family_support: int = 3,
    min_family_size: int = 3,
    no_headline_types: frozenset[str] | None = None,
    max_pairs_per_type: int = 5000,
) -> pd.DataFrame:
    """Compute pairwise co-occurrence metrics per type_slug."""
    no_headline = no_headline_types or DEFAULT_NO_HEADLINE_TYPES
    n_perm = len(permission_names)
    if n_perm < 2:
        return pd.DataFrame()

    meta = vocab_meta.set_index("permission_string")
    lanes = [
        str(meta.loc[name, "pi_bucket_source"]) if name in meta.index else "UNKNOWN"
        for name in permission_names
    ]
    buckets = [
        str(meta.loc[name, "dangerous_bucket"])
        if name in meta.index and "dangerous_bucket" in meta.columns
        else ""
        for name in permission_names
    ]
    gov_lanes = [
        classify_protection_lane(pi_bucket_source=lanes[i], dangerous_bucket=buckets[i], permission_string=permission_names[i])
        for i in range(n_perm)
    ]

    global_co = (matrix.T @ matrix).astype(np.int64)
    n_global = int(matrix.shape[0])

    rows: list[dict[str, Any]] = []
    for type_slug in sorted(set(map(str, type_slugs))):
        type_mask = type_slugs == type_slug
        n_type = int(type_mask.sum())
        if n_type <= 0:
            continue
        x = matrix[type_mask]
        fam = family_labels[type_mask]
        type_pos = x.sum(axis=0).astype(np.int64)
        co = (x.T @ x).astype(np.int64)

        candidates: list[tuple[int, int, int]] = []
        for i, j in combinations(range(n_perm), 2):
            support = int(co[i, j])
            if support >= min_sample_support:
                candidates.append((i, j, support))
        candidates.sort(key=lambda t: (-t[2], permission_names[t[0]], permission_names[t[1]]))
        candidates = candidates[: int(max_pairs_per_type)]

        unique_fams: list[tuple[str, np.ndarray]] = []
        for family in pd.unique(fam):
            name = str(family).strip()
            if name.lower() in {"", "nan", "none", "null", "(null)"}:
                continue
            fam_mask = fam == family
            if int(fam_mask.sum()) >= min_family_size:
                unique_fams.append((name, fam_mask))

        for i, j, support in candidates:
            p_a = permission_names[i]
            p_b = permission_names[j]
            a_count = int(type_pos[i])
            b_count = int(type_pos[j])
            sample_prev = support / n_type
            jaccard = support / max(a_count + b_count - support, 1)
            p_i = a_count / n_type
            p_j = b_count / n_type
            indep_lift = sample_prev / max(p_i * p_j, 1e-12)

            rest_support = int(global_co[i, j] - support)
            rest_n = n_global - n_type
            a, b, c, d = support, n_type - support, rest_support, rest_n - rest_support
            odds = _odds_ratio(a, b, c, d)
            p_raw = _fisher_two_sided(a, b, c, d)
            ci_lo, ci_hi = _wilson_ci(support, n_type)

            fam_prevs: list[float] = []
            fam_positives: list[tuple[str, int, int]] = []
            for fam_name, fam_mask in unique_fams:
                n_f = int(fam_mask.sum())
                pos_f = int((x[fam_mask, i] * x[fam_mask, j]).sum())
                fam_prevs.append(pos_f / n_f if n_f else 0.0)
                fam_positives.append((fam_name, pos_f, n_f))
            families_used = len(fam_prevs)
            families_with_pair = sum(1 for _, pos, _ in fam_positives if pos > 0)
            family_balanced = float(np.mean(fam_prevs)) if fam_prevs else float("nan")
            median_family = float(np.median(fam_prevs)) if fam_prevs else float("nan")
            if support > 0 and fam_positives:
                largest_name, largest_pos, _ = max(fam_positives, key=lambda t: t[1])
                largest_share = largest_pos / support
            else:
                largest_name, largest_pos, largest_share = "", 0, 0.0

            lane_a = gov_lanes[i]
            lane_b = gov_lanes[j]
            lane_lo, lane_hi = ordered_lane_pair(lane_a, lane_b)
            rows.append(
                {
                    "type_slug": type_slug,
                    "permission_a": p_a,
                    "permission_b": p_b,
                    "vocab_lane_a": lanes[i],
                    "vocab_lane_b": lanes[j],
                    "protection_bucket_a": buckets[i],
                    "protection_bucket_b": buckets[j],
                    "permission_a_lane": lane_a,
                    "permission_b_lane": lane_b,
                    "lane_pair_class": lane_pair_class(lane_a, lane_b),
                    "lane_pair_ordered": f"{lane_lo}__{lane_hi}",
                    "type_sample_count": n_type,
                    "positive_sample_count": support,
                    "both_permission_sample_support": support,
                    "sample_weighted_prevalence": sample_prev,
                    "sample_weighted_prevalence_pct": 100.0 * sample_prev,
                    "permission_a_count": a_count,
                    "permission_b_count": b_count,
                    "jaccard": jaccard,
                    "lift_vs_independence": indep_lift,
                    "odds_ratio_type_vs_rest": odds,
                    "p_value_raw": p_raw,
                    "prevalence_ci_low": ci_lo,
                    "prevalence_ci_high": ci_hi,
                    "families_used": families_used,
                    "families_with_pair": families_with_pair,
                    "supporting_family_count": families_with_pair,
                    "family_balanced_prevalence": family_balanced,
                    "family_balanced_prevalence_pct": (
                        100.0 * family_balanced if not math.isnan(family_balanced) else float("nan")
                    ),
                    "median_family_prevalence_pct": (
                        100.0 * median_family if not math.isnan(median_family) else float("nan")
                    ),
                    "largest_family_canonical": largest_name,
                    "largest_family_positive_count": int(largest_pos),
                    "largest_family_share_of_positives": largest_share,
                    "largest_family_contribution": largest_share,
                    "rest_positive_count": rest_support,
                    "rest_sample_count": rest_n,
                }
            )

    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows)
    q_map: dict[Any, float] = {}
    for _type_slug, group in frame.groupby("type_slug"):
        qs = _bh_fdr(group["p_value_raw"].tolist())
        for idx, q in zip(group.index.tolist(), qs):
            q_map[idx] = q
    frame["q_value_fdr"] = [q_map[i] for i in frame.index]
    frame["reportability_status"] = [
        classify_pair_reportability(
            type_slug=str(row.type_slug),
            positive_samples=int(row.positive_sample_count),
            families_with_pair=int(row.families_with_pair),
            families_used=int(row.families_used),
            largest_family_share_of_positives=float(row.largest_family_share_of_positives),
            q_value=float(row.q_value_fdr) if pd.notna(row.q_value_fdr) else None,
            effect_odds_ratio=(
                float(row.odds_ratio_type_vs_rest) if pd.notna(row.odds_ratio_type_vs_rest) else None
            ),
            min_sample_support=min_sample_support,
            min_family_support=min_family_support,
            no_headline_types=no_headline,
            lane_a=str(row.permission_a_lane),
            lane_b=str(row.permission_b_lane),
            family_balanced_prevalence=(
                float(row.family_balanced_prevalence)
                if pd.notna(row.family_balanced_prevalence)
                else None
            ),
        )
        for row in frame.itertuples(index=False)
    ]
    frame["suppression_reason"] = frame["reportability_status"].where(
        ~frame["reportability_status"].isin(
            {"family_balanced_supported", "descriptive_common", "descriptive_type_enriched"}
        ),
        "",
    )
    frame["headline_strength"] = [
        classify_headline_strength(
            reportability_status=str(row.reportability_status),
            family_balanced_prevalence=(
                float(row.family_balanced_prevalence)
                if pd.notna(row.family_balanced_prevalence)
                else None
            ),
        )
        for row in frame.itertuples(index=False)
    ]
    return frame.sort_values(
        [
            "type_slug",
            "lane_pair_class",
            "headline_strength",
            "reportability_status",
            "odds_ratio_type_vs_rest",
            "positive_sample_count",
        ],
        ascending=[True, True, True, True, False, False],
    ).reset_index(drop=True)


def compose_type_permission_pairwise_report(
    *,
    run_root: Path,
    run_id: str,
    output_dir: Path | None = None,
    min_global_support: int = 100,
    min_sample_support: int = 30,
    min_family_support: int = 3,
    min_family_size: int = 3,
    include_app_defined_lane: bool = False,
    max_pairs_per_type: int = 5000,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Mine pairwise permission co-occurrence from aligned run artifacts."""
    run_root = Path(run_root)
    generated_at = datetime.now(timezone.utc).isoformat()
    run_status = detect_source_run_status(run_root)
    paths = resolve_pairwise_inputs(run_root, run_id)

    feature_path = paths["aligned_features"]
    label_path = paths["aligned_labels"]
    audit_path = paths["permission_feature_audit"]

    all_cols = pd.read_csv(feature_path, nrows=0).columns.tolist()
    lanes: set[str] = set(HEADLINE_VOCAB_LANES)
    if include_app_defined_lane:
        lanes.add("APP_DEFINED")

    vocab = load_vocab_table(
        audit_path,
        feature_columns=all_cols,
        lanes=lanes,
        min_global_support=min_global_support,
        retained_only=True,
    )
    if vocab.empty:
        raise RuntimeError("no permissions remained after vocabulary/support filters")

    vocab = vocab.copy()
    vocab["protection_governance_lane"] = [
        classify_protection_lane(
            pi_bucket_source=row.pi_bucket_source,
            dangerous_bucket=getattr(row, "dangerous_bucket", ""),
            permission_string=row.permission_string,
        )
        for row in vocab.itertuples(index=False)
    ]
    perm_cols = vocab["feature_column"].astype(str).tolist()
    features = pd.read_csv(feature_path, usecols=["sample_id"] + perm_cols)
    labels = pd.read_csv(label_path, usecols=["sample_id", "type_slug", "family_canonical"])
    merged = features.merge(labels, on="sample_id", how="inner")
    merged["type_slug"] = merged["type_slug"].fillna("(null)").astype(str)
    merged["family_canonical"] = merged["family_canonical"].fillna("").astype(str)

    permission_names = vocab["permission_string"].astype(str).tolist()
    feature_order = vocab["feature_column"].astype(str).tolist()
    matrix = merged[feature_order].fillna(0).to_numpy(dtype=np.float64)
    matrix = (matrix > 0).astype(np.float64)

    unknown_vocab = load_vocab_table(
        audit_path,
        feature_columns=all_cols,
        lanes={UNKNOWN_LANE},
        min_global_support=1,
        retained_only=False,
    )

    pair_table = compute_type_pairwise_table(
        matrix=matrix,
        permission_names=permission_names,
        type_slugs=merged["type_slug"].to_numpy(),
        family_labels=merged["family_canonical"].to_numpy(),
        vocab_meta=vocab,
        min_sample_support=min_sample_support,
        min_family_support=min_family_support,
        min_family_size=min_family_size,
        max_pairs_per_type=max_pairs_per_type,
    )

    suppression = (
        pair_table["reportability_status"]
        .value_counts()
        .rename_axis("reportability_status")
        .reset_index(name="pair_count")
        if not pair_table.empty
        else pd.DataFrame(columns=["reportability_status", "pair_count"])
    )
    headline = (
        pair_table[pair_table["reportability_status"] == "family_balanced_supported"].copy()
        if not pair_table.empty
        else pair_table
    )
    headline_strong = (
        headline[headline["headline_strength"] == "strong"].copy() if not headline.empty else headline
    )
    headline_moderate = (
        headline[headline["headline_strength"] == "moderate"].copy() if not headline.empty else headline
    )
    within_lane = (
        pair_table[pair_table["lane_pair_class"] == "within_lane"].copy()
        if not pair_table.empty
        else pair_table
    )
    cross_lane = (
        pair_table[pair_table["lane_pair_class"] == "cross_lane"].copy()
        if not pair_table.empty
        else pair_table
    )
    lane_pair_summary = (
        pair_table.groupby(["lane_pair_class", "lane_pair_ordered", "reportability_status"], as_index=False)
        .size()
        .rename(columns={"size": "pair_count"})
        .sort_values(["lane_pair_class", "pair_count"], ascending=[True, False])
        if not pair_table.empty
        else pd.DataFrame(columns=["lane_pair_class", "lane_pair_ordered", "reportability_status", "pair_count"])
    )
    strength_summary = (
        headline["headline_strength"]
        .value_counts()
        .rename_axis("headline_strength")
        .reset_index(name="pair_count")
        if not headline.empty
        else pd.DataFrame(columns=["headline_strength", "pair_count"])
    )

    out_dir = Path(output_dir) if output_dir else run_root / "diagnostics" / "type_permission_pairwise"
    out_dir.mkdir(parents=True, exist_ok=True)

    derived = {
        "pairwise_all": pair_table,
        "pairwise_headline": headline,
        "pairwise_headline_strong": headline_strong,
        "pairwise_headline_moderate": headline_moderate,
        "pairwise_within_lane": within_lane,
        "pairwise_cross_lane": cross_lane,
        "pairwise_lane_pair_summary": lane_pair_summary,
        "pairwise_headline_strength_summary": strength_summary,
        "pairwise_suppression_summary": suppression,
        "pairwise_vocab_used": vocab[
            [
                c
                for c in [
                    "permission_string",
                    "feature_column",
                    "pi_bucket_source",
                    "dangerous_bucket",
                    "protection_governance_lane",
                    "global_support",
                ]
                if c in vocab.columns
            ]
        ],
        "pairwise_unknown_token_inventory": (
            unknown_vocab[
                [c for c in ["permission_string", "feature_column", "global_support"] if c in unknown_vocab.columns]
            ]
            if not unknown_vocab.empty
            else pd.DataFrame(columns=["permission_string", "feature_column", "global_support"])
        ),
    }
    output_hashes: dict[str, str] = {}
    for name, frame in derived.items():
        path = out_dir / f"{name}_{run_id}.csv"
        frame.to_csv(path, index=False)
        frame.to_csv(out_dir / f"{name}.latest.csv", index=False)
        output_hashes[path.name] = sha256_file(path)

    coverage_row: dict[str, Any] = {}
    if "coverage" in paths:
        cov = pd.read_csv(paths["coverage"])
        if not cov.empty:
            coverage_row = cov.iloc[0].to_dict()

    report_md = _render_pairwise_markdown(
        run_id=run_id,
        report_status=str(run_status["report_status"]),
        source_run_status=str(run_status["source_run_status"]),
        headline=headline,
        suppression=suppression,
        vocab=vocab,
        unknown_n=int(len(unknown_vocab)),
        min_global_support=min_global_support,
        min_sample_support=min_sample_support,
        min_family_support=min_family_support,
        coverage_row=coverage_row,
        lane_pair_summary=lane_pair_summary,
        headline_strong=headline_strong,
        strength_summary=strength_summary,
    )
    report_path = out_dir / f"type_permission_pairwise_report_{run_id}.md"
    report_path.write_text(report_md, encoding="utf-8")
    (out_dir / "type_permission_pairwise_report.latest.md").write_text(report_md, encoding="utf-8")
    output_hashes[report_path.name] = sha256_file(report_path)

    input_hashes = {key: sha256_file(path) for key, path in paths.items()}
    manifest = {
        "composer_version": PAIRWISE_COMPOSER_VERSION,
        "report_schema_version": PAIRWISE_SCHEMA_VERSION,
        "generated_at_utc": generated_at,
        "git_commit": resolve_git_commit(repo_root),
        "run_id": run_id,
        "run_root": str(run_root),
        "output_dir": str(out_dir),
        "report_status": run_status["report_status"],
        "source_run_status": run_status["source_run_status"],
        "controls": {
            "min_global_support": min_global_support,
            "min_sample_support": min_sample_support,
            "min_family_support": min_family_support,
            "min_family_size": min_family_size,
            "headline_vocab_lanes": sorted(HEADLINE_VOCAB_LANES),
            "include_app_defined_lane": include_app_defined_lane,
            "unknown_tokens_excluded_from_headline": True,
            "three_way_mining": False,
            "permissions_are_declared_capabilities_not_runtime_behavior": True,
            "generated_outputs_must_not_be_committed": True,
            "no_database_access": True,
            "protection_lane_thresholds": dict(DEFAULT_THRESHOLDS),
        },
        "protection_lane_contract_version": PROTECTION_LANE_CONTRACT_VERSION,
        "protection_lane_contract": contract_metadata(),
        "vocab_permission_count": int(len(vocab)),
        "unknown_token_count": int(len(unknown_vocab)),
        "pair_count_total": int(len(pair_table)),
        "pair_count_headline": int(len(headline)),
        "pair_count_headline_strong": int(len(headline_strong)),
        "pair_count_headline_moderate": int(len(headline_moderate)),
        "pair_count_within_lane": int(len(within_lane)),
        "pair_count_cross_lane": int(len(cross_lane)),
        "headline_strength_summary": {
            str(row.headline_strength): int(row.pair_count) for row in strength_summary.itertuples(index=False)
        }
        if not strength_summary.empty
        else {},
        "suppression_summary": {
            str(row.reportability_status): int(row.pair_count) for row in suppression.itertuples(index=False)
        }
        if not suppression.empty
        else {},
        "source_tables": {key: str(path) for key, path in paths.items()},
        "input_sha256": input_hashes,
        "output_sha256": output_hashes,
        "report_markdown": str(report_path),
    }
    manifest_path = out_dir / f"type_permission_pairwise_manifest_{run_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_dir / f"type_permission_pairwise_manifest_{run_id}.sha256").write_text(
        sha256_file(manifest_path) + "\n",
        encoding="utf-8",
    )
    return manifest


def _render_pairwise_markdown(
    *,
    run_id: str,
    report_status: str,
    source_run_status: str,
    headline: pd.DataFrame,
    suppression: pd.DataFrame,
    vocab: pd.DataFrame,
    unknown_n: int,
    min_global_support: int,
    min_sample_support: int,
    min_family_support: int,
    coverage_row: dict[str, Any],
    lane_pair_summary: pd.DataFrame | None = None,
    headline_strong: pd.DataFrame | None = None,
    strength_summary: pd.DataFrame | None = None,
) -> str:
    lines: list[str] = []
    lines.append(f"# Type permission pairwise co-occurrence (`{run_id}`)")
    lines.append("")
    lines.append(f"- Report status: **{report_status}**")
    lines.append(f"- Source run status: **{source_run_status}**")
    lines.append(f"- Pairwise composer: `{PAIRWISE_COMPOSER_VERSION}`")
    lines.append(f"- Schema: `{PAIRWISE_SCHEMA_VERSION}`")
    lines.append(f"- Protection-lane contract: `{PROTECTION_LANE_CONTRACT_VERSION}`")
    lines.append("- Three-way mining: **disabled**")
    lines.append("")
    if coverage_row:
        lines.append(
            f"- Prepared samples (coverage table): **{int(coverage_row.get('sample_count', 0)):,}**"
        )
        lines.append(
            f"- Permission-evidence samples: **{int(coverage_row.get('samples_with_permission_rows', 0)):,}**"
        )
    lines.append(
        f"- Headline vocabulary lanes: {', '.join(sorted(HEADLINE_VOCAB_LANES))} "
        f"(min global support >= {min_global_support}; permissions used: {len(vocab)})"
    )
    if "protection_governance_lane" in vocab.columns:
        lane_counts = vocab["protection_governance_lane"].value_counts()
        lines.append(
            "- Protection/governance lanes in vocab: "
            + ", ".join(f"`{k}`={int(v)}" for k, v in lane_counts.items())
        )
    lines.append(f"- Unknown tokens inventoried (excluded from headline): **{unknown_n}**")
    lines.append(
        f"- Pair support gates: sample >= {min_sample_support}, families >= {min_family_support}, "
        f"family-balanced prevalence >= {DEFAULT_THRESHOLDS['min_family_balanced_prevalence']}, "
        f"odds >= {DEFAULT_THRESHOLDS['min_effect_odds']}, "
        f"dominance ceiling < {DEFAULT_THRESHOLDS['dominance_threshold']}"
    )
    lines.append("")
    lines.append("## Suppression summary")
    lines.append("")
    if suppression.empty:
        lines.append("No pairs passed the sample-support gate.")
    else:
        lines.append("| reportability_status | pair_count |")
        lines.append("|---|---:|")
        for row in suppression.itertuples(index=False):
            lines.append(f"| `{row.reportability_status}` | {int(row.pair_count):,} |")
    lines.append("")
    lines.append("## Lane-pair summary")
    lines.append("")
    if lane_pair_summary is None or lane_pair_summary.empty:
        lines.append("No lane-pair summary rows.")
    else:
        lines.append("| lane_pair_class | lane_pair_ordered | reportability | pairs |")
        lines.append("|---|---|---|---:|")
        for row in lane_pair_summary.head(40).itertuples(index=False):
            lines.append(
                f"| `{row.lane_pair_class}` | `{row.lane_pair_ordered}` | "
                f"`{row.reportability_status}` | {int(row.pair_count):,} |"
            )
    lines.append("")
    lines.append("## Headline strength tiers")
    lines.append("")
    lines.append(
        "Supported pairs are retained at FB >= 0.05, then tiered: "
        "`strong` (>=0.20), `moderate` (>=0.10), `marginal` (>=0.05)."
    )
    lines.append("")
    if strength_summary is None or strength_summary.empty:
        lines.append("No supported headline rows to tier.")
    else:
        lines.append("| headline_strength | pair_count |")
        lines.append("|---|---:|")
        for row in strength_summary.itertuples(index=False):
            lines.append(f"| `{row.headline_strength}` | {int(row.pair_count):,} |")
    lines.append("")
    lines.append("## Strong headline pairs (FB >= 20%)")
    lines.append("")
    strong = headline_strong if headline_strong is not None else pd.DataFrame()
    if strong.empty:
        lines.append("No strong headline pairs under current gates.")
    else:
        lines.append(
            "| type | permission_a | permission_b | lanes | class | SW% | FB% | families | OR | q |"
        )
        lines.append("|---|---|---|---|---|---:|---:|---:|---:|---:|")
        for row in strong.head(30).itertuples(index=False):
            lines.append(
                f"| {row.type_slug} | `{row.permission_a}` | `{row.permission_b}` | "
                f"`{row.permission_a_lane}`/`{row.permission_b_lane}` | `{row.lane_pair_class}` | "
                f"{float(row.sample_weighted_prevalence_pct):.1f} | "
                f"{float(row.family_balanced_prevalence_pct):.1f} | "
                f"{int(row.families_with_pair)} | "
                f"{float(row.odds_ratio_type_vs_rest):.2f} | {float(row.q_value_fdr):.3g} |"
            )
    lines.append("")
    lines.append("## Headline pairs (`family_balanced_supported`, all strengths)")
    lines.append("")
    if headline.empty:
        lines.append("No pairs reached `family_balanced_supported` under current gates.")
    else:
        lines.append(
            "| type | permission_a | permission_b | strength | lanes | SW% | FB% | families | OR | q |"
        )
        lines.append("|---|---|---|---|---|---:|---:|---:|---:|---:|")
        for row in headline.head(40).itertuples(index=False):
            strength = getattr(row, "headline_strength", "")
            lines.append(
                f"| {row.type_slug} | `{row.permission_a}` | `{row.permission_b}` | "
                f"`{strength}` | `{row.permission_a_lane}`/`{row.permission_b_lane}` | "
                f"{float(row.sample_weighted_prevalence_pct):.1f} | "
                f"{float(row.family_balanced_prevalence_pct):.1f} | "
                f"{int(row.families_with_pair)} | "
                f"{float(row.odds_ratio_type_vs_rest):.2f} | {float(row.q_value_fdr):.3g} |"
            )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- Declared permissions only; not runtime behavior.")
    lines.append("- Prefer `strong` / `moderate` headline tiers for research claims; keep `marginal` visible.")
    lines.append("- App-defined identity tokens are excluded from the default headline lane.")
    lines.append("- Backdoor/dropper/thin types are labeled exploratory or suppressed, not headline.")
    lines.append(
        "- `unknown_unresolved` pairs are labeled `protection_level_unresolved` "
        "(signature/privileged cannot be confirmed offline)."
    )
    lines.append("- Single-family-dominated pairs remain visible with that explicit status.")
    lines.append("- Full pair tables are run-scoped CSVs (not for Git).")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "PAIRWISE_COMPOSER_VERSION",
    "PAIRWISE_SCHEMA_VERSION",
    "classify_pair_reportability",
    "compose_type_permission_pairwise_report",
    "compute_type_pairwise_table",
    "load_vocab_table",
    "resolve_pairwise_inputs",
]
