"""Profile permission-trends reporting performance without mutating DB state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts._bootstrap import prepare_script_runtime  # noqa: E402

prepare_script_runtime(__file__)

import pandas as pd

from obsidiandroid.database import db_engine
from obsidiandroid.database import db_sample_metadata_fetchers
from obsidiandroid.pipeline import stage_permission_trends_report as report_stage
from obsidiandroid.pipeline.permission_trends import bundle_exports as perm_bundle_exports
from obsidiandroid.pipeline.permission_trends import sample_permission_data
from obsidiandroid.pipeline.permission_trends.bundle_io import export_df_with_latest, export_markdown_with_latest


def _timed(func, *args, **kwargs):
    start = perf_counter()
    value = func(*args, **kwargs)
    end = perf_counter()
    return value, (end - start)


def _load_cached_major_labels(run_id: str) -> pd.DataFrame:
    diagnostics = Path("output/runs") / run_id / "diagnostics"
    labels_path = diagnostics / f"aligned_labels_{run_id}.csv"
    if labels_path.exists():
        return pd.read_csv(labels_path)
    snapshot_path = diagnostics / f"analysis_snapshot_{run_id}.csv"
    if snapshot_path.exists():
        return pd.read_csv(snapshot_path)
    raise FileNotFoundError(f"No aligned labels or analysis snapshot found for run_id={run_id}")


def _load_sampled_broad_live(limit: int) -> pd.DataFrame:
    output_columns = """
                sample_id,
                sha256,
                family_id,
                family_canonical,
                type_slug,
                family_name,
                category_primary,
                category_subtype,
                sample_label_kind,
                family_label_raw,
                vt_family_token,
                source_batch_label,
                android_package_name
    """
    return db_sample_metadata_fetchers._execute_samples_by_type_query(  # pylint: disable=protected-access
        output_columns=output_columns,
        type_slug=None,
        min_samples_per_family=None,
        require_mapped_family=False,
        require_sha256=True,
        allow_missing_package_name=True,
        exclude_unknown_type_slug=False,
        exclude_weak_label_kinds=False,
        exclude_family_label_conflicts=False,
        limit=int(limit),
        as_dataframe=True,
    )


def _warm_permission_queries(sample_ids: list[int]) -> None:
    if not sample_ids:
        return
    warm_ids = sample_ids[: min(50, len(sample_ids))]
    _fetch_permission_rows_without_governed_join(warm_ids)
    sample_permission_data.fetch_permission_rows_for_samples(warm_ids)


def _fetch_permission_rows_without_governed_join(sample_ids: list[int]) -> pd.DataFrame:
    if not sample_ids:
        return pd.DataFrame(
            columns=[
                "sample_id",
                "permission_string",
                "protection_level",
                "permission_source",
                "is_aosp_dict_match",
                "is_oem_dict_match",
            ]
        )
    chunk_size = 500
    frames: list[pd.DataFrame] = []
    permission_key_expr = sample_permission_data._permission_obs_key_expr_ops()  # pylint: disable=protected-access
    for idx in range(0, len(sample_ids), chunk_size):
        chunk = sample_ids[idx : idx + chunk_size]
        placeholders = ", ".join(["%s"] * len(chunk))
        query = f"""
            SELECT
                ops.sample_id,
                ops.permission_string AS permission_string_raw,
                {permission_key_expr} AS permission_string,
                UPPER(COALESCE(a.protection_level, o.protection_level, 'UNKNOWN')) AS protection_level,
                UPPER(COALESCE(ops.classification, 'UNKNOWN')) AS permission_source,
                CASE WHEN a.constant_value IS NOT NULL THEN 1 ELSE 0 END AS is_aosp_dict_match,
                CASE WHEN o.permission_string IS NOT NULL THEN 1 ELSE 0 END AS is_oem_dict_match
            FROM android_permission_obs_sample ops
            LEFT JOIN android_permission_dict_aosp a
              ON LOWER(TRIM(ops.permission_string)) = LOWER(TRIM(a.constant_value))
            LEFT JOIN android_permission_dict_oem o
              ON LOWER(TRIM(ops.permission_string)) = LOWER(TRIM(o.permission_string))
             AND (ops.vendor_id = o.vendor_id OR o.vendor_id IS NULL)
            WHERE ops.sample_id IN ({placeholders})
              AND ops.permission_string IS NOT NULL
              AND TRIM(ops.permission_string) <> ''
        """
        frame = db_engine.execute_permission_query(
            query, params=tuple(chunk), fetch=True, as_dataframe=True
        )
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame(
            columns=[
                "sample_id",
                "permission_string",
                "protection_level",
                "permission_source",
                "is_aosp_dict_match",
                "is_oem_dict_match",
            ]
        )
    out = pd.concat(frames, ignore_index=True)
    out["sample_id"] = pd.to_numeric(out["sample_id"], errors="coerce")
    out = out.dropna(subset=["sample_id"]).copy()
    out["sample_id"] = out["sample_id"].astype(int)
    out["permission_string"] = out["permission_string"].fillna("").astype(str).str.strip().str.lower()
    out["permission_string"] = out["permission_string"].replace(sample_permission_data.PERMISSION_ALIAS_MAP)
    out["protection_level"] = out["protection_level"].fillna("UNKNOWN").astype(str).str.upper()
    out["permission_source"] = out["permission_source"].fillna("UNKNOWN").astype(str).str.upper()
    out["is_aosp_dict_match"] = pd.to_numeric(out.get("is_aosp_dict_match", 0), errors="coerce").fillna(0).astype(int)
    out["is_oem_dict_match"] = pd.to_numeric(out.get("is_oem_dict_match", 0), errors="coerce").fillna(0).astype(int)
    out = out[out["permission_string"] != ""].drop_duplicates(subset=["sample_id", "permission_string"])
    return out


def _build_governance_coverage(permission_rows_df: pd.DataFrame, permission_signal_rows_df: pd.DataFrame, run_id: str) -> pd.DataFrame:
    return report_stage._build_permission_signal_governance_coverage(  # pylint: disable=protected-access
        permission_rows_df,
        permission_signal_rows_df,
        run_id=run_id,
    )


def _profile_scenario(
    *,
    scenario_name: str,
    sample_source: str,
    samples_df: pd.DataFrame,
    run_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    sample_core_df = report_stage._build_sample_core(samples_df)  # pylint: disable=protected-access
    sample_ids = (
        pd.to_numeric(sample_core_df.get("sample_id"), errors="coerce")
        .dropna()
        .astype(int)
        .drop_duplicates()
        .tolist()
    )
    _warm_permission_queries(sample_ids)

    permission_rows_no_gov_df, fetch_without_gov_sec = _timed(
        _fetch_permission_rows_without_governed_join,
        sample_ids,
    )
    permission_rows_df, fetch_with_gov_sec = _timed(
        sample_permission_data.fetch_permission_rows_for_samples,
        sample_ids,
    )
    signal_rows_df, signal_assignment_sec = _timed(
        report_stage._assign_permission_signal_keys,  # pylint: disable=protected-access
        permission_rows_df,
    )
    signal_prev_type_df, build_signal_prevalence_by_type_sec = _timed(
        report_stage._build_signal_prevalence_by_type,  # pylint: disable=protected-access
        sample_core_df,
        signal_rows_df,
    )
    signal_prev_type_safe_df, build_signal_prevalence_by_type_behavior_safe_sec = _timed(
        report_stage._filter_behavior_safe_signals,  # pylint: disable=protected-access
        signal_prev_type_df,
    )
    signal_prev_family_df, build_signal_prevalence_by_family_sec = _timed(
        report_stage._build_signal_prevalence_by_family,  # pylint: disable=protected-access
        sample_core_df,
        signal_rows_df,
    )
    signal_prev_family_safe_df, build_signal_prevalence_by_family_behavior_safe_sec = _timed(
        report_stage._filter_behavior_safe_signals,  # pylint: disable=protected-access
        signal_prev_family_df,
    )
    family_signal_similarity_df, build_family_signal_similarity_sec = _timed(
        report_stage._build_family_signal_similarity,  # pylint: disable=protected-access
        signal_prev_family_df[signal_prev_family_df["benchmark_eligible_n_ge_3"].astype(bool)].copy(),
    )
    family_signal_similarity_behavior_safe_df, build_family_signal_similarity_behavior_safe_sec = _timed(
        report_stage._build_family_signal_similarity,  # pylint: disable=protected-access
        signal_prev_family_safe_df[signal_prev_family_safe_df["benchmark_eligible_n_ge_3"].astype(bool)].copy(),
    )
    governance_coverage_df = _build_governance_coverage(permission_rows_df, signal_rows_df, run_id)

    scenario_bundle_dir = output_dir / f"{scenario_name}_artifacts"
    scenario_bundle_dir.mkdir(parents=True, exist_ok=True)
    artifact_write_start = perf_counter()
    artifact_paths = [
        export_df_with_latest(
            signal_prev_type_df,
            run_id,
            "permission_signal_prevalence_by_type",
            scenario_bundle_dir,
        ),
        export_df_with_latest(
            signal_prev_type_safe_df,
            run_id,
            "permission_signal_prevalence_by_type_behavior_safe",
            scenario_bundle_dir,
        ),
        export_df_with_latest(
            signal_prev_family_df,
            run_id,
            "permission_signal_prevalence_by_family",
            scenario_bundle_dir,
        ),
        export_df_with_latest(
            signal_prev_family_safe_df,
            run_id,
            "permission_signal_prevalence_by_family_behavior_safe",
            scenario_bundle_dir,
        ),
        export_df_with_latest(
            family_signal_similarity_df,
            run_id,
            "family_signal_similarity",
            scenario_bundle_dir,
        ),
        export_df_with_latest(
            family_signal_similarity_behavior_safe_df,
            run_id,
            "family_signal_similarity_behavior_safe",
            scenario_bundle_dir,
        ),
        export_df_with_latest(
            governance_coverage_df,
            run_id,
            "permission_signal_governance_coverage",
            scenario_bundle_dir,
        ),
    ]
    summary_lines = [
        f"# Scenario performance note — {scenario_name}",
        "",
        f"- sample_source: {sample_source}",
        f"- sample_ids_requested: {len(sample_ids)}",
        f"- permission_rows_returned: {len(permission_rows_df)}",
        f"- rows_with_effective_lane: {int((permission_rows_df['effective_source_family_key'].astype(str).str.strip() != '').sum()) if 'effective_source_family_key' in permission_rows_df.columns else 0}",
        f"- rows_with_candidate_lane: {int((permission_rows_df['candidate_source_family_key'].astype(str).str.strip() != '').sum()) if 'candidate_source_family_key' in permission_rows_df.columns else 0}",
        f"- fetch_permission_rows_sec: {fetch_with_gov_sec:.6f}",
        f"- fetch_without_governed_join_sec: {fetch_without_gov_sec:.6f}",
    ]
    artifact_paths.append(
        export_markdown_with_latest(
            "\n".join(summary_lines) + "\n",
            run_id,
            "permission_trends_performance_note",
            scenario_bundle_dir,
        )
    )
    write_bundle_artifacts_sec = perf_counter() - artifact_write_start

    rows_with_effective_lane = int(
        (permission_rows_df.get("effective_source_family_key", pd.Series("", index=permission_rows_df.index))
         .astype(str)
         .str.strip() != "").sum()
    ) if not permission_rows_df.empty else 0
    rows_with_candidate_lane = int(
        (permission_rows_df.get("candidate_source_family_key", pd.Series("", index=permission_rows_df.index))
         .astype(str)
         .str.strip() != "").sum()
    ) if not permission_rows_df.empty else 0

    return {
        "scenario": scenario_name,
        "sample_source": sample_source,
        "sample_ids_requested": len(sample_ids),
        "permission_rows_returned": int(len(permission_rows_df)),
        "rows_with_effective_governance_lane": rows_with_effective_lane,
        "rows_with_candidate_lane": rows_with_candidate_lane,
        "fetch_permission_rows_for_samples_sec": round(fetch_with_gov_sec, 6),
        "read_without_governed_join_sec": round(fetch_without_gov_sec, 6),
        "vw_permission_vt_current_governed_overhead_sec": round(max(fetch_with_gov_sec - fetch_without_gov_sec, 0.0), 6),
        "signal_assignment_sec": round(signal_assignment_sec, 6),
        "build_signal_prevalence_by_type_sec": round(build_signal_prevalence_by_type_sec, 6),
        "build_signal_prevalence_by_type_behavior_safe_sec": round(
            build_signal_prevalence_by_type_behavior_safe_sec, 6
        ),
        "build_signal_prevalence_by_family_sec": round(build_signal_prevalence_by_family_sec, 6),
        "build_signal_prevalence_by_family_behavior_safe_sec": round(
            build_signal_prevalence_by_family_behavior_safe_sec, 6
        ),
        "build_family_signal_similarity_sec": round(build_family_signal_similarity_sec, 6),
        "build_family_signal_similarity_behavior_safe_sec": round(
            build_family_signal_similarity_behavior_safe_sec, 6
        ),
        "write_bundle_artifacts_sec": round(write_bundle_artifacts_sec, 6),
        "artifact_count_written": len(artifact_paths),
        "artifact_output_dir": str(scenario_bundle_dir.resolve()),
    }


def _recommendation(profile_df: pd.DataFrame) -> tuple[str, str]:
    if profile_df.empty:
        return "A", "No change needed; no performance rows were produced."
    worst = profile_df.sort_values("fetch_permission_rows_for_samples_sec", ascending=False, kind="mergesort").iloc[0]
    fetch_sec = float(worst["fetch_permission_rows_for_samples_sec"])
    base_sec = float(worst["read_without_governed_join_sec"])
    overhead_sec = float(worst["vw_permission_vt_current_governed_overhead_sec"])
    assignment_sec = float(worst["signal_assignment_sec"])
    build_sec = float(
        worst["build_signal_prevalence_by_type_sec"]
        + worst["build_signal_prevalence_by_family_sec"]
        + worst["build_family_signal_similarity_sec"]
        + worst["build_signal_prevalence_by_type_behavior_safe_sec"]
        + worst["build_signal_prevalence_by_family_behavior_safe_sec"]
        + worst["build_family_signal_similarity_behavior_safe_sec"]
    )
    if fetch_sec >= 20.0 and overhead_sec >= max(5.0, base_sec * 0.35):
        return "C", (
            "Cache/materialize governed permission-token state. The governed view join is the dominant extra cost "
            "relative to the same fetch without governance context."
        )
    if fetch_sec >= 20.0 and base_sec >= max(5.0, fetch_sec * 0.6):
        return "B", (
            "Investigate indexes or query-plan improvements first. Base permission-row fetch cost is already large "
            "before the governed view overhead is added."
        )
    if fetch_sec >= 30.0 and assignment_sec + build_sec >= fetch_sec * 0.75:
        return "D", (
            "Consider chunked broad-run fetch/build execution. The post-fetch signal processing is large enough "
            "that spreading broad runs across smaller batches may reduce operator-visible lag."
        )
    return "A", "No change needed yet; current governed join and signal-building costs are acceptable for these profiled scenarios."


def _summary_markdown(
    *,
    rows_df: pd.DataFrame,
    output_dir: Path,
    major_run_id: str,
    broad_limit: int,
) -> str:
    rec_code, rec_text = _recommendation(rows_df)
    lines = [
        "# Permission Trends Performance Profile",
        "",
        f"- Major-family cached run: `{major_run_id}`",
        f"- Broad comparison mode: sampled live `android_malware_all_current` cohort (`limit={broad_limit}`)",
        "- No DB rows were mutated in this profiling pass.",
        "",
        "## Scenario summary",
    ]
    for _, row in rows_df.iterrows():
        lines.extend(
            [
                "",
                f"### {row['scenario']}",
                f"- sample_source: {row['sample_source']}",
                f"- sample_ids_requested: {int(row['sample_ids_requested'])}",
                f"- permission_rows_returned: {int(row['permission_rows_returned'])}",
                f"- rows_with_effective_governance_lane: {int(row['rows_with_effective_governance_lane'])}",
                f"- rows_with_candidate_lane: {int(row['rows_with_candidate_lane'])}",
                f"- fetch_permission_rows_for_samples: {float(row['fetch_permission_rows_for_samples_sec']):.3f}s",
                f"- read_without_governed_join: {float(row['read_without_governed_join_sec']):.3f}s",
                f"- governed_join_overhead: {float(row['vw_permission_vt_current_governed_overhead_sec']):.3f}s",
                f"- signal_assignment: {float(row['signal_assignment_sec']):.3f}s",
                f"- build_signal_prevalence_by_type: {float(row['build_signal_prevalence_by_type_sec']):.3f}s",
                f"- build_signal_prevalence_by_family: {float(row['build_signal_prevalence_by_family_sec']):.3f}s",
                f"- build_family_signal_similarity: {float(row['build_family_signal_similarity_sec']):.3f}s",
                f"- behavior_safe_variants_total: {float(row['build_signal_prevalence_by_type_behavior_safe_sec']) + float(row['build_signal_prevalence_by_family_behavior_safe_sec']) + float(row['build_family_signal_similarity_behavior_safe_sec']):.3f}s",
                f"- write_bundle_artifacts: {float(row['write_bundle_artifacts_sec']):.3f}s",
            ]
        )
    if not rows_df.empty:
        stage_cols = [
            "fetch_permission_rows_for_samples_sec",
            "read_without_governed_join_sec",
            "vw_permission_vt_current_governed_overhead_sec",
            "signal_assignment_sec",
            "build_signal_prevalence_by_type_sec",
            "build_signal_prevalence_by_family_sec",
            "build_family_signal_similarity_sec",
            "build_signal_prevalence_by_type_behavior_safe_sec",
            "build_signal_prevalence_by_family_behavior_safe_sec",
            "build_family_signal_similarity_behavior_safe_sec",
            "write_bundle_artifacts_sec",
        ]
        mean_times = (
            rows_df[stage_cols]
            .mean(numeric_only=True)
            .sort_values(ascending=False, kind="mergesort")
            .head(5)
        )
        lines.extend(["", "## Mean bottlenecks"])
        for name, value in mean_times.items():
            lines.append(f"- {name}: {float(value):.3f}s")
    lines.extend(["", "## Recommendation", f"- {rec_code}. {rec_text}", ""])
    lines.append(
        "Keep `android_permission_run_aosp_import` as a documented provenance/workflow gap; do not synthesize import rows while profiling."
    )
    path = output_dir / "permission_trends_performance_profile.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--major-run-id",
        default="20260601T164351Z__fe432f",
        help="Cached major-family run id with aligned labels available.",
    )
    parser.add_argument(
        "--broad-sample-limit",
        type=int,
        default=2000,
        help="Sample limit for live broad all-current profiling.",
    )
    parser.add_argument(
        "--output-dir",
        default="output/tools/permission_trends_performance",
        help="Directory for performance profile outputs.",
    )
    args = parser.parse_args()

    output_dir = Path(str(args.output_dir)).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    major_labels_df = _load_cached_major_labels(str(args.major_run_id).strip())
    major_profile = _profile_scenario(
        scenario_name="major_family_cached",
        sample_source=f"cached_run:{args.major_run_id}",
        samples_df=major_labels_df,
        run_id="perf_major_family_cached",
        output_dir=output_dir,
    )

    broad_samples_df = _load_sampled_broad_live(int(args.broad_sample_limit))
    broad_profile = _profile_scenario(
        scenario_name="broad_all_current_sampled",
        sample_source=f"live_loader:android_malware_all_current_limit_{int(args.broad_sample_limit)}",
        samples_df=broad_samples_df,
        run_id="perf_broad_all_current_sampled",
        output_dir=output_dir,
    )

    profile_df = pd.DataFrame([major_profile, broad_profile])
    csv_path = output_dir / "permission_trends_performance_profile.csv"
    profile_df.to_csv(csv_path, index=False)
    md_path = _summary_markdown(
        rows_df=profile_df,
        output_dir=output_dir,
        major_run_id=str(args.major_run_id),
        broad_limit=int(args.broad_sample_limit),
    )

    summary = {
        "csv_path": str(csv_path),
        "markdown_path": str(md_path),
        "scenarios": profile_df.to_dict(orient="records"),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
