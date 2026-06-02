"""Parser diagnostics state and artifact-location helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable
import json

import pandas as pd

from config import app_config

from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.output_paths import output_root as canonical_output_root
from obsidiandroid.common.runtime_paths import resolve_diagnostics_dir
from obsidiandroid.database import db_engine

from . import run_locator
from .display_mode import resolve_display_mode


def output_root() -> Path:
    """Return the configured output root."""
    return canonical_output_root()


def global_diagnostics() -> Path:
    """Return the global diagnostics directory under the output root."""
    return output_root() / "diagnostics"


def run_diagnostics(run_id: str) -> Path:
    """Return the run-scoped diagnostics directory for one run id."""
    return run_locator.resolve_run_root_for_run_id(run_id, output_base=output_root()) / "diagnostics"


def first_existing(paths: list[Path]) -> Path | None:
    """Return the first existing regular file from a candidate list."""
    for path in paths:
        if path.is_file():
            return path
    return None


def _resolve_latest_run_diagnostics_artifact(
    resolver: Callable[[Path, str], Path],
    *,
    global_latest_name: str,
) -> Path | None:
    """Resolve one latest-run diagnostics artifact with global-latest fallback."""
    rid = run_locator.read_latest_run_id()
    if rid:
        return first_existing([resolver(run_diagnostics(rid), rid)])
    return first_existing([global_diagnostics() / global_latest_name])


def resolve_vendor_parser_coverage_csv() -> Path | None:
    """Prefer run-scoped vendor_parser_coverage, then global ``.latest``."""
    return _resolve_latest_run_diagnostics_artifact(
        oh.resolve_vendor_parser_coverage_path,
        global_latest_name="vendor_parser_coverage.latest.csv",
    )


def resolve_vendor_parser_coverage_candidates_csv() -> Path | None:
    """Resolve parser onboarding candidate CSV for the latest run."""
    return _resolve_latest_run_diagnostics_artifact(
        oh.resolve_vendor_parser_coverage_candidates_path,
        global_latest_name="vendor_parser_coverage_candidates.latest.csv",
    )


def resolve_vendor_gate_pre_gate_csv() -> Path | None:
    """Resolve pre-gate vendor score CSV for the latest run."""
    return _resolve_latest_run_diagnostics_artifact(
        oh.resolve_vendor_gate_top10_pre_gate_path,
        global_latest_name="vendor_gate_top10_pre_gate.latest.csv",
    )


def resolve_vendor_stress_test_csv() -> Path | None:
    """Resolve vendor parser stress-test CSV for the latest run."""
    return _resolve_latest_run_diagnostics_artifact(
        oh.resolve_vendor_parser_stress_test_path,
        global_latest_name="vendor_parser_stress_test.latest.csv",
    )


def resolve_vendor_strengths_weaknesses_csv() -> Path | None:
    """Resolve vendor parser strengths/weaknesses CSV for the latest run."""
    return _resolve_latest_run_diagnostics_artifact(
        oh.resolve_vendor_parser_strengths_weaknesses_path,
        global_latest_name="vendor_parser_strengths_weaknesses.latest.csv",
    )


def diagnostics_dir() -> Path:
    """Resolve the active diagnostics directory under the output root."""
    return resolve_diagnostics_dir()


def read_csv(path: Path) -> pd.DataFrame:
    """Read CSV if it exists, otherwise return an empty dataframe."""
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def read_latest_manifest() -> dict[str, Any]:
    """Load the latest run manifest payload when present."""
    path = diagnostics_dir() / "run_manifest.latest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _normalize_vendor_name(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _bool_series(series: pd.Series | object) -> pd.Series:
    """Coerce a mixed-value series into stable booleans."""
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
    normalized = series.copy()
    if normalized.dtype == object:
        lowered = normalized.fillna("").astype(str).str.strip().str.lower()
        mapping = {
            "1": True,
            "true": True,
            "t": True,
            "yes": True,
            "y": True,
            "0": False,
            "false": False,
            "f": False,
            "no": False,
            "n": False,
            "": False,
            "nan": False,
            "none": False,
        }
        normalized = lowered.map(mapping).fillna(False)
    return normalized.fillna(False).astype(bool)


def _string_series(series: pd.Series | object) -> pd.Series:
    """Coerce values into stripped strings with nulls normalized to empty."""
    if not isinstance(series, pd.Series):
        series = pd.Series(series)
    return series.fillna("").astype(str).str.strip()


def _selected_vendor_quality_map(scores_csv: Path | None) -> tuple[dict[str, dict[str, object]], list[str]]:
    if scores_csv is None:
        return {}, []
    df = read_csv(scores_csv)
    if df.empty or "Vendor" not in df.columns:
        return {}, []
    out: dict[str, dict[str, object]] = {}
    ordered: list[str] = []
    for _, row in df.iterrows():
        vendor = str(row.get("Vendor", "") or "").strip()
        if not vendor:
            continue
        key = _normalize_vendor_name(vendor)
        ordered.append(vendor)
        out[key] = {
            "selected_in_latest_run": True,
            "family_match_accuracy": row.get("Family Match Accuracy (%)"),
            "selected_vendor_category": row.get("Vendor Category"),
            "selected_vendor_rank": row.get("rank"),
        }
    return out, ordered


def _trusted_active_vendor_map() -> dict[str, bool]:
    try:
        rows = db_engine.execute_query(
            "SELECT LOWER(TRIM(vendor_key)) AS vendor_key, is_trusted_vendor, is_engine_active "
            "FROM virustotal_vendor_engines",
            fetch=True,
        )
    except Exception:
        return {}
    out: dict[str, bool] = {}
    for vendor_key, trusted, active in rows:
        norm = _normalize_vendor_name(vendor_key)
        out[norm] = bool(int(trusted or 0)) and bool(int(active or 0))
    return out


def build_parser_onboarding_queue(*, limit: int | None = None) -> pd.DataFrame:
    """Return enriched parser onboarding queue with operator tuning columns."""
    coverage_csv = resolve_vendor_parser_coverage_csv()
    candidates_csv = resolve_vendor_parser_coverage_candidates_csv()
    strengths_csv = resolve_vendor_strengths_weaknesses_csv()
    scores_csv = resolve_vendor_gate_pre_gate_csv()
    coverage_df = read_csv(coverage_csv) if coverage_csv is not None else pd.DataFrame()
    if coverage_df.empty:
        return pd.DataFrame()

    strengths_df = read_csv(strengths_csv) if strengths_csv is not None else pd.DataFrame()
    candidates_df = read_csv(candidates_csv) if candidates_csv is not None else pd.DataFrame()
    selected_map, _selected_order = _selected_vendor_quality_map(scores_csv)
    trusted_map = _trusted_active_vendor_map()

    queue = coverage_df.copy()
    queue["vendor_norm"] = queue["vendor_column"].map(_normalize_vendor_name)

    if not strengths_df.empty and "vendor" in strengths_df.columns:
        strengths = strengths_df.copy()
        strengths["vendor_norm"] = strengths["vendor"].map(_normalize_vendor_name)
        keep_cols = [
            "vendor_norm",
            "mapped_ratio",
            "unknown_ratio",
            "generic_ratio",
            "trusted_vendor_flag",
            "active_vendor_flag",
            "weakness_tags",
            "strength_tags",
        ]
        queue = queue.merge(strengths[keep_cols], on="vendor_norm", how="left")

    if not candidates_df.empty and "vendor_column" in candidates_df.columns:
        cands = candidates_df.copy()
        cands["vendor_norm"] = cands["vendor_column"].map(_normalize_vendor_name)
        queue = queue.merge(
            cands[["vendor_norm", "priority_rank", "onboarding_priority"]],
            on="vendor_norm",
            how="left",
        )

    queue["selected_in_latest_run"] = queue["vendor_norm"].map(
        lambda key: bool(selected_map.get(str(key), {}).get("selected_in_latest_run", False))
    )
    queue["family_match_accuracy"] = queue["vendor_norm"].map(
        lambda key: selected_map.get(str(key), {}).get("family_match_accuracy")
    )
    queue["trusted_active"] = queue["vendor_norm"].map(
        lambda key: bool(trusted_map.get(str(key), False))
    )
    queue["unknown_rate"] = pd.to_numeric(queue.get("unknown_ratio"), errors="coerce").round(4)
    queue["generic_rate"] = pd.to_numeric(queue.get("generic_ratio"), errors="coerce").round(4)
    queue["family_match_accuracy"] = pd.to_numeric(queue.get("family_match_accuracy"), errors="coerce").round(2)

    def _priority_reason(row: pd.Series) -> str:
        reasons: list[str] = []
        if bool(row.get("selected_in_latest_run", False)):
            reasons.append("selected for latest run")
        if bool(row.get("trusted_active", False)):
            reasons.append("trusted active engine")
        cov = float(pd.to_numeric(row.get("coverage_pct"), errors="coerce") or 0.0)
        if cov >= 99.0:
            reasons.append("very high coverage")
        elif cov >= 90.0:
            reasons.append("high coverage")
        unknown = float(pd.to_numeric(row.get("unknown_rate"), errors="coerce") or 0.0)
        generic = float(pd.to_numeric(row.get("generic_rate"), errors="coerce") or 0.0)
        if unknown >= 0.75:
            reasons.append("high unknown output")
        if generic >= 0.75:
            reasons.append("high generic output")
        fma = pd.to_numeric(row.get("family_match_accuracy"), errors="coerce")
        if pd.notna(fma):
            if float(fma) >= 20.0:
                reasons.append("usable family match signal")
            else:
                reasons.append("weak family match signal")
        if not reasons:
            reasons.append("coverage-only candidate")
        return "; ".join(reasons)

    def _recommended_action(row: pd.Series) -> str:
        if bool(row.get("selected_in_latest_run", False)):
            return "Prioritize custom parser review for selected-vendor quality."
        if bool(row.get("trusted_active", False)):
            return "Consider onboarding or validating a generic parser path."
        unknown = float(pd.to_numeric(row.get("unknown_rate"), errors="coerce") or 0.0)
        generic = float(pd.to_numeric(row.get("generic_rate"), errors="coerce") or 0.0)
        if unknown >= 0.75 or generic >= 0.75:
            return "Sample labels first; likely needs custom parser logic."
        return "Queue for parser onboarding if label patterns look stable."

    queue["priority_reason"] = queue.apply(_priority_reason, axis=1)
    queue["recommended_action"] = queue.apply(_recommended_action, axis=1)

    queue = queue[queue["parser_mapped"] == 0].copy()
    queue["selected_sort"] = queue["selected_in_latest_run"].astype(int)
    queue["trusted_sort"] = queue["trusted_active"].astype(int)
    if "priority_rank" in queue.columns:
        queue["priority_sort"] = pd.to_numeric(queue["priority_rank"], errors="coerce").fillna(9999)
    else:
        queue["priority_sort"] = 9999
    queue["coverage_sort"] = pd.to_numeric(queue.get("coverage_pct"), errors="coerce").fillna(0.0)
    queue = queue.sort_values(
        by=["selected_sort", "trusted_sort", "priority_sort", "coverage_sort", "vendor_column"],
        ascending=[False, False, True, False, True],
    )
    if limit is not None:
        queue = queue.head(max(0, int(limit)))
    return queue[
        [
            "vendor_column",
            "coverage_pct",
            "selected_in_latest_run",
            "trusted_active",
            "parser_mapped",
            "unknown_rate",
            "generic_rate",
            "family_match_accuracy",
            "priority_reason",
            "recommended_action",
        ]
    ].reset_index(drop=True)


def build_parser_diagnostics_state(
    *,
    workbook_loader: Callable[..., object],
    mode: str | None = None,
) -> dict[str, object]:
    """Return current parser-diagnostics capability state."""
    coverage_csv = resolve_vendor_parser_coverage_csv()
    candidates_csv = resolve_vendor_parser_coverage_candidates_csv()
    scores_csv = resolve_vendor_gate_pre_gate_csv()
    try:
        workbook_df = workbook_loader(emit_warnings=False)
    except TypeError:
        workbook_df = workbook_loader()
    workbook_ready = isinstance(workbook_df, pd.DataFrame)
    csv_ready = coverage_csv is not None
    rid = run_locator.read_latest_run_id()
    source_run_id = rid or ""
    observed_engines = 0
    parser_mapped_vendors = 0
    unmapped_vendors = 0
    mapped_pct = 0.0
    top_unmapped_preview: list[str] = []
    coverage_from_latest_run = False
    if coverage_csv is not None:
        coverage_from_latest_run = bool(rid and str(run_diagnostics(rid)) in str(coverage_csv))
        coverage_df = read_csv(coverage_csv)
        if not coverage_df.empty:
            observed_engines = int(len(coverage_df))
            parser_mapped_vendors = int(
                pd.to_numeric(coverage_df.get("parser_mapped", 0), errors="coerce").fillna(0).sum()
            )
            unmapped_vendors = max(0, observed_engines - parser_mapped_vendors)
            mapped_pct = round((100.0 * parser_mapped_vendors / observed_engines), 1) if observed_engines else 0.0
            unmapped_df = coverage_df[coverage_df["parser_mapped"] == 0].copy()
            if not unmapped_df.empty and "coverage_pct" in unmapped_df.columns:
                unmapped_df["coverage_pct"] = pd.to_numeric(
                    unmapped_df.get("coverage_pct"),
                    errors="coerce",
                ).fillna(0.0)
                top_unmapped_preview = [
                    str(v).strip()
                    for v in unmapped_df.sort_values("coverage_pct", ascending=False)
                    .head(3)
                    .get("vendor_column", pd.Series(dtype="object"))
                    .tolist()
                    if str(v).strip()
                ]
    onboarding_candidate_count = 0
    top_candidates_preview: list[str] = []
    if candidates_csv is not None:
        candidates_df = read_csv(candidates_csv)
        if not candidates_df.empty:
            onboarding_candidate_count = int(len(candidates_df))
            top_candidates_preview = [
                str(v).strip()
                for v in candidates_df.head(3).get("vendor_column", pd.Series(dtype="object")).tolist()
                if str(v).strip()
            ]
    manifest = read_latest_manifest()
    selected_vendors = manifest.get("selected_vendor_count")
    try:
        selected_vendors = int(selected_vendors) if selected_vendors is not None else None
    except (TypeError, ValueError):
        selected_vendors = None
    try:
        cohort_engines_observed = (
            int(manifest.get("engine_count_observed")) if manifest.get("engine_count_observed") is not None else None
        )
    except (TypeError, ValueError):
        cohort_engines_observed = None
    try:
        cohort_engines_canonical = (
            int(manifest.get("engine_count_canonical")) if manifest.get("engine_count_canonical") is not None else None
        )
    except (TypeError, ValueError):
        cohort_engines_canonical = None
    try:
        post_score_engines_included = (
            int(manifest.get("engine_count_included_after_gating"))
            if manifest.get("engine_count_included_after_gating") is not None
            else None
        )
    except (TypeError, ValueError):
        post_score_engines_included = None
    try:
        requested_parser_top_k = (
            int(manifest.get("engine_count_requested_top_k"))
            if manifest.get("engine_count_requested_top_k") is not None
            else None
        )
    except (TypeError, ValueError):
        requested_parser_top_k = None
    engine_scoring_universe = None
    engine_metadata_table_universe = None
    engine_metadata_only_count = None
    engine_verdict_only_count = None
    engine_metadata_alias_suggestion_count = None
    engine_metadata_current_prefix_missing_verdict_count = None
    engine_metadata_unclear_count = None
    top_metadata_alias_preview: list[str] = []
    engine_exclusion_audit_rows = None
    engine_near_miss_count = None
    top_near_miss_preview: list[str] = []
    engine_csv = Path()
    if rid:
        rd = run_diagnostics(rid)
        for candidate in (rd / "engine_scoring_summary.csv", rd / "engine_scoring_summary.latest.csv"):
            if candidate.is_file():
                engine_csv = candidate
                break
    if engine_csv.is_file():
        engine_df = read_csv(engine_csv)
        if not engine_df.empty:
            engine_scoring_universe = int(len(engine_df))
        drift_csv = engine_csv.with_name("engine_metadata_drift.csv")
        drift_df = read_csv(drift_csv)
        if not drift_df.empty and "drift_status" in drift_df.columns:
            engine_metadata_table_universe = int(
                pd.to_numeric(drift_df.get("in_metadata_table", 0), errors="coerce").fillna(0).astype(bool).sum()
            )
            drift_status = _string_series(drift_df["drift_status"])
            engine_metadata_only_count = int((drift_status == "metadata_only").sum())
            engine_verdict_only_count = int((drift_status == "verdict_only").sum())
            if "suggestion_basis" in drift_df.columns and "likely_current_vendor_key" in drift_df.columns:
                suggestion_basis = _string_series(drift_df["suggestion_basis"])
                likely_current = _string_series(drift_df["likely_current_vendor_key"])
                vendor_key = _string_series(drift_df.get("vendor_key", pd.Series(dtype="object")))
                metadata_only_mask = drift_status == "metadata_only"
                alias_mask = metadata_only_mask & (suggestion_basis == "legacy_metadata_alias_to_current_vt_prefix")
                current_prefix_mask = metadata_only_mask & (
                    suggestion_basis == "current_vt_documented_prefix_without_verdict_column"
                )
                unclear_mask = metadata_only_mask & (~alias_mask) & (~current_prefix_mask)
                engine_metadata_alias_suggestion_count = int(alias_mask.sum())
                engine_metadata_current_prefix_missing_verdict_count = int(current_prefix_mask.sum())
                engine_metadata_unclear_count = int(unclear_mask.sum())
                if int(alias_mask.sum()) > 0:
                    alias_df = pd.DataFrame(
                        {
                            "vendor_key": vendor_key[alias_mask].tolist(),
                            "likely_current_vendor_key": likely_current[alias_mask].tolist(),
                        }
                    )
                    top_metadata_alias_preview = [
                        f"{str(row.vendor_key)}->{str(row.likely_current_vendor_key)}"
                        for row in alias_df.head(3).itertuples(index=False)
                        if str(row.vendor_key).strip() and str(row.likely_current_vendor_key).strip()
                    ]
        exclusion_csv = run_diagnostics(rid) / f"engine_exclusion_audit_{rid}.csv"
        exclusion_df = read_csv(exclusion_csv)
        if not exclusion_df.empty:
            engine_exclusion_audit_rows = int(len(exclusion_df))
            near_miss_mask = _bool_series(exclusion_df.get("near_miss_flag", pd.Series(dtype="object")))
            engine_near_miss_count = int(near_miss_mask.sum())
            if engine_near_miss_count > 0:
                near_df = exclusion_df[near_miss_mask].copy()
                if "coverage_pct" in near_df.columns:
                    near_df["coverage_pct"] = pd.to_numeric(near_df.get("coverage_pct"), errors="coerce").fillna(0.0)
                    near_df = near_df.sort_values("coverage_pct", ascending=False)
                top_near_miss_preview = [
                    str(v).strip()
                    for v in near_df.head(3).get("engine_name_canonical", pd.Series(dtype="object")).tolist()
                    if str(v).strip()
                ]
    top_selected_vendor_preview: list[str] = []
    selected_vendor_data_present = False
    if scores_csv is not None:
        scores_df = read_csv(scores_csv)
        if not scores_df.empty:
            selected_vendor_data_present = True
            top_selected_vendor_preview = [
                str(v).strip()
                for v in scores_df.head(3).get("Vendor", pd.Series(dtype="object")).tolist()
                if str(v).strip()
            ]
    needs_attention = ""
    recommended_open_first = "Parser onboarding queue"
    status = "GREEN"
    if csv_ready and not workbook_ready:
        needs_attention = "Workbook drill-down unavailable (optional unless doing single-vendor deep debugging)"
        recommended_open_first = "Parser onboarding queue"
        status = "YELLOW"
    elif not csv_ready:
        needs_attention = "CSV snapshots unavailable"
        recommended_open_first = "Export paths"
        status = "RED"
    elif onboarding_candidate_count > 0:
        needs_attention = (
            f"{onboarding_candidate_count} prioritized onboarding candidates "
            f"out of {unmapped_vendors} unmapped vendors"
        )
        status = "YELLOW"
    elif unmapped_vendors > 0:
        needs_attention = f"{unmapped_vendors} unmapped vendors remain (coverage-only backlog)"
        status = "YELLOW"
    next_tuning_action = "Review parser onboarding candidates."
    if not csv_ready:
        next_tuning_action = "Generate parser coverage snapshots first."
    elif not workbook_ready:
        next_tuning_action = "Review onboarding candidates; workbook drill-down is optional."
    elif onboarding_candidate_count > 0:
        next_tuning_action = (
            "Open Parser onboarding queue; start with selected/trusted high-coverage unmapped vendors before coverage-only backlog."
        )
    else:
        next_tuning_action = "Review selected vendors and parser quality drift."
    explanation = (
        "Observed engines are all vendor columns seen in the run coverage snapshot. "
        "Post-score included engines are the narrower engine-gated subset. "
        "Selected vendors are the parser-scored leakage-safe subset used by the latest run."
    )
    return {
        "display_mode": resolve_display_mode(mode),
        "source_run_id": source_run_id,
        "coverage_from_latest_run": coverage_from_latest_run,
        "selected_vendor_data_present": selected_vendor_data_present,
        "status": status,
        "workbook_ready": workbook_ready,
        "csv_ready": csv_ready,
        "coverage_csv_path": coverage_csv or Path(),
        "candidates_csv_path": candidates_csv or Path(),
        "scores_csv_path": scores_csv or Path(),
        "observed_engines": observed_engines,
        "parser_mapped_vendors": parser_mapped_vendors,
        "unmapped_vendors": unmapped_vendors,
        "mapped_pct": mapped_pct,
        "onboarding_candidate_count": onboarding_candidate_count,
        "top_unmapped_preview": top_unmapped_preview,
        "top_candidates_preview": top_candidates_preview,
        "selected_vendors": selected_vendors,
        "top_selected_vendor_preview": top_selected_vendor_preview,
        "engine_scoring_universe": engine_scoring_universe,
        "cohort_engines_observed": cohort_engines_observed,
        "cohort_engines_canonical": cohort_engines_canonical,
        "post_score_engines_included": post_score_engines_included,
        "requested_parser_top_k": requested_parser_top_k,
        "engine_metadata_table_universe": engine_metadata_table_universe,
        "engine_metadata_only_count": engine_metadata_only_count,
        "engine_verdict_only_count": engine_verdict_only_count,
        "engine_metadata_alias_suggestion_count": engine_metadata_alias_suggestion_count,
        "engine_metadata_current_prefix_missing_verdict_count": engine_metadata_current_prefix_missing_verdict_count,
        "engine_metadata_unclear_count": engine_metadata_unclear_count,
        "top_metadata_alias_preview": top_metadata_alias_preview,
        "engine_exclusion_audit_rows": engine_exclusion_audit_rows,
        "engine_near_miss_count": engine_near_miss_count,
        "top_near_miss_preview": top_near_miss_preview,
        "needs_attention": needs_attention,
        "recommended_open_first": recommended_open_first,
        "next_tuning_action": next_tuning_action,
        "explanation": explanation,
    }


def get_parser_summary_state(*, mode: str | None = None) -> dict[str, object]:
    """Return current parser summary state using the default workbook loader."""
    from .workbook_loader import load_enriched_matrix_for_menu

    return build_parser_diagnostics_state(workbook_loader=load_enriched_matrix_for_menu, mode=mode)


__all__ = [
    "build_parser_onboarding_queue",
    "build_parser_diagnostics_state",
    "diagnostics_dir",
    "first_existing",
    "global_diagnostics",
    "get_parser_summary_state",
    "output_root",
    "read_csv",
    "read_latest_manifest",
    "resolve_vendor_gate_pre_gate_csv",
    "resolve_vendor_parser_coverage_candidates_csv",
    "resolve_vendor_parser_coverage_csv",
    "resolve_vendor_strengths_weaknesses_csv",
    "resolve_vendor_stress_test_csv",
    "run_diagnostics",
]
