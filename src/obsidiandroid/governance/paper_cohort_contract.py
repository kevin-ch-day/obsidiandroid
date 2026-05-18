"""Locked cohort contract helpers for reproducible evidence runs.

Compatibility note:
    This module retains historical ``paper_*`` field names for older callers
    and artifacts. New operator-facing profiles and emitted payloads should
    prefer generic cohort-contract language.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.common.cohort_contracts import (
    declared_cohort_contract_status,
    declared_cohort_enforcement_level,
    unresolved_cohort_contract_payload,
)
from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.common.repo_paths import repo_root
from obsidiandroid.database import db_config


def validate_profile_paper_lock(profile: dict[str, Any], profile_path: Path) -> None:
    """Validate optional locked-cohort metadata embedded in a profile."""
    paper_locked = bool(profile.get("paper_locked", False))
    raw_lock = profile.get("paper_lock")
    profile_id = str(profile.get("profile_id", profile_path.stem) or profile_path.stem)

    if "paper_locked" in profile and not isinstance(profile.get("paper_locked"), bool):
        raise ValueError(f"Profile '{profile_path}' key 'paper_locked' must be a boolean.")

    if profile_id.endswith("_locked") and not paper_locked:
        raise ValueError(
            f"Profile '{profile_path}' ends with '_locked' and must declare paper_locked: true."
        )

    if raw_lock is None:
        if paper_locked:
            raise ValueError(f"Profile '{profile_path}' declares paper_locked: true but has no paper_lock block.")
        return

    if not isinstance(raw_lock, dict):
        raise ValueError(f"Profile '{profile_path}' key 'paper_lock' must be a dictionary.")
    if not paper_locked:
        raise ValueError(
            f"Profile '{profile_path}' declares paper_lock metadata but is not marked paper_locked: true."
        )

    contract_id = str(raw_lock.get("contract_id", "") or raw_lock.get("paper_id", "")).strip()
    if not contract_id:
        raise ValueError(
            f"Profile '{profile_path}' paper_lock must declare contract_id "
            "(paper_id accepted as a legacy alias)."
        )

    required = {
        "expected_sample_count",
        "expected_family_count",
        "expected_type_count",
    }
    missing = sorted(required - set(raw_lock.keys()))
    if missing:
        raise ValueError(
            f"Profile '{profile_path}' paper_lock missing required keys: {missing}"
        )

    for key in ("expected_sample_count", "expected_family_count", "expected_type_count"):
        value = raw_lock.get(key)
        if not isinstance(value, int) or value <= 0:
            raise ValueError(
                f"Profile '{profile_path}' paper_lock.{key} must be a positive integer."
            )

    material_change = raw_lock.get("material_change_abs_delta_macro_f1_gt")
    if material_change is not None:
        try:
            if float(material_change) <= 0:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Profile '{profile_path}' paper_lock.material_change_abs_delta_macro_f1_gt "
                "must be a positive number."
            ) from exc

    lock_file = _resolve_repo_relative_path(raw_lock.get("sample_id_lock_file"))
    lock_status = str(raw_lock.get("sample_id_lock_status", "") or "").strip().lower()
    lock_todo = str(raw_lock.get("sample_id_lock_todo", "") or "").strip()
    if lock_file:
        if not Path(lock_file).exists():
            raise ValueError(
                f"Profile '{profile_path}' paper_lock.sample_id_lock_file does not exist: {lock_file}"
            )
    elif not lock_todo and lock_status not in {"unavailable", "todo", "not_recovered"}:
        raise ValueError(
            f"Profile '{profile_path}' paper_lock must provide either sample_id_lock_file "
            "or a documented sample_id_lock_todo/sample_id_lock_status."
        )


def configure_runtime_snapshot_lock(profile: dict[str, Any]) -> dict[str, Any]:
    """Apply runtime snapshot-lock pointers for a locked cohort profile when available."""
    contract = build_declared_contract(profile)
    if not contract.get("paper_locked", False):
        return contract

    sample_id_lock = contract.get("sample_id_lock", {})
    lock_path = str(sample_id_lock.get("path", "") or "").strip()
    if lock_path:
        setattr(app_config, "ENABLE_SNAPSHOT_LOCK", True)
        setattr(app_config, "SNAPSHOT_LOCK_FILE", lock_path)
    return contract


def enforce_publication_profile_lock(
    *,
    profile: dict[str, Any],
    effective_evidence_mode: bool,
) -> None:
    """Require ``paper_locked`` for publication-ready evidence runs."""
    if not is_publication_intended_profile(profile=profile, effective_evidence_mode=effective_evidence_mode):
        return
    if bool(profile.get("paper_locked", False)):
        return

    profile_id = str(profile.get("profile_id", "unknown") or "unknown").strip()
    suggestion = _suggest_locked_profile_id(profile_id)
    if suggestion:
        raise ValueError(
            f"[PROFILE] Publication-ready profile '{profile_id}' is unlocked and cannot run in evidence/publication mode. "
            f"Use '{suggestion}' instead."
        )
    raise ValueError(
        f"[PROFILE] Publication-ready profile '{profile_id}' is unlocked and cannot run in evidence/publication mode. "
        "Create or use a profile with paper_locked: true and locked cohort metadata."
    )


def is_publication_intended_profile(*, profile: dict[str, Any], effective_evidence_mode: bool) -> bool:
    """Return whether a profile should be treated as publication-ready."""
    profile_id = str(profile.get("profile_id", "") or "").strip().lower()
    if bool(effective_evidence_mode):
        return True
    if profile_id.startswith("paper"):
        return True
    if profile_id.endswith("_locked"):
        return True
    if isinstance(profile.get("paper_perturbation_axes"), list) and profile.get("paper_perturbation_axes"):
        return True
    if isinstance(profile.get("evidence_perturbation_axes"), list) and profile.get("evidence_perturbation_axes"):
        return True
    return False


def build_runtime_contract(
    *,
    profile: dict[str, Any],
    manifest_context: dict[str, Any],
    samples_df: pd.DataFrame,
    raise_on_mismatch: bool = True,
) -> dict[str, Any]:
    """Build and validate the runtime locked cohort contract for the observed cohort."""
    declared = build_declared_contract(profile)
    if not declared.get("paper_locked", False):
        return declared

    observed = {
        "sample_count": int(len(samples_df)),
        "family_count": _unique_count(samples_df, ("family_canonical", "family_id")),
        "type_count": _unique_count(samples_df, ("type_slug",)),
        "sample_id_hash": _sample_id_hash(samples_df),
    }
    expected = dict(declared.get("expected", {}))
    mismatches: list[str] = []
    if observed["sample_count"] != int(expected.get("sample_count", 0) or 0):
        mismatches.append(
            f"sample_count observed={observed['sample_count']} expected={expected.get('sample_count')}"
        )
    if observed["family_count"] != int(expected.get("family_count", 0) or 0):
        mismatches.append(
            f"family_count observed={observed['family_count']} expected={expected.get('family_count')}"
        )
    if observed["type_count"] != int(expected.get("type_count", 0) or 0):
        mismatches.append(
            f"type_count observed={observed['type_count']} expected={expected.get('type_count')}"
        )

    sample_id_lock = dict(declared.get("sample_id_lock", {}))
    lock_path = str(sample_id_lock.get("path", "") or "").strip()
    if lock_path:
        lock_meta = _read_lock_file_metadata(Path(lock_path))
        sample_id_lock.update(lock_meta)
        lock_count = int(lock_meta.get("lock_sample_count", 0) or 0)
        if lock_count and lock_count != observed["sample_count"]:
            mismatches.append(
                f"lock_sample_count observed={observed['sample_count']} lock_file={lock_count}"
            )

    db_query_contract = manifest_context.get("db_query_contract", {})
    db_snapshot = {
        "primary_db_name": str(getattr(db_config, "DB_NAME", "")),
        "permission_intel_db_name": str(getattr(db_config, "PERMISSION_INTEL_DB_NAME", "")),
        "db_host": str(getattr(db_config, "DB_HOST", "")),
        "db_query_contract": dict(db_query_contract) if isinstance(db_query_contract, dict) else {},
        "db_query_contract_hash": hash_payload(db_query_contract),
        "analysis_snapshot": dict(manifest_context.get("analysis_snapshot", {}) or {}),
        "canonical_historical_run_id": str(declared.get("canonical_historical_run_id", "")),
    }

    payload = {
        **declared,
        "observed": observed,
        "sample_id_lock": sample_id_lock,
        "db_snapshot": db_snapshot,
        "validation": {
            "checked": True,
            "status": "match" if not mismatches else "mismatch",
            "mismatches": mismatches,
        },
    }
    if mismatches and raise_on_mismatch:
        raise ValueError(_format_contract_mismatch_error(profile=profile, declared=declared, mismatches=mismatches))
    return payload


def _format_contract_mismatch_error(
    *,
    profile: dict[str, Any],
    declared: dict[str, Any],
    mismatches: list[str],
) -> str:
    """Build the canonical locked-cohort mismatch error message."""
    return (
        f"[COHORT_LOCK] Locked cohort contract mismatch for profile "
        f"{declared.get('profile_id', profile.get('profile_id', 'unknown'))}: "
        + "; ".join(mismatches)
    )


def build_declared_contract(profile: dict[str, Any]) -> dict[str, Any]:
    """Normalize declared locked-cohort metadata from a loaded profile."""
    profile_id = str(profile.get("profile_id", "unknown") or "unknown")
    paper_locked = bool(profile.get("paper_locked", False))
    raw_lock = profile.get("paper_lock", {}) if isinstance(profile.get("paper_lock"), dict) else {}
    if not paper_locked:
        return unresolved_cohort_contract_payload(profile_id=profile_id)

    sample_id_lock_path = _resolve_repo_relative_path(raw_lock.get("sample_id_lock_file"))
    has_sample_lock = bool(sample_id_lock_path)
    contract_status = declared_cohort_contract_status(has_sample_lock=has_sample_lock)
    enforcement_level = declared_cohort_enforcement_level(has_sample_lock=has_sample_lock)
    contract_id = str(raw_lock.get("contract_id", "") or raw_lock.get("paper_id", "") or profile_id)
    return {
        "paper_locked": True,
        "profile_id": profile_id,
        "contract_name": profile_id,
        "contract_id": contract_id,
        "paper_id": contract_id,
        "canonical_historical_run_id": str(raw_lock.get("canonical_historical_run_id", "") or ""),
        "baseline_artifact_root": _resolve_repo_relative_path(raw_lock.get("baseline_artifact_root")),
        "contract_status": contract_status,
        "cohort_lock_status": contract_status,
        "enforcement_level": enforcement_level,
        "expected": {
            "sample_count": int(raw_lock.get("expected_sample_count", 0) or 0),
            "family_count": int(raw_lock.get("expected_family_count", 0) or 0),
            "type_count": int(raw_lock.get("expected_type_count", 0) or 0),
            "type_scope": str(raw_lock.get("expected_type_scope", "") or ""),
            "time_window_start_utc": str(raw_lock.get("time_window_start_utc", "") or ""),
            "time_window_end_utc": str(raw_lock.get("time_window_end_utc", "") or ""),
            "material_change_abs_delta_macro_f1_gt": float(
                raw_lock.get(
                    "material_change_abs_delta_macro_f1_gt",
                    getattr(app_config, "PAPER_MATERIAL_CHANGE_ABS_DELTA_MACRO_F1", 0.02),
                )
            ),
        },
        "sample_id_lock": {
            "path": sample_id_lock_path,
            "present": has_sample_lock,
            "enforceable": has_sample_lock,
            "status": str(raw_lock.get("sample_id_lock_status", "") or ""),
            "source": str(raw_lock.get("sample_id_lock_source", "") or ""),
            "todo": str(raw_lock.get("sample_id_lock_todo", "") or ""),
        },
        "notes": str(raw_lock.get("notes", "") or ""),
        "validation": {"checked": False, "status": "declared_only", "mismatches": []},
    }


def _resolve_repo_relative_path(raw_path: object) -> str:
    value = str(raw_path or "").strip()
    if not value:
        return ""
    path = Path(value)
    if not path.is_absolute():
        path = repo_root() / path
    return str(path.resolve())


def _read_lock_file_metadata(lock_path: Path) -> dict[str, Any]:
    try:
        lock_df = pd.read_csv(lock_path)
    except Exception:
        return {
            "lock_sample_count": 0,
            "lock_sample_id_hash": "",
        }
    if "sample_id" not in lock_df.columns:
        return {
            "lock_sample_count": 0,
            "lock_sample_id_hash": "",
        }
    sample_ids = (
        pd.to_numeric(lock_df["sample_id"], errors="coerce")
        .dropna()
        .astype(int)
        .drop_duplicates()
        .sort_values()
        .tolist()
    )
    return {
        "lock_sample_count": int(len(sample_ids)),
        "lock_sample_id_hash": hash_payload(sample_ids),
    }


def _sample_id_hash(samples_df: pd.DataFrame) -> str:
    if "sample_id" not in samples_df.columns:
        return ""
    sample_ids = (
        pd.to_numeric(samples_df["sample_id"], errors="coerce")
        .dropna()
        .astype(int)
        .drop_duplicates()
        .sort_values()
        .tolist()
    )
    return hash_payload(sample_ids)


def _unique_count(samples_df: pd.DataFrame, preferred_columns: tuple[str, ...]) -> int:
    for column in preferred_columns:
        if column not in samples_df.columns:
            continue
        series = samples_df[column].fillna("").astype(str).str.strip()
        series = series[series != ""]
        if not series.empty:
            return int(series.nunique())
    return 0


def _suggest_locked_profile_id(profile_id: str) -> str:
    suggestions = {
        "paper2_primary": "malicious_temporal_stability_locked",
        "malicious_temporal_stability": "malicious_temporal_stability_locked",
        "paper2_primary_locked": "malicious_temporal_stability_locked",
        "banker": "banker_locked",
        "paper1_banker_locked": "banker_locked",
    }
    if profile_id in suggestions:
        return suggestions[profile_id]
    locked_candidate = f"{profile_id}_locked"
    locked_path = repo_root() / "profiles" / f"{locked_candidate}.yaml"
    if locked_path.exists():
        return locked_candidate
    return ""
