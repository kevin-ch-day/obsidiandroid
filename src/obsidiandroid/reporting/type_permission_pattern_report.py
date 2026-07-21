"""Compose a malware-type permission-pattern report from an existing run bundle.

This is a read-only post-hoc composer. It does not query production databases.
It reuses ``bundles/permission_trends`` tables (and the analysis snapshot when
present) to answer type-level prevalence, lift, capability-bundle, similarity,
and family-balance questions on the live corpus.

Generated outputs are run-scoped under ``output/`` and must not be committed.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

COMPOSER_VERSION = "1.0.0"
REPORT_SCHEMA_VERSION = "type_permission_pattern_report_v1"

# Types that can enter the headline comparison when support gates pass.
_MAIN_COMPARISON_CANDIDATES = frozenset(
    {
        "banker",
        "rat",
        "spyware",
        "adware",
        "backdoor",
        "dropper",
        "sms-trojan",
        "trojan",
        "stealer",
    }
)


def _require_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"required permission-trends table missing: {path}")
    return pd.read_csv(path)


def _table(run_root: Path, stem: str, run_id: str) -> Path:
    return run_root / "bundles" / "permission_trends" / "tables" / f"{stem}_{run_id}.csv"


def sha256_file(path: Path) -> str:
    """Return lowercase hex SHA-256 of a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_git_commit(repo_root: Path | None = None) -> str:
    """Best-effort repository HEAD commit (empty string if unavailable)."""
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[3]
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    return str(completed.stdout or "").strip()


def detect_source_run_status(run_root: Path) -> dict[str, Any]:
    """Classify whether the source run is still active or completed."""
    run_root = Path(run_root)
    running_path = run_root / ".RUNNING"
    manifest_path = run_root / "run_manifest.json"
    manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                manifest = payload
        except (OSError, json.JSONDecodeError):
            manifest = {}
    running_meta: dict[str, Any] = {}
    if running_path.is_file():
        try:
            payload = json.loads(running_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                running_meta = payload
        except (OSError, json.JSONDecodeError):
            running_meta = {"raw": running_path.read_text(encoding="utf-8", errors="replace")[:500]}
    if running_path.is_file():
        report_status = "PROVISIONAL"
        source_status = "RUNNING"
    else:
        run_status = str(manifest.get("run_status") or manifest.get("status") or "").strip().lower()
        if run_status in {"complete", "completed"}:
            report_status = "FINAL_FROM_COMPLETED_RUN"
            source_status = "COMPLETE"
        elif run_status:
            report_status = "PROVISIONAL"
            source_status = run_status.upper()
        else:
            report_status = "PROVISIONAL"
            source_status = "UNKNOWN"
    return {
        "report_status": report_status,
        "source_run_status": source_status,
        "running_marker_present": running_path.is_file(),
        "running_meta": running_meta,
        "manifest_run_status": str(manifest.get("run_status") or manifest.get("status") or ""),
        "manifest_completed_stage": str(manifest.get("completed_stage") or ""),
    }


def resolve_type_permission_inputs(run_root: Path, run_id: str) -> dict[str, Path]:
    """Return paths for the tables this composer consumes."""
    required = {
        "coverage": "permission_coverage_report",
        "prevalence_by_type": "permission_prevalence_by_type",
        "type_enrichment": "permission_type_enrichment",
        "capability_bundles": "type_capability_bundle_prevalence",
        "type_similarity": "type_permission_similarity",
        "family_support": "family_support_distribution",
        "prevalence_by_family": "permission_prevalence_by_family",
        "dangerous_by_type": "dangerous_distribution_by_type",
    }
    optional = {
        "type_prevalence_long": "type_permission_prevalence",
        "signal_by_type": "permission_signal_prevalence_by_type",
    }
    paths = {key: _table(run_root, stem, run_id) for key, stem in required.items()}
    for key, stem in optional.items():
        path = _table(run_root, stem, run_id)
        if path.is_file():
            paths[key] = path
    snapshot = run_root / "diagnostics" / f"analysis_snapshot_{run_id}.csv"
    if snapshot.is_file():
        paths["analysis_snapshot"] = snapshot
    return paths


def _blank_family_mask(series: pd.Series) -> pd.Series:
    text = series.fillna("").astype(str).str.strip()
    return text.eq("") | text.str.lower().isin({"nan", "none", "null", "(null)"})


def classify_type_inclusion(
    *,
    type_slug: str,
    sample_count: int,
    active_families: int,
    largest_family_share: float,
    mapped_family_samples: int,
    min_main_samples: int = 100,
    min_main_families: int = 5,
    max_dominance_for_main: float = 0.85,
) -> tuple[bool, str]:
    """Return (included_in_main_comparison, reason)."""
    slug = str(type_slug or "").strip().lower()
    if slug in {"", "(null)", "unknown"}:
        return False, "unknown_or_unresolved_type"
    if sample_count <= 0:
        return False, "zero_samples"
    if slug not in _MAIN_COMPARISON_CANDIDATES:
        return False, "outside_main_comparison_candidate_set"
    if sample_count < int(min_main_samples):
        return False, "insufficient_sample_support"
    if active_families < int(min_main_families):
        return False, "insufficient_family_support"
    if float(largest_family_share) >= float(max_dominance_for_main):
        return False, "single_family_dominated"
    if mapped_family_samples < int(min_main_samples) * 0.5:
        return False, "high_unmapped_family_share"
    return True, "included_in_main_comparison"


def build_complete_type_inventory(
    *,
    analysis_snapshot: pd.DataFrame,
    family_support: pd.DataFrame,
    prevalence_by_type: pd.DataFrame,
    prepared_sample_count: int | None = None,
    min_main_samples: int = 100,
    min_main_families: int = 5,
    max_dominance_for_main: float = 0.85,
) -> pd.DataFrame:
    """Full type inventory with reconciliation fields for every prepared sample."""
    snap = analysis_snapshot.copy()
    if "sample_id" not in snap.columns:
        raise ValueError("analysis_snapshot requires sample_id")
    snap["type_slug"] = snap["type_slug"].fillna("(null)").astype(str)
    if "family_canonical" not in snap.columns:
        snap["family_canonical"] = ""
    snap["family_blank"] = _blank_family_mask(snap["family_canonical"])

    type_rows: list[dict[str, Any]] = []
    for type_slug, group in snap.groupby("type_slug", dropna=False):
        samples = int(group["sample_id"].nunique())
        mapped = int(group.loc[~group["family_blank"], "sample_id"].nunique())
        unmapped = samples - mapped
        families = int(group.loc[~group["family_blank"], "family_canonical"].nunique())
        if families:
            fam_counts = group.loc[~group["family_blank"]].groupby("family_canonical")["sample_id"].nunique()
            largest = int(fam_counts.max())
            median = float(fam_counts.median())
            largest_name = str(fam_counts.sort_values(ascending=False).index[0])
            largest_share = (largest / samples) if samples else 0.0
        else:
            largest = 0
            median = 0.0
            largest_name = ""
            largest_share = 0.0
        included, reason = classify_type_inclusion(
            type_slug=str(type_slug),
            sample_count=samples,
            active_families=families,
            largest_family_share=largest_share,
            mapped_family_samples=mapped,
            min_main_samples=min_main_samples,
            min_main_families=min_main_families,
            max_dominance_for_main=max_dominance_for_main,
        )
        type_rows.append(
            {
                "type_slug": type_slug,
                "sample_count": samples,
                "mapped_family_samples": mapped,
                "unmapped_family_samples": unmapped,
                "active_families": families,
                "median_samples_per_family": median,
                "largest_family_samples": largest,
                "largest_family_share": largest_share,
                "largest_family_canonical": largest_name,
                "included_in_main_comparison": bool(included),
                "suppression_or_inclusion_reason": reason,
            }
        )
    inventory = pd.DataFrame(type_rows)

    # Permission-bearing counts from prevalence n_samples (type partition).
    prev = prevalence_by_type.copy()
    prev["n_samples"] = pd.to_numeric(prev["n_samples"], errors="coerce").fillna(0)
    perm_n = prev.groupby("type_slug", as_index=False)["n_samples"].max().rename(
        columns={"n_samples": "permission_table_n_samples"}
    )
    inventory = inventory.merge(perm_n, how="left", on="type_slug")
    inventory["permission_table_n_samples"] = (
        inventory["permission_table_n_samples"].fillna(inventory["sample_count"]).astype(int)
    )

    # Family-support keyed counts (excludes blank-family samples).
    fs = family_support.copy()
    fs["type_slug"] = fs["type_slug"].fillna("(null)").astype(str)
    fs["sample_count"] = pd.to_numeric(fs["sample_count"], errors="coerce").fillna(0).astype(int)
    fs_sum = (
        fs.groupby("type_slug", as_index=False)
        .agg(
            family_support_sample_count=("sample_count", "sum"),
            family_support_family_count=("family_canonical", "nunique"),
        )
    )
    inventory = inventory.merge(fs_sum, how="left", on="type_slug")
    inventory["family_support_sample_count"] = inventory["family_support_sample_count"].fillna(0).astype(int)
    inventory["family_support_family_count"] = inventory["family_support_family_count"].fillna(0).astype(int)

    inventory = inventory.sort_values("sample_count", ascending=False).reset_index(drop=True)
    total = int(inventory["sample_count"].sum())
    expected = int(prepared_sample_count) if prepared_sample_count is not None else total
    inventory.attrs["reconciliation"] = {
        "prepared_sample_count": expected,
        "inventory_sample_sum": total,
        "reconciles": total == expected,
        "delta": total - expected,
        "main_comparison_sample_sum": int(
            inventory.loc[inventory["included_in_main_comparison"], "sample_count"].sum()
        ),
        "suppressed_sample_sum": int(
            inventory.loc[~inventory["included_in_main_comparison"], "sample_count"].sum()
        ),
    }
    return inventory


def build_type_census(
    family_support: pd.DataFrame,
    *,
    analysis_snapshot: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Legacy family-support census; prefer ``build_complete_type_inventory``."""
    frame = family_support.copy()
    frame["type_slug"] = frame["type_slug"].fillna("(null)").astype(str)
    frame["sample_count"] = pd.to_numeric(frame["sample_count"], errors="coerce").fillna(0).astype(int)
    rows: list[dict[str, Any]] = []
    for type_slug, group in frame.groupby("type_slug", dropna=False):
        samples = int(group["sample_count"].sum())
        families = int(group.shape[0])
        largest = int(group["sample_count"].max()) if samples else 0
        median = float(group["sample_count"].median()) if families else 0.0
        rows.append(
            {
                "type_slug": type_slug,
                "sample_count": samples,
                "active_families": families,
                "median_samples_per_family": median,
                "largest_family_samples": largest,
                "largest_family_share": (largest / samples) if samples else 0.0,
                "largest_family_canonical": (
                    str(group.sort_values("sample_count", ascending=False).iloc[0]["family_canonical"])
                    if families
                    else ""
                ),
            }
        )
    census = pd.DataFrame(rows).sort_values("sample_count", ascending=False).reset_index(drop=True)
    if analysis_snapshot is not None and "type_slug" in analysis_snapshot.columns:
        snap = analysis_snapshot.copy()
        snap["type_slug"] = snap["type_slug"].fillna("(null)").astype(str)
        snap_counts = (
            snap.groupby("type_slug", dropna=False)["sample_id"]
            .nunique()
            .rename("snapshot_sample_count")
        )
        census = census.merge(snap_counts, how="left", left_on="type_slug", right_index=True)
    return census


def build_overall_permission_prevalence(prevalence_by_type: pd.DataFrame) -> pd.DataFrame:
    """Corpus-wide prevalence assuming type_slug partitions the prepared cohort."""
    frame = prevalence_by_type.copy()
    frame["permission_positive_count"] = pd.to_numeric(frame["permission_positive_count"], errors="coerce").fillna(0)
    frame["n_samples"] = pd.to_numeric(frame["n_samples"], errors="coerce").fillna(0)
    type_sizes = frame.groupby("type_slug", as_index=False)["n_samples"].max()
    total_samples = float(type_sizes["n_samples"].sum())
    positives = (
        frame.groupby("permission", as_index=False)["permission_positive_count"]
        .sum()
        .rename(columns={"permission_positive_count": "positive_count"})
    )
    positives["total_samples"] = total_samples
    positives["prevalence_pct"] = (
        100.0 * positives["positive_count"] / total_samples if total_samples else 0.0
    )
    return positives.sort_values("prevalence_pct", ascending=False).reset_index(drop=True)


def classify_permission_role(
    *,
    overall_prevalence_pct: float,
    type_prevalence_pct: float,
    non_type_prevalence_pct: float,
    odds_ratio: float | None,
    high_prevalence_pct: float = 70.0,
    enrichment_odds: float = 2.0,
    strong_enrichment_odds: float = 5.0,
) -> str:
    """Bucket permissions into descriptive discrimination roles."""
    overall = float(overall_prevalence_pct)
    type_pct = float(type_prevalence_pct)
    rest = float(non_type_prevalence_pct)
    or_val = float(odds_ratio) if odds_ratio is not None and pd.notna(odds_ratio) else None
    if overall >= high_prevalence_pct and (or_val is None or or_val < enrichment_odds):
        return "high_prevalence_low_discrimination"
    if overall >= high_prevalence_pct and or_val is not None and or_val >= enrichment_odds:
        return "high_prevalence_type_enriched"
    if type_pct < 5.0 and rest < 5.0 and (or_val is None or or_val < enrichment_odds):
        return "low_prevalence_weak"
    if or_val is not None and or_val >= strong_enrichment_odds:
        return "low_prevalence_strongly_type_enriched"
    if or_val is not None and or_val >= enrichment_odds:
        return "type_enriched"
    return "descriptive_common"


def annotate_permission_roles(
    overall: pd.DataFrame,
    type_enrichment: pd.DataFrame,
) -> pd.DataFrame:
    """Join overall prevalence with enrichment and assign role labels."""
    overall_map = overall.set_index("permission")["prevalence_pct"].to_dict()
    frame = type_enrichment.copy()
    frame["overall_prevalence_pct"] = frame["permission"].map(overall_map).fillna(0.0)
    frame["odds_ratio"] = pd.to_numeric(frame["odds_ratio"], errors="coerce")
    frame["type_prevalence_pct"] = pd.to_numeric(frame["type_prevalence_pct"], errors="coerce").fillna(0.0)
    frame["non_type_prevalence_pct"] = pd.to_numeric(frame["non_type_prevalence_pct"], errors="coerce").fillna(0.0)
    frame["permission_role"] = [
        classify_permission_role(
            overall_prevalence_pct=float(row.overall_prevalence_pct),
            type_prevalence_pct=float(row.type_prevalence_pct),
            non_type_prevalence_pct=float(row.non_type_prevalence_pct),
            odds_ratio=float(row.odds_ratio) if pd.notna(row.odds_ratio) else None,
        )
        for row in frame.itertuples(index=False)
    ]
    return frame


def build_family_balanced_type_prevalence(
    prevalence_by_family: pd.DataFrame,
    *,
    min_family_support: int = 3,
) -> pd.DataFrame:
    """Equal-weight mean of family prevalences within each type (anti-dominance)."""
    frame = prevalence_by_family.copy()
    frame["family_support"] = pd.to_numeric(frame["family_support"], errors="coerce").fillna(0)
    frame["prevalence_pct"] = pd.to_numeric(frame["prevalence_pct"], errors="coerce").fillna(0.0)
    frame = frame[frame["family_support"] >= int(min_family_support)].copy()
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "type_slug",
                "permission",
                "families_used",
                "family_balanced_prevalence_pct",
                "sample_weighted_prevalence_pct",
                "max_family_prevalence_pct",
                "median_family_prevalence_pct",
                "dominance_gap_pct",
                "largest_family_canonical",
            ]
        )
    frame["weighted_positive"] = frame["prevalence_pct"] * frame["family_support"] / 100.0
    idx = frame.groupby(["type_slug", "permission"])["prevalence_pct"].idxmax()
    largest_names = frame.loc[idx, ["type_slug", "permission", "family_canonical"]].rename(
        columns={"family_canonical": "largest_family_canonical"}
    )
    grouped = frame.groupby(["type_slug", "permission"], as_index=False).agg(
        families_used=("family_canonical", "nunique"),
        family_balanced_prevalence_pct=("prevalence_pct", "mean"),
        max_family_prevalence_pct=("prevalence_pct", "max"),
        median_family_prevalence_pct=("prevalence_pct", "median"),
        support_sum=("family_support", "sum"),
        weighted_positive_sum=("weighted_positive", "sum"),
    )
    grouped["sample_weighted_prevalence_pct"] = (
        100.0 * grouped["weighted_positive_sum"] / grouped["support_sum"]
    )
    grouped["dominance_gap_pct"] = (
        grouped["max_family_prevalence_pct"] - grouped["family_balanced_prevalence_pct"]
    )
    grouped = grouped.merge(largest_names, on=["type_slug", "permission"], how="left")
    return grouped.drop(columns=["support_sum", "weighted_positive_sum"]).sort_values(
        ["type_slug", "family_balanced_prevalence_pct"],
        ascending=[True, False],
    )


def build_type_lift_leaders(type_enrichment: pd.DataFrame, *, top_n: int = 15) -> pd.DataFrame:
    """Highest-lift permissions per type (odds ratio / enrichment tables)."""
    frame = type_enrichment.copy()
    frame["odds_ratio"] = pd.to_numeric(frame["odds_ratio"], errors="coerce")
    frame["type_prevalence_pct"] = pd.to_numeric(frame["type_prevalence_pct"], errors="coerce")
    frame["non_type_prevalence_pct"] = pd.to_numeric(frame["non_type_prevalence_pct"], errors="coerce")
    frame["lift"] = frame["type_prevalence_pct"] / frame["non_type_prevalence_pct"].replace(0, pd.NA)
    frame = frame.sort_values(["type_slug", "odds_ratio", "type_prevalence_pct"], ascending=[True, False, False])
    return frame.groupby("type_slug", as_index=False).head(int(top_n)).reset_index(drop=True)


def build_banker_dropper_comparison(
    prevalence_by_type: pd.DataFrame,
    type_enrichment: pd.DataFrame,
    prevalence_by_family: pd.DataFrame,
    family_balanced: pd.DataFrame,
    *,
    top_n: int = 20,
    min_family_support: int = 3,
) -> pd.DataFrame:
    """Banker vs dropper with sample-weighted, family-balanced, and family distribution."""
    prev = prevalence_by_type[prevalence_by_type["type_slug"].isin(["banker", "dropper"])].copy()
    if prev.empty:
        return pd.DataFrame()
    pivot = prev.pivot_table(
        index="permission",
        columns="type_slug",
        values="prevalence_pct",
        aggfunc="first",
    )
    for col in ("banker", "dropper"):
        if col not in pivot.columns:
            pivot[col] = pd.NA
    pivot = pivot.rename(columns={"banker": "banker_sample_weighted_pct", "dropper": "dropper_sample_weighted_pct"})

    fb = family_balanced[family_balanced["type_slug"].isin(["banker", "dropper"])].copy()
    if not fb.empty:
        fb_pivot = fb.pivot_table(
            index="permission",
            columns="type_slug",
            values="family_balanced_prevalence_pct",
            aggfunc="first",
        )
        for col in ("banker", "dropper"):
            if col not in fb_pivot.columns:
                fb_pivot[col] = pd.NA
        pivot["banker_family_balanced_pct"] = fb_pivot["banker"]
        pivot["dropper_family_balanced_pct"] = fb_pivot["dropper"]
        med = fb.pivot_table(
            index="permission",
            columns="type_slug",
            values="median_family_prevalence_pct",
            aggfunc="first",
        )
        fam_n = fb.pivot_table(
            index="permission",
            columns="type_slug",
            values="families_used",
            aggfunc="first",
        )
        for side in ("banker", "dropper"):
            pivot[f"{side}_median_family_pct"] = med[side] if side in med.columns else pd.NA
            pivot[f"{side}_families_used"] = fam_n[side] if side in fam_n.columns else pd.NA
            largest = fb[fb["type_slug"] == side].set_index("permission")
            if "largest_family_canonical" in largest.columns:
                pivot[f"{side}_largest_family"] = largest["largest_family_canonical"]
            if "max_family_prevalence_pct" in largest.columns:
                pivot[f"{side}_max_family_pct"] = largest["max_family_prevalence_pct"]
    else:
        for col in (
            "banker_family_balanced_pct",
            "dropper_family_balanced_pct",
            "banker_median_family_pct",
            "dropper_median_family_pct",
            "banker_families_used",
            "dropper_families_used",
            "banker_largest_family",
            "dropper_largest_family",
            "banker_max_family_pct",
            "dropper_max_family_pct",
        ):
            pivot[col] = pd.NA

    # Per-family positive share for dropper (small type).
    fam = prevalence_by_family[
        (prevalence_by_family["type_slug"] == "dropper")
        & (pd.to_numeric(prevalence_by_family["family_support"], errors="coerce") >= min_family_support)
    ].copy()
    if not fam.empty:
        fam["prevalence_pct"] = pd.to_numeric(fam["prevalence_pct"], errors="coerce").fillna(0.0)
        supporting = (
            fam[fam["prevalence_pct"] > 0]
            .groupby("permission")["family_canonical"]
            .nunique()
            .rename("dropper_families_with_permission")
        )
        pivot = pivot.join(supporting, how="left")
        pivot["dropper_families_with_permission"] = pivot["dropper_families_with_permission"].fillna(0).astype(int)
    else:
        pivot["dropper_families_with_permission"] = 0

    enrich = type_enrichment[type_enrichment["type_slug"].isin(["banker", "dropper"])][
        ["permission", "type_slug", "odds_ratio", "interpretation_bucket"]
    ].copy()
    banker = enrich[enrich["type_slug"] == "banker"].set_index("permission")
    dropper = enrich[enrich["type_slug"] == "dropper"].set_index("permission")
    out = pivot.copy()
    out["banker_odds_ratio"] = banker["odds_ratio"]
    out["dropper_odds_ratio"] = dropper["odds_ratio"]
    out["banker_bucket"] = banker["interpretation_bucket"]
    out["dropper_bucket"] = dropper["interpretation_bucket"]
    out["abs_sample_weighted_gap_pct"] = (
        out["banker_sample_weighted_pct"] - out["dropper_sample_weighted_pct"]
    ).abs()
    out = out.reset_index().sort_values("abs_sample_weighted_gap_pct", ascending=False)
    return out.head(int(top_n)).reset_index(drop=True)


def compose_type_permission_pattern_report(
    *,
    run_root: Path,
    run_id: str,
    output_dir: Path | None = None,
    min_family_support: int = 3,
    lift_top_n: int = 15,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Build derived tables + markdown report under diagnostics."""
    run_root = Path(run_root)
    generated_at = datetime.now(timezone.utc).isoformat()
    run_status = detect_source_run_status(run_root)
    paths = resolve_type_permission_inputs(run_root, run_id)
    if "analysis_snapshot" not in paths:
        raise FileNotFoundError(
            f"analysis_snapshot_{run_id}.csv is required for complete type accounting"
        )

    coverage = _require_csv(paths["coverage"])
    prevalence_by_type = _require_csv(paths["prevalence_by_type"])
    type_enrichment = _require_csv(paths["type_enrichment"])
    capability_bundles = _require_csv(paths["capability_bundles"])
    type_similarity = _require_csv(paths["type_similarity"])
    family_support = _require_csv(paths["family_support"])
    prevalence_by_family = _require_csv(paths["prevalence_by_family"])
    dangerous_by_type = _require_csv(paths["dangerous_by_type"])
    snapshot = _require_csv(paths["analysis_snapshot"])

    coverage_row = coverage.iloc[0].to_dict() if not coverage.empty else {}
    prepared = int(coverage_row.get("sample_count") or len(snapshot))
    permission_bearing = int(coverage_row.get("samples_with_permission_rows") or 0)

    out_dir = Path(output_dir) if output_dir else run_root / "diagnostics" / "type_permission_pattern_report"
    out_dir.mkdir(parents=True, exist_ok=True)

    type_inventory = build_complete_type_inventory(
        analysis_snapshot=snapshot,
        family_support=family_support,
        prevalence_by_type=prevalence_by_type,
        prepared_sample_count=prepared,
    )
    reconciliation = dict(type_inventory.attrs.get("reconciliation") or {})
    type_census = type_inventory[
        [
            "type_slug",
            "sample_count",
            "active_families",
            "median_samples_per_family",
            "largest_family_samples",
            "largest_family_share",
            "largest_family_canonical",
            "included_in_main_comparison",
            "suppression_or_inclusion_reason",
        ]
    ].copy()

    overall = build_overall_permission_prevalence(prevalence_by_type)
    roles = annotate_permission_roles(overall, type_enrichment)
    family_balanced = build_family_balanced_type_prevalence(
        prevalence_by_family,
        min_family_support=min_family_support,
    )
    lift_leaders = build_type_lift_leaders(type_enrichment, top_n=lift_top_n)
    banker_dropper = build_banker_dropper_comparison(
        prevalence_by_type,
        type_enrichment,
        prevalence_by_family,
        family_balanced,
        min_family_support=min_family_support,
    )

    derived = {
        "type_inventory": type_inventory,
        "type_census": type_census,
        "overall_permission_prevalence": overall,
        "permission_role_annotations": roles,
        "family_balanced_type_prevalence": family_balanced,
        "type_lift_leaders": lift_leaders,
        "banker_dropper_comparison": banker_dropper,
    }
    output_hashes: dict[str, str] = {}
    for name, frame in derived.items():
        path = out_dir / f"{name}_{run_id}.csv"
        latest = out_dir / f"{name}.latest.csv"
        frame.to_csv(path, index=False)
        frame.to_csv(latest, index=False)
        output_hashes[path.name] = sha256_file(path)

    report_md = _render_markdown(
        run_id=run_id,
        report_status=str(run_status["report_status"]),
        source_run_status=str(run_status["source_run_status"]),
        coverage_row=coverage_row,
        type_inventory=type_inventory,
        reconciliation=reconciliation,
        overall=overall,
        roles=roles,
        lift_leaders=lift_leaders,
        capability_bundles=capability_bundles,
        type_similarity=type_similarity,
        family_balanced=family_balanced,
        banker_dropper=banker_dropper,
        dangerous_by_type=dangerous_by_type,
        min_family_support=min_family_support,
    )
    report_path = out_dir / f"type_permission_pattern_report_{run_id}.md"
    latest_path = out_dir / "type_permission_pattern_report.latest.md"
    report_path.write_text(report_md, encoding="utf-8")
    latest_path.write_text(report_md, encoding="utf-8")
    output_hashes[report_path.name] = sha256_file(report_path)

    input_hashes = {key: sha256_file(path) for key, path in paths.items()}
    git_commit = resolve_git_commit(repo_root)

    manifest: dict[str, Any] = {
        "composer_version": COMPOSER_VERSION,
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": generated_at,
        "git_commit": git_commit,
        "run_id": run_id,
        "run_root": str(run_root),
        "output_dir": str(out_dir),
        "report_status": run_status["report_status"],
        "source_run_status": run_status["source_run_status"],
        "source_run_status_detail": run_status,
        "prepared_sample_count": prepared,
        "permission_evidence_sample_count": permission_bearing,
        "complete_type_count": int(type_inventory.shape[0]),
        "type_accounting_reconciliation": reconciliation,
        "source_tables": {key: str(path) for key, path in paths.items()},
        "input_sha256": input_hashes,
        "output_sha256": output_hashes,
        "derived_tables": sorted(f"{name}_{run_id}.csv" for name in derived),
        "report_markdown": str(report_path),
        "controls": {
            "prevalence_denominator": "type-partitioned prepared cohort samples",
            "family_balanced_min_family_support": min_family_support,
            "permissions_are_declared_capabilities_not_runtime_behavior": True,
            "dropper_is_top_level_type_slug": True,
            "generated_outputs_must_not_be_committed": True,
        },
    }
    manifest_path = out_dir / f"type_permission_pattern_report_manifest_{run_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest["manifest_sha256"] = sha256_file(manifest_path)
    # Rewrite with self hash of prior content is awkward; store companion hash file instead.
    (out_dir / f"type_permission_pattern_report_manifest_{run_id}.sha256").write_text(
        manifest["manifest_sha256"] + "\n",
        encoding="utf-8",
    )
    return manifest


def _render_markdown(
    *,
    run_id: str,
    report_status: str,
    source_run_status: str,
    coverage_row: dict[str, Any],
    type_inventory: pd.DataFrame,
    reconciliation: dict[str, Any],
    overall: pd.DataFrame,
    roles: pd.DataFrame,
    lift_leaders: pd.DataFrame,
    capability_bundles: pd.DataFrame,
    type_similarity: pd.DataFrame,
    family_balanced: pd.DataFrame,
    banker_dropper: pd.DataFrame,
    dangerous_by_type: pd.DataFrame,
    min_family_support: int,
) -> str:
    lines: list[str] = []
    lines.append(f"# Malware-type permission-pattern report (`{run_id}`)")
    lines.append("")
    lines.append(f"- Report status: **{report_status}**")
    lines.append(f"- Source run status: **{source_run_status}**")
    lines.append(f"- Composer version: `{COMPOSER_VERSION}`")
    lines.append(f"- Schema: `{REPORT_SCHEMA_VERSION}`")
    if report_status == "PROVISIONAL":
        lines.append(
            "- This report is **provisional** because the source run is still active "
            "or not fully finalized. Regenerate after `.RUNNING` clears."
        )
    lines.append("")
    lines.append(
        "Live-corpus structural analysis. This report characterizes **malware types** "
        "using declared APK permissions. It is not a reproduction of the frozen "
        "publication cohort."
    )
    lines.append("")
    lines.append("## 1. Dataset and evidence coverage")
    lines.append("")
    if coverage_row:
        lines.append(
            f"- Prepared samples: **{int(coverage_row.get('sample_count', 0)):,}**"
        )
        lines.append(
            f"- Samples with permission rows: **{int(coverage_row.get('samples_with_permission_rows', 0)):,}** "
            f"({float(coverage_row.get('pct_with_permission_rows', 0)) * 100:.1f}%)"
        )
        lines.append(
            f"- Zero-permission / missing evidence: "
            f"**{int(coverage_row.get('samples_zero_permission_rows', 0)):,}**"
        )
        lines.append(
            f"- Mean unique permissions / sample: "
            f"**{float(coverage_row.get('mean_unique_permissions', 0)):.1f}**"
        )
    lines.append(
        "- Denominator for type prevalence: samples of that type in the prepared cohort "
        "(permission-trends tables)."
    )
    lines.append(
        "- Permissions are **declared capabilities** from manifests / Permission Intel, "
        "not observed runtime behavior."
    )
    lines.append("")
    lines.append("## 2. Complete type inventory and accounting")
    lines.append("")
    lines.append(
        f"Prepared samples: **{int(reconciliation.get('prepared_sample_count', 0)):,}**. "
        f"Inventory sum: **{int(reconciliation.get('inventory_sample_sum', 0)):,}**. "
        f"Reconciles: **{bool(reconciliation.get('reconciles'))}** "
        f"(delta={int(reconciliation.get('delta', 0))})."
    )
    lines.append("")
    lines.append(
        f"Main-comparison samples: **{int(reconciliation.get('main_comparison_sample_sum', 0)):,}**. "
        f"Suppressed / other / unknown: **{int(reconciliation.get('suppressed_sample_sum', 0)):,}**."
    )
    lines.append("")
    lines.append(
        "| type_slug | samples | mapped | families | largest family | share | main? | reason |"
    )
    lines.append("|---|---:|---:|---:|---|---:|---|---|")
    for row in type_inventory.itertuples(index=False):
        lines.append(
            f"| {row.type_slug} | {row.sample_count:,} | {row.mapped_family_samples:,} | "
            f"{row.active_families} | {row.largest_family_canonical} | "
            f"{100.0 * row.largest_family_share:.1f}% | "
            f"{'yes' if row.included_in_main_comparison else 'no'} | "
            f"`{row.suppression_or_inclusion_reason}` |"
        )
    lines.append("")
    lines.append(
        "`dropper` is a **top-level `type_slug`** in this taxonomy (exclusive label), "
        "not only a delivery attribute. Dual-role banker∩dropper samples are not modeled yet."
    )
    lines.append("")
    lines.append("## 3. Overall permission prevalence")
    lines.append("")
    lines.append(
        "Common permissions remain in the report even when they are weak discriminators. "
        "Roles: `high_prevalence_low_discrimination`, `high_prevalence_type_enriched`, "
        "`low_prevalence_strongly_type_enriched`."
    )
    lines.append("")
    lines.append("| permission | prevalence % | positives |")
    lines.append("|---|---:|---:|")
    for row in overall.head(20).itertuples(index=False):
        lines.append(
            f"| `{row.permission}` | {row.prevalence_pct:.1f} | {int(row.positive_count):,} |"
        )
    if not roles.empty:
        role_counts = roles["permission_role"].value_counts()
        lines.append("")
        lines.append("Role counts across type×permission enrichment rows:")
        lines.append("")
        for role, count in role_counts.items():
            lines.append(f"- `{role}`: {int(count):,}")
    lines.append("")
    lines.append("## 4. Permission prevalence by malware type")
    lines.append("")
    lines.append(
        "Full matrices live in the permission-trends bundle. Dangerous-permission intensity:"
    )
    lines.append("")
    if not dangerous_by_type.empty:
        lines.append("| type_slug | samples | strict dangerous mean | total perms median |")
        lines.append("|---|---:|---:|---:|")
        ordered = dangerous_by_type.sort_values("sample_count", ascending=False)
        for row in ordered.itertuples(index=False):
            lines.append(
                f"| {row.type_slug} | {int(row.sample_count):,} | "
                f"{float(row.dangerous_count_strict_mean):.1f} | "
                f"{float(row.total_perm_count_median):.0f} |"
            )
    lines.append("")
    lines.append("## 5. Type-specific permission lift")
    lines.append("")
    main_types = set(
        type_inventory.loc[type_inventory["included_in_main_comparison"], "type_slug"].astype(str)
    )
    for type_slug, group in lift_leaders.groupby("type_slug"):
        tag = "main" if str(type_slug) in main_types else "suppressed/exploratory"
        lines.append(f"### `{type_slug}` ({tag})")
        lines.append("")
        lines.append("| permission | type % | non-type % | odds ratio | bucket |")
        lines.append("|---|---:|---:|---:|---|")
        for row in group.head(8).itertuples(index=False):
            lines.append(
                f"| `{row.permission}` | {float(row.type_prevalence_pct):.1f} | "
                f"{float(row.non_type_prevalence_pct):.1f} | {float(row.odds_ratio):.2f} | "
                f"{row.interpretation_bucket} |"
            )
        lines.append("")
    lines.append("## 6. Permission co-occurrence bundles")
    lines.append("")
    lines.append(
        "Current bundle surface uses **predefined capability groups**, not pairwise mining."
    )
    lines.append("")
    if not capability_bundles.empty:
        top_bundles = capability_bundles.sort_values("prevalence_pct", ascending=False).head(20)
        lines.append("| type_slug | capability_bundle | prevalence % | positives / samples |")
        lines.append("|---|---|---:|---:|")
        for row in top_bundles.itertuples(index=False):
            lines.append(
                f"| {row.type_slug} | `{row.capability_bundle}` | {float(row.prevalence_pct):.1f} | "
                f"{int(row.positive_count)}/{int(row.sample_count)} |"
            )
    lines.append("")
    lines.append("## 7. Within-type family variability")
    lines.append("")
    lines.append(
        f"Family-balanced prevalence = unweighted mean of family prevalences for families "
        f"with support ≥ {min_family_support}."
    )
    lines.append("")
    if not family_balanced.empty:
        spotlight = family_balanced.sort_values("dominance_gap_pct", ascending=False).head(15)
        lines.append(
            "| type | permission | family-balanced % | sample-weighted % | "
            "dominance gap | families | largest family |"
        )
        lines.append("|---|---|---:|---:|---:|---:|---|")
        for row in spotlight.itertuples(index=False):
            largest = getattr(row, "largest_family_canonical", "")
            lines.append(
                f"| {row.type_slug} | `{row.permission}` | "
                f"{float(row.family_balanced_prevalence_pct):.1f} | "
                f"{float(row.sample_weighted_prevalence_pct):.1f} | "
                f"{float(row.dominance_gap_pct):.1f} | {int(row.families_used)} | {largest} |"
            )
    lines.append("")
    lines.append("## 8. Type-to-type permission similarity")
    lines.append("")
    if not type_similarity.empty:
        sim = type_similarity.sort_values("cosine_similarity", ascending=False).head(12)
        lines.append("| type_a | type_b | cosine | jaccard | spearman |")
        lines.append("|---|---|---:|---:|---:|")
        for row in sim.itertuples(index=False):
            lines.append(
                f"| {row.type_a} | {row.type_b} | {float(row.cosine_similarity):.3f} | "
                f"{float(row.jaccard_similarity):.3f} | {float(row.spearman_correlation):.3f} |"
            )
    lines.append("")
    lines.append("## 9. Type classification (secondary)")
    lines.append("")
    lines.append(
        "This composer does not retrain type classifiers. A mediocre type Macro-F1 is itself "
        "evidence of static-permission overlap."
    )
    lines.append("")
    lines.append("## 10. Data-quality and taxonomy limitations")
    lines.append("")
    lines.append("- Blank-family samples are counted in type inventory but absent from family-support tables.")
    lines.append("- Sample-weighted type patterns can vanish under family balance.")
    lines.append("- Backdoor/dropper/thin types remain descriptive / exploratory.")
    lines.append("- Pairwise co-occurrence mining is a separate Phase-2 composer.")
    lines.append("- Banker-vs-dropper assumes exclusive `type_slug` labels.")
    lines.append("")
    if not banker_dropper.empty:
        lines.append("### Banker vs dropper (sample-weighted + family-balanced)")
        lines.append("")
        lines.append(
            "| permission | banker SW% | dropper SW% | banker FB% | dropper FB% | "
            "dropper families w/ perm | dropper largest |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---|")
        for row in banker_dropper.head(12).itertuples(index=False):
            b_fb = getattr(row, "banker_family_balanced_pct", float("nan"))
            d_fb = getattr(row, "dropper_family_balanced_pct", float("nan"))
            d_fam = getattr(row, "dropper_families_with_permission", 0)
            d_large = getattr(row, "dropper_largest_family", "")
            lines.append(
                f"| `{row.permission}` | {float(row.banker_sample_weighted_pct):.1f} | "
                f"{float(row.dropper_sample_weighted_pct):.1f} | "
                f"{float(b_fb) if pd.notna(b_fb) else float('nan'):.1f} | "
                f"{float(d_fb) if pd.notna(d_fb) else float('nan'):.1f} | "
                f"{int(d_fam)} | {d_large} |"
            )
        lines.append("")
    lines.append("---")
    lines.append(
        "Derived CSVs accompany this markdown under "
        "`diagnostics/type_permission_pattern_report/` (run-scoped; not for Git)."
    )
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "COMPOSER_VERSION",
    "REPORT_SCHEMA_VERSION",
    "annotate_permission_roles",
    "build_banker_dropper_comparison",
    "build_complete_type_inventory",
    "build_family_balanced_type_prevalence",
    "build_overall_permission_prevalence",
    "build_type_census",
    "build_type_lift_leaders",
    "classify_permission_role",
    "classify_type_inclusion",
    "compose_type_permission_pattern_report",
    "detect_source_run_status",
    "resolve_git_commit",
    "resolve_type_permission_inputs",
    "sha256_file",
]
