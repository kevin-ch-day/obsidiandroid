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
from obsidiandroid.common.authority_taxonomy_terms import (
    taxonomy_count_drift_note,
    taxonomy_count_drift_semantics,
)
from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.common.repo_paths import repo_root
from obsidiandroid.database import db_config
from obsidiandroid.governance.cohort_lock_manifest import (
    load_lock_manifest,
    resolve_lock_manifest_path,
    validate_lock_manifest,
)


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
    manifest_path = resolve_lock_manifest_path(raw_lock)
    lock_status = str(raw_lock.get("sample_id_lock_status", "") or "").strip().lower()
    lock_todo = str(raw_lock.get("sample_id_lock_todo", "") or "").strip()
    if manifest_path is not None and manifest_path.exists():
        manifest = load_lock_manifest(raw_lock)
        assert manifest is not None
        validate_lock_manifest(manifest=manifest, manifest_path=manifest_path)
        lock_file = str(manifest.get("member_list_path", "") or "").strip() or lock_file
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
    runtime_snapshot_lock = dict(samples_df.attrs.get("snapshot_lock", {}) or {})
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

    validation_status = "match" if not mismatches else "mismatch"
    validation_severity = "error" if mismatches else "none"
    runtime_drift = _runtime_db_drift_summary(
        declared=declared,
        observed=observed,
        sample_id_lock=sample_id_lock,
        runtime_snapshot_lock=runtime_snapshot_lock,
        mismatches=mismatches,
    )
    taxonomy_drift = _taxonomy_label_drift_summary(
        declared=declared,
        observed=observed,
        sample_id_lock=sample_id_lock,
        runtime_snapshot_lock=runtime_snapshot_lock,
        mismatches=mismatches,
    )
    if runtime_drift is not None:
        validation_status = "degraded_live_db_drift"
        validation_severity = "warning"
        sample_id_lock["runtime_db_drift"] = runtime_drift
    elif taxonomy_drift is not None:
        validation_status = "degraded_taxonomy_label_drift"
        validation_severity = "warning"
        sample_id_lock["taxonomy_label_drift"] = taxonomy_drift

    payload = {
        **declared,
        "observed": observed,
        "sample_id_lock": sample_id_lock,
        "db_snapshot": db_snapshot,
        "validation": {
            "checked": True,
            "status": validation_status,
            "severity": validation_severity,
            "mismatches": mismatches,
        },
    }
    if runtime_drift is not None:
        payload["contract_status"] = "count_only_incomplete_sample_lock"
        payload["cohort_lock_status"] = "count_only_incomplete_sample_lock"
        payload["enforcement_level"] = "partial"
        payload["validation"]["warning"] = _format_runtime_db_drift_warning(
            profile=profile,
            runtime_drift=runtime_drift,
        )
    elif taxonomy_drift is not None:
        payload["contract_status"] = "membership_locked_taxonomy_drift"
        payload["cohort_lock_status"] = "membership_locked_taxonomy_drift"
        payload["enforcement_level"] = "partial"
        payload["validation"]["warning"] = _format_taxonomy_label_drift_warning(
            profile=profile,
            taxonomy_drift=taxonomy_drift,
        )
    if validation_status == "mismatch" and raise_on_mismatch:
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


def _format_runtime_db_drift_warning(
    *,
    profile: dict[str, Any],
    runtime_drift: dict[str, Any],
) -> str:
    """Explain degraded lock enforcement when a preserved sample lock outlives the live DB."""
    profile_id = str(profile.get("profile_id", "unknown") or "unknown")
    return (
        f"[COHORT_LOCK] Locked cohort drift for profile {profile_id}: preserved sample-id lock still exists, "
        f"but {int(runtime_drift.get('missing_from_db_count', 0) or 0)} locked sample(s) are absent from the "
        "current live DB cohort. Downgrading to count-only lock semantics for this run."
    )


def _format_taxonomy_label_drift_warning(
    *,
    profile: dict[str, Any],
    taxonomy_drift: dict[str, Any],
) -> str:
    """Explain degraded enforcement when sample membership is stable but labels changed."""
    profile_id = str(profile.get("profile_id", "unknown") or "unknown")
    return (
        f"[COHORT_LOCK] Locked cohort taxonomy drift for profile {profile_id}: sample-id membership still matches "
        "the preserved lock, but current live DB taxonomy changed family/type counts "
        f"(families observed={taxonomy_drift.get('observed_family_count')} expected={taxonomy_drift.get('expected_family_count')}; "
        f"types observed={taxonomy_drift.get('observed_type_count')} expected={taxonomy_drift.get('expected_type_count')}). "
        f"{taxonomy_count_drift_note(taxonomy_drift)} "
        "Continuing with partial lock semantics and recording the drift in run artifacts."
    )


def build_declared_contract(profile: dict[str, Any]) -> dict[str, Any]:
    """Normalize declared locked-cohort metadata from a loaded profile."""
    profile_id = str(profile.get("profile_id", "unknown") or "unknown")
    paper_locked = bool(profile.get("paper_locked", False))
    raw_lock = profile.get("paper_lock", {}) if isinstance(profile.get("paper_lock"), dict) else {}
    if not paper_locked:
        return unresolved_cohort_contract_payload(profile_id=profile_id)

    manifest_payload = load_lock_manifest(raw_lock)
    manifest_path = str(manifest_payload.get("manifest_path", "") or "") if isinstance(manifest_payload, dict) else ""
    manifest_member_list = (
        str(manifest_payload.get("member_list_path", "") or "").strip()
        if isinstance(manifest_payload, dict)
        else ""
    )
    sample_id_lock_path = manifest_member_list or _resolve_repo_relative_path(raw_lock.get("sample_id_lock_file"))
    has_sample_lock = bool(sample_id_lock_path)
    contract_status = declared_cohort_contract_status(has_sample_lock=has_sample_lock)
    enforcement_level = declared_cohort_enforcement_level(has_sample_lock=has_sample_lock)
    contract_id = str(
        raw_lock.get("contract_id", "")
        or raw_lock.get("paper_id", "")
        or (manifest_payload or {}).get("contract_id", "")
        or profile_id
    )
    manifest_expected = manifest_payload if isinstance(manifest_payload, dict) else {}
    time_window = manifest_expected.get("time_window", {}) if isinstance(manifest_expected.get("time_window"), dict) else {}
    baseline_artifact_root = (
        str(manifest_expected.get("baseline_artifact_root", "") or "")
        or _resolve_repo_relative_path(raw_lock.get("baseline_artifact_root"))
    )
    return {
        "paper_locked": True,
        "profile_id": profile_id,
        "contract_name": profile_id,
        "contract_id": contract_id,
        "paper_id": contract_id,
        "canonical_historical_run_id": str(
            (manifest_payload or {}).get("canonical_historical_run_id", "")
            or raw_lock.get("canonical_historical_run_id", "")
            or ""
        ),
        "baseline_artifact_root": baseline_artifact_root,
        "contract_status": contract_status,
        "cohort_lock_status": contract_status,
        "enforcement_level": enforcement_level,
        "expected": {
            "sample_count": int(
                (manifest_expected.get("sample_count", 0) or 0)
                or (raw_lock.get("expected_sample_count", 0) or 0)
            ),
            "family_count": int(
                (manifest_expected.get("family_count", 0) or 0)
                or (raw_lock.get("expected_family_count", 0) or 0)
            ),
            "type_count": int(
                (manifest_expected.get("type_count", 0) or 0)
                or (raw_lock.get("expected_type_count", 0) or 0)
            ),
            "type_scope": str(
                (manifest_expected.get("type_scope", "") or time_window.get("type_scope", "") or "")
                or raw_lock.get("expected_type_scope", "")
                or ""
            ),
            "time_window_start_utc": str(
                (time_window.get("start_utc", "") or "")
                or raw_lock.get("time_window_start_utc", "")
                or ""
            ),
            "time_window_end_utc": str(
                (time_window.get("end_utc", "") or "")
                or raw_lock.get("time_window_end_utc", "")
                or ""
            ),
            "time_window_semantics": str(
                (time_window.get("window_semantics", "") or "")
                or "start_inclusive_end_exclusive"
            ),
            "material_change_abs_delta_macro_f1_gt": float(
                raw_lock.get(
                    "material_change_abs_delta_macro_f1_gt",
                    getattr(app_config, "PAPER_MATERIAL_CHANGE_ABS_DELTA_MACRO_F1", 0.02),
                )
            ),
        },
        "sample_id_lock": {
            "path": sample_id_lock_path,
            "member_list_path": sample_id_lock_path,
            "present": has_sample_lock,
            "enforceable": has_sample_lock,
            "status": str(raw_lock.get("sample_id_lock_status", "") or ""),
            "source": str(raw_lock.get("sample_id_lock_source", "") or ""),
            "todo": str(raw_lock.get("sample_id_lock_todo", "") or ""),
            "lock_manifest_path": manifest_path,
            "lock_version": str((manifest_expected.get("lock_version", "") or "")),
            "created_at_utc": str((manifest_expected.get("created_at_utc", "") or "")),
            "cohort_hash": str((manifest_expected.get("cohort_hash", "") or "")),
            "taxonomy_hash": str((manifest_expected.get("taxonomy_hash", "") or "")),
            "sql_profile_version": str((manifest_expected.get("sql_profile_version", "") or "")),
            "profile_version": str((manifest_expected.get("profile_version", "") or "")),
            "top_family_share": manifest_expected.get("top_family_share"),
            "top_family_support": manifest_expected.get("top_family_support"),
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


def _runtime_db_drift_summary(
    *,
    declared: dict[str, Any],
    observed: dict[str, Any],
    sample_id_lock: dict[str, Any],
    runtime_snapshot_lock: dict[str, Any],
    mismatches: list[str],
) -> dict[str, Any] | None:
    """Return degraded lock metadata when live DB drift explains a preserved lock mismatch."""
    if not mismatches:
        return None
    lock_status = str(sample_id_lock.get("status", "") or "").strip().lower()
    if lock_status != "recovered_from_historical_artifact":
        return None
    if not bool(runtime_snapshot_lock.get("applied", False)):
        return None
    missing_from_db_count = int(runtime_snapshot_lock.get("missing_from_db_count", 0) or 0)
    if missing_from_db_count <= 0:
        return None
    lock_sample_count = int(sample_id_lock.get("lock_sample_count", 0) or 0)
    expected = dict(declared.get("expected", {}) or {})
    expected_sample_count = int(expected.get("sample_count", 0) or 0)
    expected_family_count = int(expected.get("family_count", 0) or 0)
    expected_type_count = int(expected.get("type_count", 0) or 0)
    matched_sample_count = int(runtime_snapshot_lock.get("matched_sample_count", observed["sample_count"]) or observed["sample_count"])
    if lock_sample_count <= 0 or matched_sample_count != observed["sample_count"]:
        return None
    if expected_sample_count and lock_sample_count != expected_sample_count:
        return None
    if observed["sample_count"] >= lock_sample_count:
        return None
    if expected_type_count and observed["type_count"] != expected_type_count:
        return None
    allowed_prefixes = (
        "sample_count observed=",
        "family_count observed=",
        "lock_sample_count observed=",
    )
    if any(not any(item.startswith(prefix) for prefix in allowed_prefixes) for item in mismatches):
        return None
    return {
        "reason": "live_db_missing_locked_members",
        "missing_from_db_count": missing_from_db_count,
        "lock_sample_count": lock_sample_count,
        "matched_sample_count": matched_sample_count,
        "expected_family_count": expected_family_count,
        "observed_family_count": observed["family_count"],
    }


def _taxonomy_label_drift_summary(
    *,
    declared: dict[str, Any],
    observed: dict[str, Any],
    sample_id_lock: dict[str, Any],
    runtime_snapshot_lock: dict[str, Any],
    mismatches: list[str],
) -> dict[str, Any] | None:
    """Return degraded metadata when curation changes labels inside a matched sample lock."""
    if not mismatches:
        return None
    if not bool(runtime_snapshot_lock.get("applied", False)):
        return None
    if int(runtime_snapshot_lock.get("missing_from_db_count", 0) or 0) != 0:
        return None
    matched_sample_count = int(runtime_snapshot_lock.get("matched_sample_count", observed["sample_count"]) or observed["sample_count"])
    if matched_sample_count != observed["sample_count"]:
        return None

    expected = dict(declared.get("expected", {}) or {})
    expected_sample_count = int(expected.get("sample_count", 0) or 0)
    expected_family_count = int(expected.get("family_count", 0) or 0)
    expected_type_count = int(expected.get("type_count", 0) or 0)
    if expected_sample_count and observed["sample_count"] != expected_sample_count:
        return None

    lock_sample_count = int(sample_id_lock.get("lock_sample_count", 0) or 0)
    if lock_sample_count and lock_sample_count != observed["sample_count"]:
        return None
    lock_sample_id_hash = str(sample_id_lock.get("lock_sample_id_hash", "") or "")
    if lock_sample_id_hash and lock_sample_id_hash != str(observed.get("sample_id_hash", "") or ""):
        return None

    allowed_prefixes = (
        "family_count observed=",
        "type_count observed=",
    )
    if any(not any(item.startswith(prefix) for prefix in allowed_prefixes) for item in mismatches):
        return None

    semantics = taxonomy_count_drift_semantics(
        expected_family_count=expected_family_count,
        observed_family_count=observed["family_count"],
        expected_type_count=expected_type_count,
        observed_type_count=observed["type_count"],
    )

    return {
        "reason": "taxonomy_label_drift_with_matched_sample_lock",
        "matched_sample_count": matched_sample_count,
        "lock_sample_count": lock_sample_count or matched_sample_count,
        "expected_family_count": expected_family_count,
        "observed_family_count": observed["family_count"],
        "expected_type_count": expected_type_count,
        "observed_type_count": observed["type_count"],
        **semantics,
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
