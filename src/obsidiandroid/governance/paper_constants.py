"""Paper constants export for locked benchmark runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import json
import pandas as pd


def build_paper_constants_payload(
    *,
    run_id: str,
    profile_id: str,
    cohort_contract: dict[str, Any],
    split_hash: str,
    samples_df: pd.DataFrame,
) -> dict[str, Any]:
    """Build manuscript constants from a validated locked benchmark run."""
    if not bool(cohort_contract.get("paper_locked", False)):
        raise ValueError("paper constants require a locked cohort contract")
    if str(cohort_contract.get("validation", {}).get("status", "") or "") != "match":
        raise ValueError("paper constants require a fully matched locked cohort run")
    if not str(split_hash or "").strip():
        raise ValueError("paper constants require a non-empty split_hash")

    sample_lock = cohort_contract.get("sample_id_lock", {}) if isinstance(cohort_contract.get("sample_id_lock"), dict) else {}
    cohort_hash = str(sample_lock.get("cohort_hash", "") or "").strip()
    if not cohort_hash:
        raise ValueError("paper constants require a non-empty cohort_hash")

    sample_count = int(cohort_contract.get("expected", {}).get("sample_count", 0) or 0)
    family_count = int(cohort_contract.get("expected", {}).get("family_count", 0) or 0)
    type_count = int(cohort_contract.get("expected", {}).get("type_count", 0) or 0)
    family_counts = (
        samples_df["family_canonical"].fillna("").astype(str).str.strip().value_counts()
        if "family_canonical" in samples_df.columns
        else pd.Series(dtype="int64")
    )
    top_family_share = float((family_counts.iloc[0] / len(samples_df)) if len(samples_df) and not family_counts.empty else 0.0)
    return {
        "schema_version": "1.0",
        "run_id": str(run_id),
        "profile_id": str(profile_id),
        "contract_id": str(cohort_contract.get("contract_id", "") or ""),
        "sample_count": sample_count,
        "family_count": family_count,
        "malware_type_count": type_count,
        "time_window": {
            "start_utc": str(cohort_contract.get("expected", {}).get("time_window_start_utc", "") or ""),
            "end_utc": str(cohort_contract.get("expected", {}).get("time_window_end_utc", "") or ""),
            "window_semantics": str(
                cohort_contract.get("expected", {}).get("time_window_semantics", "start_inclusive_end_exclusive") or ""
            ),
        },
        "top_family_share": round(top_family_share, 12),
        "cohort_hash": cohort_hash,
        "split_hash": str(split_hash),
        "taxonomy_hash": str(sample_lock.get("taxonomy_hash", "") or ""),
    }


def write_paper_constants(
    *,
    run_id: str,
    profile_id: str,
    cohort_contract: dict[str, Any],
    split_hash: str,
    samples_df: pd.DataFrame,
    output_root: Path,
) -> Path:
    """Write canonical paper constants and reject incompatible rewrites."""
    payload = build_paper_constants_payload(
        run_id=run_id,
        profile_id=profile_id,
        cohort_contract=cohort_contract,
        split_hash=split_hash,
        samples_df=samples_df,
    )
    out_dir = output_root / "artifacts" / "paper"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "paper_constants.json"
    if out_path.exists():
        existing = json.loads(out_path.read_text(encoding="utf-8"))
        for key in ("sample_count", "family_count", "malware_type_count", "cohort_hash"):
            if existing.get(key) != payload.get(key):
                raise ValueError(
                    f"paper_constants mismatch for '{key}': existing={existing.get(key)!r} new={payload.get(key)!r}"
                )
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path

