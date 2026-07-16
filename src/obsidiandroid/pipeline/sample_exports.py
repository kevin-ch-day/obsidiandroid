"""Cohort export and time-contract helpers for the samples stage.

Canonical implementation (**Pass 69**): ``obsidiandroid.pipeline.sample_exports``;
The supported import path is ``obsidiandroid.pipeline.sample_exports``.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.common import output_hygiene as oh


def diagnostics_dir(run_id: str | None = None) -> Path:
    """Resolve diagnostics directory for the active runtime context."""
    runtime_dir = str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "").strip()
    if runtime_dir:
        runtime_path = Path(runtime_dir)
        runtime_run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "") or "").strip()
        if run_id:
            run_root = runtime_path.parent
            requested_run_id = str(run_id).strip()
            if runtime_run_id and runtime_run_id == requested_run_id:
                return runtime_path
            if run_root.name == requested_run_id:
                return runtime_path
        else:
            if runtime_run_id and runtime_path.parent.name == runtime_run_id:
                return runtime_path
            if not runtime_run_id:
                return runtime_path
            return runtime_path
    return Path(app_config.DEFAULT_OUTPUT_DIR) / "diagnostics"


def export_cohort_filter_contract(
    *,
    run_id: str,
    profile_id: str,
    gates: dict[str, Any],
    gate_rows: list[dict[str, Any]],
) -> tuple[str, str]:
    """Export the cohort filter contract and gate-count report."""
    out_dir = diagnostics_dir(run_id=run_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    contract = {
        "run_id": run_id,
        "profile_id": profile_id,
        "filter_order": [
            "time_window",
            "exclude_unknown_family_canonical",
            "package_name_gate",
            "min_malicious_detections",
            "family_cap",
        ],
        "cohort_gates": gates,
        "paper_mode": bool(getattr(app_config, "PAPER_MODE_ENABLED", False)),
    }
    contract_path = out_dir / f"cohort_filter_contract_{run_id}.json"
    payload = contract
    written_contract = oh.mirror_json_text_run_then_global(
        diagnostics_dir=out_dir,
        run_filename=contract_path.name,
        payload=payload,
        global_latest_name="cohort_filter_contract.latest.json",
    )
    contract_path = written_contract[0]

    gate_df = pd.DataFrame(gate_rows)
    gate_csv_text = gate_df.to_csv(index=False)
    gate_written = oh.mirror_csv_text_run_then_global(
        diagnostics_dir=out_dir,
        run_filename=f"cohort_gate_counts_{run_id}.csv",
        csv_text=gate_csv_text,
        global_latest_name="cohort_gate_counts.latest.csv",
    )
    gate_path = gate_written[0]
    return str(contract_path), str(gate_path)


def resolve_dataset_time_contract(gates: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Build the deterministic dataset time-window contract for the run."""
    if not bool(getattr(app_config, "ENABLE_PAPER_TIME_WINDOW", True)):
        return {
            "enabled": False,
            "run_id": run_id,
            "timestamp_field": "effective_first_seen_at_utc",
            "fallback_order": ["vt_first_seen_itw_date", "vt_first_submission_at_utc"],
            "require_effective_first_seen": True,
            "start_utc": None,
            "end_utc": None,
            "window_semantics": "start_inclusive_end_exclusive",
            "utc_normalization_method": "assume_naive_is_utc",
        }
    start_utc = str(
        gates.get(
            "time_window_start_utc",
            getattr(app_config, "PAPER_TIME_WINDOW_START_UTC", "2020-01-01T00:00:00Z"),
        )
    )
    explicit_end = gates.get("time_window_end_utc")
    if explicit_end:
        end_utc = str(explicit_end)
    else:
        end_mode = str(getattr(app_config, "PAPER_TIME_WINDOW_END_MODE", "run_date_eod_utc"))
        if end_mode == "run_date_eod_utc":
            now = datetime.now(timezone.utc)
            # The SQL predicate is end-exclusive. Use the following midnight so
            # the complete current UTC day is included rather than silently
            # omitting rows timestamped at 23:59:59 (or later fractions).
            end_utc = (now.date() + timedelta(days=1)).isoformat() + "T00:00:00Z"
        else:
            end_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "enabled": True,
        "run_id": run_id,
        "timestamp_field": "effective_first_seen_at_utc",
        "fallback_order": ["vt_first_seen_itw_date", "vt_first_submission_at_utc"],
        "require_effective_first_seen": True,
        "start_utc": start_utc,
        "end_utc": end_utc,
        "window_semantics": "start_inclusive_end_exclusive",
        "utc_normalization_method": "assume_naive_is_utc",
    }


def augment_dataset_time_contract(
    *,
    time_contract: dict[str, Any],
    samples_df: pd.DataFrame,
) -> dict[str, Any]:
    """Attach realized time-window audit values after cohort construction."""
    out = dict(time_contract or {})
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        out["min_timestamp_included"] = None
        out["max_timestamp_included"] = None
        out["records_on_start_boundary"] = 0
        out["records_on_end_boundary"] = 0
        return out

    ts = pd.to_datetime(samples_df.get("effective_first_seen_at_utc"), errors="coerce", utc=True)
    valid = ts.dropna()
    if valid.empty:
        out["min_timestamp_included"] = None
        out["max_timestamp_included"] = None
        out["records_on_start_boundary"] = 0
        out["records_on_end_boundary"] = 0
        return out

    out["min_timestamp_included"] = str(valid.min().strftime("%Y-%m-%dT%H:%M:%SZ"))
    out["max_timestamp_included"] = str(valid.max().strftime("%Y-%m-%dT%H:%M:%SZ"))

    start_raw = out.get("start_utc")
    end_raw = out.get("end_utc")
    start_ts = pd.to_datetime(start_raw, errors="coerce", utc=True) if start_raw else pd.NaT
    end_ts = pd.to_datetime(end_raw, errors="coerce", utc=True) if end_raw else pd.NaT
    out["records_on_start_boundary"] = int((valid == start_ts).sum()) if pd.notna(start_ts) else 0
    out["records_on_end_boundary"] = int((valid == end_ts).sum()) if pd.notna(end_ts) else 0
    return out


def export_dataset_time_contract(time_contract: dict[str, Any]) -> str:
    """Export the dataset time-window contract JSON."""
    path = Path(
        str(
            getattr(
                app_config,
                "DATASET_TIME_CONTRACT_FILE",
                "output/diagnostics/dataset_time_contract.latest.json",
            )
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(time_contract, indent=2, sort_keys=True), encoding="utf-8")
    return str(path)


def export_time_window_family_distributions(samples_df: pd.DataFrame) -> list[str]:
    """Export family distributions required by reviewer time-window audits."""
    out_dir = diagnostics_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    if samples_df.empty:
        return artifacts

    family_df = (
        samples_df.groupby("family_canonical", dropna=False)["sample_id"]
        .count()
        .reset_index(name="sample_count")
        .sort_values("sample_count", ascending=False)
    )
    family_path = out_dir / "family_distribution_2020_present.csv"
    family_df.to_csv(family_path, index=False)
    artifacts.append(str(family_path))

    year_col = "effective_first_seen_year"
    year_df = samples_df.copy()
    if year_col not in year_df.columns and "effective_first_seen_at_utc" in year_df.columns:
        anchor = pd.to_datetime(year_df["effective_first_seen_at_utc"], errors="coerce", utc=True)
        year_df[year_col] = anchor.dt.year
    if year_col not in year_df.columns:
        return artifacts
    year_df[year_col] = pd.to_numeric(year_df[year_col], errors="coerce")
    year_df = year_df.dropna(subset=[year_col])
    if year_df.empty:
        return artifacts
    year_df[year_col] = year_df[year_col].astype(int)

    family_year_df = (
        year_df.groupby([year_col, "family_canonical"], dropna=False)["sample_id"]
        .count()
        .reset_index(name="sample_count")
        .sort_values([year_col, "sample_count"], ascending=[True, False])
    )
    family_year_path = out_dir / "family_distribution_by_year.csv"
    family_year_df.to_csv(family_year_path, index=False)
    artifacts.append(str(family_year_path))

    if bool(getattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", True)):
        for family_name in ("Devixor", "Gigabud"):
            family_year = (
                family_year_df[
                    family_year_df["family_canonical"].astype(str).str.lower() == family_name.lower()
                ]
                .copy()
                .sort_values(year_col)
            )
            family_path = out_dir / f"{family_name.lower()}_by_year.csv"
            if family_year.empty:
                if family_path.exists():
                    try:
                        family_path.unlink()
                    except Exception:
                        pass
                continue
            family_year.to_csv(family_path, index=False)
            artifacts.append(str(family_path))
    return artifacts


def export_paper_cohort_sample_ids(samples_df: pd.DataFrame) -> str:
    """Freeze cohort sample IDs used for paper ablation comparability."""
    if (
        not bool(getattr(app_config, "PAPER_MODE_ENABLED", False))
        and not bool(getattr(app_config, "ENABLE_VERBOSE_RUN_ARTIFACTS", True))
    ):
        return ""
    out_path = Path(
        str(
            getattr(
                app_config,
                "PAPER_COHORT_SAMPLE_IDS_FILE",
                "output/diagnostics/paper_cohort_sample_ids.csv",
            )
        )
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ids = (
        pd.to_numeric(samples_df.get("sample_id"), errors="coerce")
        .dropna()
        .astype(int)
        .drop_duplicates()
        .sort_values()
        .to_frame(name="sample_id")
    )
    ids.to_csv(out_path, index=False)
    return str(out_path)
