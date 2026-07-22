"""Offline temporal permission / capability trend reports.

Consumes completed-run artifacts only. Uses the observation-date temporal
contract. Does not claim causal relationships with Android platform changes.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from obsidiandroid.common.csv_io import write_csv
from obsidiandroid.reporting.package_balanced_permission_analysis import (
    assign_package_keys,
    family_balanced_prevalence,
    package_balanced_prevalence,
    sample_weighted_prevalence,
)
from obsidiandroid.reporting.permission_capability_categories import (
    CANONICAL_CAPABILITY_CATEGORIES,
    build_sample_category_matrix,
    normalize_permission_token,
)
from obsidiandroid.reporting.permission_governance_lanes import (
    CANONICAL_PROTECTION_LANES,
    classify_protection_lane,
)
from obsidiandroid.reporting.temporal_observation_contract import (
    attach_temporal_observations,
    temporal_observation_contract_metadata,
)
from obsidiandroid.reporting.type_permission_pattern_report import resolve_git_commit, sha256_file
from obsidiandroid.reporting.type_permission_protection import EXPECTED_RUN_ID, verify_completed_run

TEMPORAL_TRENDS_COMPOSER_VERSION = "1.0.0"
DEFAULT_MIN_YEAR_SUPPORT = 30
DEFAULT_PLATFORM_EVENTS_PATH = Path("config/research/android_platform_event_annotations_v1.json")


def load_platform_event_annotations(path: Path | None = None) -> pd.DataFrame:
    """Load optional descriptive platform-event markers (non-causal)."""
    candidate = Path(path) if path else DEFAULT_PLATFORM_EVENTS_PATH
    if not candidate.is_file():
        return pd.DataFrame(
            columns=["event_id", "year", "label", "description", "annotation_only", "causal_claim_permitted"]
        )
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    events = payload.get("events", [])
    frame = pd.DataFrame(events)
    if not frame.empty:
        frame["annotation_only"] = True
        frame["causal_claim_permitted"] = False
    return frame


def _load_labels(run_root: Path, run_id: str) -> pd.DataFrame:
    return pd.read_csv(run_root / "diagnostics" / f"aligned_labels_{run_id}.csv")


def _load_permission_long(run_root: Path, run_id: str) -> pd.DataFrame:
    path = run_root / "diagnostics" / f"ml_sample_permission_feature_{run_id}.csv"
    frame = pd.read_csv(path)
    frame["permission_name"] = frame["permission_name"].map(normalize_permission_token)
    frame["permission_present"] = pd.to_numeric(frame["permission_present"], errors="coerce").fillna(0).astype(int)
    return frame[frame["permission_present"] > 0].copy()


def _load_audit(run_root: Path) -> pd.DataFrame:
    path = run_root / "diagnostics" / "permission_feature_audit.csv"
    if not path.is_file():
        return pd.DataFrame()
    audit = pd.read_csv(path)
    if "permission_string" in audit.columns:
        audit = audit.copy()
        audit["permission_name"] = audit["permission_string"].map(normalize_permission_token)
    return audit


def build_yearly_counts(temporal_labels: pd.DataFrame, *, group_col: str, min_support: int) -> pd.DataFrame:
    """Yearly sample counts by type or family with support suppression."""
    eligible = temporal_labels[temporal_labels["temporal_eligibility_status"] == "eligible"].copy()
    rows: list[dict[str, Any]] = []
    if eligible.empty:
        return pd.DataFrame(
            columns=[group_col, "observation_year", "sample_count", "support_suppressed", "suppression_reason"]
        )
    for (group_value, year), part in eligible.groupby([group_col, "observation_year"], dropna=False):
        n = len(part)
        suppressed = n < min_support
        rows.append(
            {
                group_col: group_value,
                "observation_year": int(year) if pd.notna(year) else pd.NA,
                "sample_count": n,
                "support_suppressed": suppressed,
                "suppression_reason": f"n<{min_support}" if suppressed else "",
                "date_semantics": "observation_date_not_apk_creation",
            }
        )
    return pd.DataFrame(rows).sort_values(["observation_year", group_col]).reset_index(drop=True)


def build_yearly_capability_prevalence(
    temporal_matrix: pd.DataFrame,
    *,
    min_support: int,
    weighting: str = "sample_weighted",
) -> pd.DataFrame:
    """Yearly capability prevalence with configurable weighting and suppression."""
    eligible = temporal_matrix[temporal_matrix["temporal_eligibility_status"] == "eligible"].copy()
    rows: list[dict[str, Any]] = []
    for year, part in eligible.groupby("observation_year", dropna=False):
        n = len(part)
        suppressed = n < min_support
        for cat in CANONICAL_CAPABILITY_CATEGORIES:
            if suppressed:
                prev = float("nan")
            elif weighting == "family_balanced":
                prev = family_balanced_prevalence(part, cat)
            elif weighting == "package_balanced":
                prev = package_balanced_prevalence(part, cat)
            else:
                prev = sample_weighted_prevalence(part, cat)
            rows.append(
                {
                    "observation_year": int(year) if pd.notna(year) else pd.NA,
                    "capability_category": cat,
                    "sample_count": n,
                    "positive_sample_count": int(part[cat].sum()) if not suppressed else 0,
                    "prevalence": prev,
                    "weighting": weighting,
                    "support_suppressed": suppressed,
                    "suppression_reason": f"n<{min_support}" if suppressed else "",
                    "date_semantics": "observation_date_not_apk_creation",
                }
            )
    return pd.DataFrame(rows)


def build_yearly_protection_lane_prevalence(
    temporal_labels: pd.DataFrame,
    permission_long: pd.DataFrame,
    audit: pd.DataFrame,
    *,
    min_support: int,
) -> pd.DataFrame:
    """Yearly share of samples with ≥1 permission in each protection lane."""
    pi = {}
    danger = {}
    if not audit.empty and "permission_name" in audit.columns:
        for row in audit.itertuples(index=False):
            token = getattr(row, "permission_name", "")
            if token:
                pi[str(token)] = str(getattr(row, "pi_bucket_source", "") or "")
                danger[str(token)] = str(getattr(row, "dangerous_bucket", "") or "")

    perm = permission_long.copy()
    perm["protection_lane"] = [
        classify_protection_lane(
            pi_bucket_source=pi.get(p, ""),
            dangerous_bucket=danger.get(p, ""),
            permission_string=p,
        )
        for p in perm["permission_name"]
    ]
    sample_lanes = (
        perm.groupby(["sample_id", "protection_lane"], as_index=False)
        .size()
        .assign(flag=1)
        .pivot_table(index="sample_id", columns="protection_lane", values="flag", aggfunc="max", fill_value=0)
        .reset_index()
    )
    merged = temporal_labels.merge(sample_lanes, on="sample_id", how="left")
    for lane in CANONICAL_PROTECTION_LANES:
        if lane not in merged.columns:
            merged[lane] = 0
        merged[lane] = pd.to_numeric(merged[lane], errors="coerce").fillna(0).astype(int)

    eligible = merged[merged["temporal_eligibility_status"] == "eligible"]
    rows: list[dict[str, Any]] = []
    for year, part in eligible.groupby("observation_year", dropna=False):
        n = len(part)
        suppressed = n < min_support
        for lane in CANONICAL_PROTECTION_LANES:
            prev = float(part[lane].mean()) if not suppressed else float("nan")
            rows.append(
                {
                    "observation_year": int(year) if pd.notna(year) else pd.NA,
                    "protection_lane": lane,
                    "sample_count": n,
                    "positive_sample_count": int(part[lane].sum()) if not suppressed else 0,
                    "sample_weighted_prevalence": prev,
                    "support_suppressed": suppressed,
                    "suppression_reason": f"n<{min_support}" if suppressed else "",
                    "date_semantics": "observation_date_not_apk_creation",
                }
            )
    return pd.DataFrame(rows)


def build_first_observed_capability_year(temporal_matrix: pd.DataFrame) -> pd.DataFrame:
    """Earliest observation year where a capability is present (eligible samples)."""
    eligible = temporal_matrix[
        (temporal_matrix["temporal_eligibility_status"] == "eligible")
    ].copy()
    rows = []
    for cat in CANONICAL_CAPABILITY_CATEGORIES:
        hit = eligible[eligible[cat] > 0]
        if hit.empty:
            rows.append(
                {
                    "capability_category": cat,
                    "first_observed_year": pd.NA,
                    "first_observed_sample_count_in_year": 0,
                    "date_semantics": "observation_date_not_apk_creation",
                }
            )
            continue
        year = int(hit["observation_year"].min())
        n = int((hit["observation_year"] == year).sum())
        rows.append(
            {
                "capability_category": cat,
                "first_observed_year": year,
                "first_observed_sample_count_in_year": n,
                "date_semantics": "observation_date_not_apk_creation",
            }
        )
    return pd.DataFrame(rows)


def build_timestamp_source_coverage(temporal_labels: pd.DataFrame) -> pd.DataFrame:
    """Coverage of selected date sources by year and type."""
    rows = []
    for (year, type_slug, source), part in temporal_labels.groupby(
        ["observation_year", "type_slug", "selected_date_source"], dropna=False
    ):
        rows.append(
            {
                "observation_year": year if pd.notna(year) else pd.NA,
                "type_slug": type_slug,
                "selected_date_source": source,
                "sample_count": len(part),
                "source_confidence": part["source_confidence"].iloc[0] if len(part) else "",
            }
        )
    return pd.DataFrame(rows)


def build_missing_date_rates(temporal_labels: pd.DataFrame) -> pd.DataFrame:
    """Missingness summary for temporal fields."""
    n = len(temporal_labels)
    cols = [
        "missing_first_seen_in_the_wild",
        "missing_first_discovered",
        "missing_first_analyzed_or_submission",
        "missing_collection_timestamp",
        "missing_selected_temporal_date",
    ]
    rows = []
    for col in cols:
        if col not in temporal_labels.columns:
            continue
        miss = int(temporal_labels[col].astype(bool).sum())
        rows.append({"metric": col, "missing_count": miss, "missing_rate": miss / n if n else float("nan"), "denominator": n})
    eligible = int((temporal_labels["temporal_eligibility_status"] == "eligible").sum())
    rows.append(
        {
            "metric": "temporal_eligible_samples",
            "missing_count": n - eligible,
            "missing_rate": (n - eligible) / n if n else float("nan"),
            "denominator": n,
        }
    )
    return pd.DataFrame(rows)


def build_concentration(temporal_labels: pd.DataFrame, *, group_col: str, min_support: int) -> pd.DataFrame:
    """Share of each group within a year (concentration)."""
    eligible = temporal_labels[temporal_labels["temporal_eligibility_status"] == "eligible"]
    rows = []
    for year, year_part in eligible.groupby("observation_year", dropna=False):
        year_n = len(year_part)
        suppressed_year = year_n < min_support
        for group_value, part in year_part.groupby(group_col, dropna=False):
            n = len(part)
            rows.append(
                {
                    "observation_year": int(year) if pd.notna(year) else pd.NA,
                    group_col: group_value,
                    "sample_count": n,
                    "year_sample_count": year_n,
                    "share_of_year": (n / year_n) if year_n and not suppressed_year else float("nan"),
                    "support_suppressed": suppressed_year or n < min_support,
                    "suppression_reason": (
                        f"year_n<{min_support}" if suppressed_year else (f"n<{min_support}" if n < min_support else "")
                    ),
                }
            )
    return pd.DataFrame(rows)


def _plot_lines(
    frame: pd.DataFrame,
    *,
    x: str,
    y: str,
    series: str,
    out_path: Path,
    title: str,
    run_id: str,
    weighting: str,
    denominator_note: str,
) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except ImportError:
        return
    work = frame[~frame.get("support_suppressed", False)].copy() if "support_suppressed" in frame.columns else frame.copy()
    if work.empty:
        return
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for key, part in work.groupby(series):
        part = part.sort_values(x)
        ax.plot(part[x], part[y], marker="o", label=str(key), linewidth=1.5)
    ax.set_xlabel(x)
    ax.set_ylabel(y)
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=7, ncol=2, loc="best")
    fig.text(
        0.01,
        0.01,
        f"run={run_id}; weighting={weighting}; {denominator_note}; "
        "observation-date framework (not APK creation); no causal Android-update claims",
        fontsize=7,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, bbox_inches="tight", dpi=140)
    plt.close(fig)


def compose_temporal_permission_trends(
    *,
    run_root: Path,
    run_id: str = EXPECTED_RUN_ID,
    output_dir: Path | None = None,
    repo_root: Path | None = None,
    min_support: int = DEFAULT_MIN_YEAR_SUPPORT,
    platform_events_path: Path | None = None,
) -> dict[str, Any]:
    """Compose offline temporal trend reports from a completed run."""
    run_root = Path(run_root).resolve()
    verify_completed_run(run_root, expected_run_id=run_id)
    out_dir = Path(output_dir) if output_dir else run_root / "diagnostics" / "temporal_permission_trends"
    out_dir.mkdir(parents=True, exist_ok=True)
    repo = Path(repo_root) if repo_root else Path(__file__).resolve().parents[3]

    labels = _load_labels(run_root, run_id)
    temporal_labels = attach_temporal_observations(labels)
    permission_long = _load_permission_long(run_root, run_id)
    audit = _load_audit(run_root)
    sample_matrix = build_sample_category_matrix(labels, permission_long)
    temporal_matrix = sample_matrix.merge(
        temporal_labels[
            [
                "sample_id",
                "selected_temporal_date",
                "selected_date_source",
                "source_confidence",
                "observation_year",
                "temporal_eligibility_status",
                "missing_first_seen_in_the_wild",
                "missing_first_discovered",
                "missing_first_analyzed_or_submission",
                "missing_selected_temporal_date",
            ]
        ],
        on="sample_id",
        how="left",
    )
    temporal_matrix = assign_package_keys(temporal_matrix)

    yearly_type = build_yearly_counts(temporal_labels, group_col="type_slug", min_support=min_support)
    yearly_family = build_yearly_counts(temporal_labels, group_col="family_canonical", min_support=min_support)
    cap_sw = build_yearly_capability_prevalence(temporal_matrix, min_support=min_support, weighting="sample_weighted")
    cap_fb = build_yearly_capability_prevalence(temporal_matrix, min_support=min_support, weighting="family_balanced")
    cap_pb = build_yearly_capability_prevalence(temporal_matrix, min_support=min_support, weighting="package_balanced")
    lane_year = build_yearly_protection_lane_prevalence(
        temporal_labels, permission_long, audit, min_support=min_support
    )
    first_year = build_first_observed_capability_year(temporal_matrix)
    source_cov = build_timestamp_source_coverage(temporal_labels)
    missing = build_missing_date_rates(temporal_labels)
    type_conc = build_concentration(temporal_labels, group_col="type_slug", min_support=min_support)
    family_conc = build_concentration(temporal_labels, group_col="family_canonical", min_support=min_support)
    events = load_platform_event_annotations(
        (repo / platform_events_path) if platform_events_path and not Path(platform_events_path).is_absolute() else platform_events_path
    )
    if events.empty:
        events = load_platform_event_annotations(repo / DEFAULT_PLATFORM_EVENTS_PATH)

    # Sample-level temporal export (selected fields + originals already attached)
    export_cols = [
        c
        for c in temporal_labels.columns
        if c.startswith("original__")
        or c
        in {
            "sample_id",
            "type_slug",
            "family_canonical",
            "selected_temporal_date",
            "selected_date_source",
            "selected_date_source_field",
            "source_confidence",
            "observation_year",
            "temporal_eligibility_status",
            "missing_first_seen_in_the_wild",
            "missing_first_discovered",
            "missing_first_analyzed_or_submission",
            "missing_collection_timestamp",
            "missing_selected_temporal_date",
            "apk_creation_dating",
        }
    ]
    write_csv(out_dir / "sample_temporal_observations.csv", temporal_labels[export_cols])
    write_csv(out_dir / "yearly_sample_counts_by_type.csv", yearly_type)
    write_csv(out_dir / "yearly_sample_counts_by_family.csv", yearly_family)
    write_csv(out_dir / "yearly_capability_prevalence_sample_weighted.csv", cap_sw)
    write_csv(out_dir / "yearly_capability_prevalence_family_balanced.csv", cap_fb)
    write_csv(out_dir / "yearly_capability_prevalence_package_balanced.csv", cap_pb)
    write_csv(out_dir / "yearly_protection_lane_prevalence.csv", lane_year)
    write_csv(out_dir / "first_observed_year_for_capabilities.csv", first_year)
    write_csv(out_dir / "timestamp_source_coverage_by_year_type.csv", source_cov)
    write_csv(out_dir / "missing_date_rates.csv", missing)
    write_csv(out_dir / "type_by_year_concentration.csv", type_conc)
    write_csv(out_dir / "family_by_year_concentration.csv", family_conc)
    write_csv(out_dir / "platform_event_annotations_contextual.csv", events)

    fig_dir = out_dir / "figures"
    # Yearly type composition shares
    type_share = type_conc[~type_conc["support_suppressed"]].copy()
    if not type_share.empty:
        _plot_lines(
            type_share,
            x="observation_year",
            y="share_of_year",
            series="type_slug",
            out_path=fig_dir / "yearly_type_composition.png",
            title="Yearly type composition (share of year)",
            run_id=run_id,
            weighting="share_of_year",
            denominator_note=f"min_support={min_support}",
        )
    focus_caps = ["sms_mms", "accessibility", "overlay_screen", "phone_call_log", "wifi_network"]
    cap_focus = cap_sw[cap_sw["capability_category"].isin(focus_caps)]
    _plot_lines(
        cap_focus,
        x="observation_year",
        y="prevalence",
        series="capability_category",
        out_path=fig_dir / "yearly_capability_prevalence.png",
        title="Yearly capability prevalence (sample-weighted)",
        run_id=run_id,
        weighting="sample_weighted",
        denominator_note=f"min_support={min_support}",
    )
    dangerous = lane_year[lane_year["protection_lane"].isin(["aosp_dangerous", "aosp_signature", "aosp_signature_privileged"])]
    _plot_lines(
        dangerous,
        x="observation_year",
        y="sample_weighted_prevalence",
        series="protection_lane",
        out_path=fig_dir / "yearly_dangerous_signature_prevalence.png",
        title="Yearly dangerous/signature lane prevalence",
        run_id=run_id,
        weighting="sample_weighted",
        denominator_note=f"min_support={min_support}",
    )
    # Banker / RAT capability trends
    for type_slug in ("banker", "rat"):
        part = temporal_matrix[
            (temporal_matrix["type_slug"] == type_slug)
            & (temporal_matrix["temporal_eligibility_status"] == "eligible")
        ]
        rows = []
        for year, year_part in part.groupby("observation_year", dropna=False):
            n = len(year_part)
            suppressed = n < min_support
            for cat in focus_caps:
                rows.append(
                    {
                        "observation_year": int(year) if pd.notna(year) else pd.NA,
                        "capability_category": cat,
                        "prevalence": float(year_part[cat].mean()) if not suppressed else float("nan"),
                        "sample_count": n,
                        "support_suppressed": suppressed,
                    }
                )
        trend = pd.DataFrame(rows)
        write_csv(out_dir / f"yearly_{type_slug}_capability_trends.csv", trend)
        _plot_lines(
            trend,
            x="observation_year",
            y="prevalence",
            series="capability_category",
            out_path=fig_dir / f"yearly_{type_slug}_capability_trends.png",
            title=f"{type_slug} yearly capability trends",
            run_id=run_id,
            weighting="sample_weighted_within_type",
            denominator_note=f"type={type_slug}; min_support={min_support}",
        )

    # Family-balanced vs sample-weighted comparison for focus caps
    cmp_rows = []
    for _, sw_row in cap_sw.iterrows():
        fb_match = cap_fb[
            (cap_fb["observation_year"] == sw_row["observation_year"])
            & (cap_fb["capability_category"] == sw_row["capability_category"])
        ]
        if fb_match.empty:
            continue
        fb_val = fb_match.iloc[0]["prevalence"]
        cmp_rows.append(
            {
                "observation_year": sw_row["observation_year"],
                "capability_category": sw_row["capability_category"],
                "sample_weighted": sw_row["prevalence"],
                "family_balanced": fb_val,
                "delta_pp": (
                    (float(fb_val) - float(sw_row["prevalence"])) * 100.0
                    if pd.notna(fb_val) and pd.notna(sw_row["prevalence"])
                    else float("nan")
                ),
                "support_suppressed": bool(sw_row["support_suppressed"]) or bool(fb_match.iloc[0]["support_suppressed"]),
            }
        )
    cmp = pd.DataFrame(cmp_rows)
    write_csv(out_dir / "yearly_family_balanced_vs_sample_weighted.csv", cmp)
    _plot_lines(
        cmp[cmp["capability_category"].isin(focus_caps)],
        x="observation_year",
        y="delta_pp",
        series="capability_category",
        out_path=fig_dir / "family_balanced_trend_delta_pp.png",
        title="Family-balanced − sample-weighted (pp)",
        run_id=run_id,
        weighting="delta_pp",
        denominator_note=f"min_support={min_support}",
    )

    # Timestamp source coverage chart
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt

        cov = source_cov.copy()
        if not cov.empty:
            pivot = cov.pivot_table(
                index="observation_year",
                columns="selected_date_source",
                values="sample_count",
                aggfunc="sum",
                fill_value=0,
            )
            fig, ax = plt.subplots(figsize=(9, 4.5))
            pivot.plot(kind="bar", stacked=True, ax=ax)
            ax.set_title("Timestamp-source coverage by year")
            ax.set_ylabel("sample_count")
            fig.text(0.01, 0.01, f"run={run_id}; observation-date framework; not APK creation", fontsize=7)
            fig.savefig(fig_dir / "timestamp_source_coverage.png", bbox_inches="tight", dpi=140)
            plt.close(fig)
    except ImportError:
        pass

    artifact_paths = sorted(p for p in out_dir.rglob("*") if p.is_file())
    checksums = {str(p.relative_to(out_dir)): sha256_file(p) for p in artifact_paths}
    manifest = {
        **temporal_observation_contract_metadata(),
        "temporal_trends_composer_version": TEMPORAL_TRENDS_COMPOSER_VERSION,
        "run_id": run_id,
        "run_root": str(run_root),
        "output_dir": str(out_dir),
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": resolve_git_commit(repo),
        "min_support": min_support,
        "sample_count": int(len(temporal_labels)),
        "eligible_sample_count": int((temporal_labels["temporal_eligibility_status"] == "eligible").sum()),
        "platform_events_are_contextual_only": True,
        "causal_android_update_claims": False,
        "checksums": checksums,
        "disclaimer": (
            "Offline observation-date analysis only. Does not query databases or Core. "
            "Does not treat dates as APK creation time. Platform events are contextual markers only."
        ),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest["checksums"]["manifest.json"] = sha256_file(out_dir / "manifest.json")
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


__all__ = [
    "DEFAULT_MIN_YEAR_SUPPORT",
    "TEMPORAL_TRENDS_COMPOSER_VERSION",
    "compose_temporal_permission_trends",
    "load_platform_event_annotations",
]
