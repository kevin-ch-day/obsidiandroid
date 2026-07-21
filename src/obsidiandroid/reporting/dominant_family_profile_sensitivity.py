"""Type-level dominant-family permission profile sensitivity (offline).

Leave-largest / leave-second / leave-both profile comparisons with Spearman
rank correlation and Jensen–Shannon distance. Does not access databases or
mutate run artifacts.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from obsidiandroid.pipeline.permission_trends.stats_core import js_distance

FOCUS_LANES = ("aosp_normal", "aosp_dangerous")
MIN_TYPE_SAMPLES = 50
MIN_TYPE_FAMILIES = 3
MIN_REMAINDER_SAMPLES = 30
MIN_REMAINDER_FAMILIES = 2
HEADLINE_PREV_FLOOR = 20.0


def _norm_perm(value: Any) -> str:
    return str(value or "").strip().lower()


def spearman_rank_corr(a: np.ndarray, b: np.ndarray) -> float:
    if a.size == 0 or b.size == 0 or a.size != b.size:
        return float("nan")
    if np.allclose(a, a[0]) or np.allclose(b, b[0]):
        return float("nan")
    ra = pd.Series(a).rank().to_numpy(dtype=float)
    rb = pd.Series(b).rank().to_numpy(dtype=float)
    corr = np.corrcoef(ra, rb)[0, 1]
    return float(corr) if np.isfinite(corr) else float("nan")


def _spearman_rank_corr(a: np.ndarray, b: np.ndarray) -> float:
    return spearman_rank_corr(a, b)


def _profile_vector(
    fam_prev: pd.DataFrame,
    *,
    type_slug: str,
    exclude_families: set[str] | None = None,
    mode: str = "sample_weighted",
    permissions: Sequence[str] | None = None,
) -> tuple[np.ndarray, list[str], int, int]:
    """Return (prevalence_fraction_vector, permission_list, n_samples, n_families)."""
    frame = fam_prev[fam_prev["type_slug"].astype(str) == type_slug].copy()
    if exclude_families:
        frame = frame[~frame["family_canonical"].astype(str).isin(exclude_families)]
    if frame.empty:
        return np.asarray([], dtype=float), [], 0, 0
    frame["permission"] = frame["permission"].map(_norm_perm)
    frame["family_support"] = pd.to_numeric(frame["family_support"], errors="coerce").fillna(0.0)
    frame["prevalence_pct"] = pd.to_numeric(frame["prevalence_pct"], errors="coerce").fillna(0.0)
    families = sorted(frame["family_canonical"].astype(str).unique().tolist())
    n_families = len(families)
    # sample count approx = sum of unique family supports
    support_by_fam = frame.groupby("family_canonical")["family_support"].max()
    n_samples = int(support_by_fam.sum())
    if permissions is None:
        permissions = sorted(frame["permission"].unique().tolist())
    values: list[float] = []
    for perm in permissions:
        g = frame[frame["permission"] == perm]
        if g.empty:
            values.append(0.0)
            continue
        if mode == "family_balanced":
            values.append(float(g["prevalence_pct"].mean()) / 100.0)
        else:
            supp = g["family_support"].to_numpy(dtype=float)
            prev = g["prevalence_pct"].to_numpy(dtype=float) / 100.0
            total = float(supp.sum())
            values.append(float((prev * supp).sum() / total) if total > 0 else 0.0)
    return np.asarray(values, dtype=float), list(permissions), n_samples, n_families


def classify_type_profile_robustness(
    *,
    n_families_full: int,
    n_samples_full: int,
    n_families_ex: int,
    n_samples_ex: int,
    spearman: float,
    jsd: float,
    max_abs_shift_pp: float,
    headline_lost: int,
    min_families: int = MIN_TYPE_FAMILIES,
    min_samples: int = MIN_TYPE_SAMPLES,
) -> str:
    if n_samples_full < min_samples:
        return "insufficient_sample_support"
    if n_families_full < min_families:
        return "insufficient_family_support"
    if n_samples_ex < MIN_REMAINDER_SAMPLES:
        return "insufficient_sample_support"
    if n_families_ex < MIN_REMAINDER_FAMILIES:
        return "insufficient_family_support"
    if (
        (pd.notna(spearman) and spearman < 0.55)
        or (pd.notna(jsd) and jsd >= 0.25)
        or max_abs_shift_pp >= 25.0
        or headline_lost >= 5
    ):
        return "dominant_family_driven"
    if (
        (pd.notna(spearman) and spearman < 0.85)
        or (pd.notna(jsd) and jsd >= 0.10)
        or max_abs_shift_pp >= 10.0
        or headline_lost >= 2
    ):
        return "moderately_family_sensitive"
    return "robust_across_families"


def build_dominant_family_type_robustness(
    *,
    fam_prev: pd.DataFrame,
    type_inventory: pd.DataFrame,
    role_annotations: pd.DataFrame,
    pairwise_headline: pd.DataFrame,
    lane_lookup: Mapping[str, str] | None = None,
    min_samples: int = MIN_TYPE_SAMPLES,
    min_families: int = MIN_TYPE_FAMILIES,
) -> pd.DataFrame:
    """Type-level leave-top-1 / leave-top-2 / leave-both profile sensitivity."""
    frame = fam_prev.copy()
    frame["type_slug"] = frame["type_slug"].astype(str)
    frame["family_canonical"] = frame["family_canonical"].astype(str)
    frame["permission"] = frame["permission"].map(_norm_perm)
    if lane_lookup:
        frame = frame[
            frame["permission"].map(lambda p: lane_lookup.get(p, "unknown_unresolved") in FOCUS_LANES)
        ].copy()

    inv = type_inventory.copy() if not type_inventory.empty else pd.DataFrame()
    rows: list[dict[str, Any]] = []
    for type_slug, group in frame.groupby("type_slug"):
        support = (
            group.groupby("family_canonical")["family_support"]
            .max()
            .sort_values(ascending=False)
        )
        families = support.index.astype(str).tolist()
        n_samples_full = int(support.sum())
        n_families_full = len(families)
        if n_samples_full < min_samples and n_families_full < min_families:
            rows.append(
                {
                    "type_slug": type_slug,
                    "scenario": "full",
                    "excluded_families": "",
                    "largest_family": families[0] if families else "",
                    "second_largest_family": families[1] if len(families) > 1 else "",
                    "n_samples": n_samples_full,
                    "n_families": n_families_full,
                    "spearman_vs_full_sw": "",
                    "js_distance_vs_full_sw": "",
                    "max_abs_prevalence_shift_pp": "",
                    "headline_permissions_lost": "",
                    "type_enriched_permissions_lost": "",
                    "reportable_pairs_lost": "",
                    "supporting_family_count_change": "",
                    "robustness_class": (
                        "insufficient_sample_support"
                        if n_samples_full < min_samples
                        else "insufficient_family_support"
                    ),
                }
            )
            continue

        largest = families[0] if families else ""
        second = families[1] if len(families) > 1 else ""
        sw_full, perms, _, _ = _profile_vector(group, type_slug=str(type_slug), mode="sample_weighted")
        fb_full, _, _, _ = _profile_vector(
            group, type_slug=str(type_slug), mode="family_balanced", permissions=perms
        )

        # Headline / enriched permission sets for this type from annotations.
        enriched: set[str] = set()
        if not role_annotations.empty:
            ann = role_annotations[role_annotations["type_slug"].astype(str) == type_slug]
            if "permission_role" in ann.columns:
                enriched = {
                    _norm_perm(r.permission)
                    for r in ann.itertuples(index=False)
                    if any(tok in str(getattr(r, "permission_role", "")).lower() for tok in ("enrich",))
                }
        headline_full = {
            perms[i]
            for i, v in enumerate(sw_full)
            if float(v) * 100.0 >= HEADLINE_PREV_FLOOR
        }

        pair_full = 0
        if not pairwise_headline.empty:
            ph = pairwise_headline[pairwise_headline["type_slug"].astype(str) == type_slug]
            pair_full = int(len(ph))

        scenarios = [
            ("full", set()),
            ("exclude_largest", {largest} if largest else set()),
            ("exclude_second_largest", {second} if second else set()),
            (
                "exclude_largest_and_second",
                {x for x in (largest, second) if x},
            ),
        ]
        for scenario, excluded in scenarios:
            sw, _, n_s, n_f = _profile_vector(
                group,
                type_slug=str(type_slug),
                exclude_families=excluded or None,
                mode="sample_weighted",
                permissions=perms,
            )
            fb, _, _, _ = _profile_vector(
                group,
                type_slug=str(type_slug),
                exclude_families=excluded or None,
                mode="family_balanced",
                permissions=perms,
            )
            if scenario == "full":
                rows.append(
                    {
                        "type_slug": type_slug,
                        "scenario": scenario,
                        "excluded_families": "",
                        "largest_family": largest,
                        "second_largest_family": second,
                        "n_samples": n_s,
                        "n_families": n_f,
                        "spearman_vs_full_sw": 1.0,
                        "js_distance_vs_full_sw": 0.0,
                        "max_abs_prevalence_shift_pp": 0.0,
                        "headline_permissions_lost": 0,
                        "type_enriched_permissions_lost": 0,
                        "reportable_pairs_lost": 0,
                        "supporting_family_count_change": 0,
                        "robustness_class": "reference_full_profile",
                        "family_balanced_spearman_vs_full": 1.0,
                        "family_balanced_js_distance_vs_full": 0.0,
                    }
                )
                continue

            if sw.size == 0 or n_s < MIN_REMAINDER_SAMPLES:
                rows.append(
                    {
                        "type_slug": type_slug,
                        "scenario": scenario,
                        "excluded_families": "|".join(sorted(excluded)),
                        "largest_family": largest,
                        "second_largest_family": second,
                        "n_samples": n_s,
                        "n_families": n_f,
                        "spearman_vs_full_sw": "",
                        "js_distance_vs_full_sw": "",
                        "max_abs_prevalence_shift_pp": "",
                        "headline_permissions_lost": "",
                        "type_enriched_permissions_lost": "",
                        "reportable_pairs_lost": "",
                        "supporting_family_count_change": n_f - n_families_full,
                        "robustness_class": "insufficient_sample_support",
                        "family_balanced_spearman_vs_full": "",
                        "family_balanced_js_distance_vs_full": "",
                    }
                )
                continue

            # Align lengths
            if sw.size != sw_full.size:
                # pad
                m = max(sw.size, sw_full.size)
                sw_a = np.zeros(m)
                sw_b = np.zeros(m)
                sw_a[: sw_full.size] = sw_full
                sw_b[: sw.size] = sw
            else:
                sw_a, sw_b = sw_full, sw
            spearman = _spearman_rank_corr(sw_a, sw_b)
            # JSD on normalized non-negative profiles
            p = sw_a.clip(min=0)
            q = sw_b.clip(min=0)
            if p.sum() <= 0:
                p = np.ones_like(p) / max(len(p), 1)
            else:
                p = p / p.sum()
            if q.sum() <= 0:
                q = np.ones_like(q) / max(len(q), 1)
            else:
                q = q / q.sum()
            jsd = float(js_distance(p, q))
            max_shift = float(np.max(np.abs(sw_a - sw_b)) * 100.0) if sw_a.size else 0.0
            headline_ex = {
                perms[i]
                for i, v in enumerate(sw_b)
                if i < len(perms) and float(v) * 100.0 >= HEADLINE_PREV_FLOOR
            }
            headline_lost = len(headline_full - headline_ex)
            enriched_full = {p for p in enriched if p in headline_full or p in perms}
            enriched_lost = 0
            for perm in enriched_full:
                if perm in perms:
                    idx = perms.index(perm)
                    before = float(sw_a[idx]) * 100.0 if idx < len(sw_a) else 0.0
                    after = float(sw_b[idx]) * 100.0 if idx < len(sw_b) else 0.0
                    if before >= HEADLINE_PREV_FLOOR and after < HEADLINE_PREV_FLOOR:
                        enriched_lost += 1

            # Approximate reportable pairs lost when largest family dominated them.
            pairs_lost = 0
            if not pairwise_headline.empty and excluded:
                ph = pairwise_headline[pairwise_headline["type_slug"].astype(str) == type_slug]
                if "largest_family_canonical" in ph.columns:
                    pairs_lost = int(
                        ph["largest_family_canonical"].astype(str).isin(excluded).sum()
                    )

            fb_spearman = float("nan")
            fb_jsd = float("nan")
            if fb.size and fb_full.size and fb.size == fb_full.size:
                fb_spearman = _spearman_rank_corr(fb_full, fb)
                pf = fb_full.clip(min=0)
                qf = fb.clip(min=0)
                pf = pf / pf.sum() if pf.sum() > 0 else np.ones_like(pf) / max(len(pf), 1)
                qf = qf / qf.sum() if qf.sum() > 0 else np.ones_like(qf) / max(len(qf), 1)
                fb_jsd = float(js_distance(pf, qf))

            klass = classify_type_profile_robustness(
                n_families_full=n_families_full,
                n_samples_full=n_samples_full,
                n_families_ex=n_f,
                n_samples_ex=n_s,
                spearman=spearman,
                jsd=jsd,
                max_abs_shift_pp=max_shift,
                headline_lost=headline_lost,
                min_families=min_families,
                min_samples=min_samples,
            )
            rows.append(
                {
                    "type_slug": type_slug,
                    "scenario": scenario,
                    "excluded_families": "|".join(sorted(excluded)),
                    "largest_family": largest,
                    "second_largest_family": second,
                    "n_samples": n_s,
                    "n_families": n_f,
                    "spearman_vs_full_sw": round(spearman, 6) if pd.notna(spearman) else "",
                    "js_distance_vs_full_sw": round(jsd, 6),
                    "max_abs_prevalence_shift_pp": round(max_shift, 3),
                    "headline_permissions_lost": headline_lost,
                    "type_enriched_permissions_lost": enriched_lost,
                    "reportable_pairs_lost": pairs_lost,
                    "supporting_family_count_change": n_f - n_families_full,
                    "robustness_class": klass,
                    "family_balanced_spearman_vs_full": (
                        round(fb_spearman, 6) if pd.notna(fb_spearman) else ""
                    ),
                    "family_balanced_js_distance_vs_full": (
                        round(fb_jsd, 6) if pd.notna(fb_jsd) else ""
                    ),
                }
            )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["type_slug", "scenario"]).reset_index(drop=True)

__all__ = [
    "build_dominant_family_type_robustness",
    "classify_type_profile_robustness",
    "spearman_rank_corr",
]

