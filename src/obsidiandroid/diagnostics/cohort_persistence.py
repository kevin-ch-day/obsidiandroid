"""Persist and reload governed cohort membership across pipeline stages."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd

from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.csv_io import optional_csv


DEFAULT_COHORT_MEMBERSHIP_COLUMNS: tuple[str, ...] = (
    "sample_id",
    "sha256",
    "family_id",
    "family_canonical",
    "type_slug",
    "android_package_name",
    "effective_first_seen_at_utc",
    "vt_first_submission_at_utc",
)


def _read_csv_if_exists(path: Path) -> pd.DataFrame:
    return optional_csv(path)


def load_samples_df_fallback(diagnostics_dir: Path, run_id: str) -> pd.DataFrame:
    """Rebuild cohort rows from diagnostics exports when the runtime frame is unavailable."""
    for stem in ("aligned_labels", "cohort_membership"):
        candidates = [
            diagnostics_dir / f"{stem}_{run_id}.csv",
            diagnostics_dir / f"{stem}.latest.csv",
        ]
        if stem == "cohort_membership":
            candidates.insert(0, diagnostics_dir / "cohort_membership.csv")
        for path in candidates:
            df = _read_csv_if_exists(path)
            if not df.empty and "sample_id" in df.columns:
                return df
    return pd.DataFrame()


def resolve_effective_samples_df(
    diagnostics_dir: Path,
    run_id: str,
    samples_df: pd.DataFrame | None,
) -> pd.DataFrame | None:
    """Return in-memory samples or reload from persisted diagnostics exports."""
    if isinstance(samples_df, pd.DataFrame) and not samples_df.empty:
        return samples_df
    fallback = load_samples_df_fallback(diagnostics_dir, run_id)
    return fallback if not fallback.empty else None


def normalize_membership_df(samples_df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    available_columns = [column for column in columns if column in samples_df.columns]
    membership_df = samples_df[available_columns].copy() if available_columns else samples_df.copy()
    if "sample_id" in membership_df.columns:
        membership_df["sample_id"] = pd.to_numeric(membership_df["sample_id"], errors="coerce")
        membership_df = membership_df.sort_values("sample_id", kind="mergesort")
    return membership_df


def export_cohort_membership_snapshot(
    *,
    diagnostics_dir: Path,
    run_id: str,
    samples_df: pd.DataFrame,
    columns: Sequence[str] | None = None,
) -> list[str]:
    """Write legacy and run-scoped cohort membership exports for manifest reload."""
    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    membership_df = normalize_membership_df(
        samples_df,
        tuple(columns or DEFAULT_COHORT_MEMBERSHIP_COLUMNS),
    )
    csv_text = membership_df.to_csv(index=False)
    paths: list[str] = []

    legacy_path = diagnostics_dir / "cohort_membership.csv"
    legacy_path.write_text(csv_text, encoding="utf-8")
    paths.append(str(legacy_path))

    rid = str(run_id or "").strip() or "unknown"
    mirrored = oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=f"cohort_membership_{rid}.csv",
        csv_text=csv_text,
        global_latest_name="cohort_membership.latest.csv",
    )
    paths.extend(str(path) for path in mirrored)
    return paths
