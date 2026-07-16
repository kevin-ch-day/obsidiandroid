"""Immutable filesystem source snapshots for the frozen Android benchmark.

This module deliberately has no database imports.  Production extraction is a
separately authorized concern; benchmark code consumes only a sealed package.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from obsidiandroid.common.hash_utils import hash_payload
from obsidiandroid.features.av_detection_contract import classify_av_row
from obsidiandroid.pipeline.engine_normalization import canonicalize_engine_name


SNAPSHOT_SCHEMA_VERSION = "frozen_latest_state_source_snapshot_v1"
SNAPSHOT_STATES = ("DRAFT", "EXTRACTED", "VALIDATED", "SEALED")
MAX_CANONICAL_EXTRACTION_WINDOW_SECONDS = 300
REQUIRED_EXTRACTS = (
    "cohort_candidates", "android_metadata", "vt_wide_rows", "vt_long_normalized",
    "permission_observations", "permission_knowledge", "taxonomy_aliases",
    "engine_metadata", "duplicate_label_audit",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_csv(frame: pd.DataFrame) -> bytes:
    return frame.sort_index(axis=1).sort_values(list(frame.columns), kind="stable", na_position="first").to_csv(index=False, lineterminator="\n").encode("utf-8") if not frame.empty else b"\n"


def _frame_hash(frame: pd.DataFrame) -> str:
    return hashlib.sha256(_canonical_csv(frame)).hexdigest()


def _safe_relative(root: Path, relative: str) -> Path:
    if Path(relative).is_absolute():
        raise ValueError("Snapshot evidence path must be a non-symlink relative path inside the snapshot root.")
    raw = root / relative
    candidate = raw.resolve()
    if raw.is_symlink() or root not in candidate.parents:
        raise ValueError("Snapshot evidence path must be a non-symlink relative path inside the snapshot root.")
    if "latest" in {part for part in re.split(r"[._-]+", Path(relative).name.lower()) if part}:
        raise ValueError("Snapshot evidence cannot use a latest-style filename.")
    return candidate


def _write_frame(root: Path, name: str, snapshot_id: str, frame: pd.DataFrame) -> dict[str, Any]:
    relative = f"{name}_{snapshot_id}.csv.gz"
    path = _safe_relative(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        frame.to_csv(handle, index=False, lineterminator="\n")
    return {
        "name": name, "path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "ordered_content_hash": _frame_hash(frame), "row_count": int(len(frame)),
        "primary_keys": ["sample_id"] if "sample_id" in frame.columns else [],
    }


def _manifest_integrity(manifest: Mapping[str, Any]) -> str:
    """Hash all manifest claims except the self-referential integrity field."""
    payload = {key: value for key, value in manifest.items() if key != "manifest_integrity_hash"}
    return hash_payload(payload)


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    manifest["manifest_integrity_hash"] = _manifest_integrity(manifest)
    path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _wide_row_hash(row: Mapping[str, Any]) -> str:
    return hash_payload({str(key): "" if pd.isna(value) else str(value) for key, value in sorted(row.items())})


def derive_normalized_vt_rows(
    wide_rows: pd.DataFrame,
    *,
    snapshot_id: str,
    engine_columns: list[str],
    engine_aliases: Mapping[str, str] | None = None,
    snapshot_created_at_utc: str,
) -> pd.DataFrame:
    """Derive long AV evidence exclusively from sealed wide snapshot rows."""
    required = {"sample_id", "updated_at"}
    if missing := required.difference(wide_rows.columns):
        raise ValueError(f"Snapshot VT wide rows missing: {sorted(missing)}")
    if missing := set(engine_columns).difference(wide_rows.columns):
        raise ValueError(f"Snapshot VT engine columns missing: {sorted(missing)}")
    output: list[dict[str, Any]] = []
    for row in wide_rows.to_dict("records"):
        row_hash = _wide_row_hash(row)
        for engine in engine_columns:
            raw_result = row.get(engine)
            avobs, avdet, status = classify_av_row(pd.Series({"result": raw_result}))
            output.append({
                "snapshot_id": snapshot_id, "sample_id": int(row["sample_id"]),
                "snapshot_row_id": f"{snapshot_id}:{row_hash}", "raw_engine_name": engine,
                "canonical_engine_name": canonicalize_engine_name(engine, dict(engine_aliases or {})),
                "raw_result": "" if pd.isna(raw_result) else str(raw_result),
                "normalized_status": status, "avdet": int(avdet), "avobs": int(avobs),
                "source_wide_row_hash": row_hash, "source_updated_at": str(row["updated_at"]),
                "snapshot_created_at_utc": snapshot_created_at_utc,
            })
    return pd.DataFrame(output).sort_values(["sample_id", "raw_engine_name"], kind="stable").reset_index(drop=True)


def govern_duplicate_authority_rows(rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Select one non-conflicting authority row per sample with a full audit."""
    required = {"sample_id", "family_id", "family_canonical"}
    if missing := required.difference(rows.columns):
        raise ValueError(f"Authority candidates missing: {sorted(missing)}")
    work = rows.copy()
    work["sample_id"] = pd.to_numeric(work["sample_id"], errors="raise").astype(int)
    work["family_id"] = pd.to_numeric(work["family_id"], errors="raise").astype(int)
    work["family_canonical"] = work["family_canonical"].astype(str).str.strip()
    priority = work["authority_priority"] if "authority_priority" in work else pd.Series(0, index=work.index)
    work["authority_priority"] = pd.to_numeric(priority, errors="coerce").fillna(0).astype(int)
    selected: list[pd.DataFrame] = []
    audit: list[dict[str, Any]] = []
    for sample_id, group in work.groupby("sample_id", sort=True):
        labels = group[["family_id", "family_canonical"]].drop_duplicates()
        if len(labels) != 1:
            audit.append({"sample_id": int(sample_id), "candidate_count": int(len(group)), "status": "conflicting_family_identity", "selected": False})
            raise ValueError(f"DUPLICATE_AUTHORITY_CONFLICT sample_id={sample_id}")
        chosen = group.sort_values(["authority_priority", "family_id", "family_canonical"], ascending=[False, True, True], kind="stable").iloc[[0]]
        selected.append(chosen)
        audit.append({"sample_id": int(sample_id), "candidate_count": int(len(group)), "status": "selected_single" if len(group) == 1 else "selected_duplicate_same_identity", "selected": True})
    return pd.concat(selected, ignore_index=True), pd.DataFrame(audit)


@dataclass(frozen=True)
class SealedSnapshot:
    root: Path
    manifest: dict[str, Any]


def validate_sealed_snapshot(root: Path, *, expected_schema_version: str = SNAPSHOT_SCHEMA_VERSION) -> SealedSnapshot:
    supplied_root = Path(root)
    if supplied_root.is_symlink():
        raise ValueError("Snapshot root cannot be a symlink.")
    root = supplied_root.resolve()
    manifest_path = root / "source_snapshot_manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Snapshot manifest is missing or symlinked.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("manifest_integrity_hash") != _manifest_integrity(manifest):
        raise ValueError("Snapshot manifest integrity hash mismatch.")
    if manifest.get("schema_version") != expected_schema_version:
        raise ValueError("Snapshot schema version mismatch.")
    if manifest.get("state") != "SEALED":
        raise ValueError("Snapshot provider requires a SEALED snapshot.")
    if [item.get("state") for item in manifest.get("lifecycle_history", [])] != list(SNAPSHOT_STATES):
        raise ValueError("Snapshot lifecycle history is incomplete or reordered.")
    if manifest.get("temporal_limitation_classification") != "MUTABLE_LATEST_STATE_CAPTURE":
        raise ValueError("Snapshot temporal limitation declaration is invalid.")
    sequence = manifest.get("extraction_sequence") or {}
    required_sequence = {
        "primary_started_at_utc", "primary_completed_at_utc",
        "permission_started_at_utc", "permission_completed_at_utc",
    }
    if required_sequence.difference(sequence):
        raise ValueError("Snapshot extraction sequence is incomplete.")
    try:
        timestamps = {
            key: datetime.fromisoformat(str(sequence[key]).replace("Z", "+00:00"))
            for key in required_sequence
        }
    except ValueError as exc:
        raise ValueError("Snapshot extraction sequence timestamps are invalid.") from exc
    primary_started = timestamps["primary_started_at_utc"]
    permission_completed = timestamps["permission_completed_at_utc"]
    if not (timestamps["primary_started_at_utc"] <= timestamps["primary_completed_at_utc"] <= timestamps["permission_started_at_utc"] <= permission_completed):
        raise ValueError("Snapshot extraction sequence is chronologically invalid.")
    window = float(manifest.get("cross_database_extraction_window_seconds", -1))
    if abs((permission_completed - primary_started).total_seconds() - window) > 1.0:
        raise ValueError("Snapshot extraction window does not match the recorded sequence.")
    if window < 0 or (manifest.get("classification") == "canonical" and window > MAX_CANONICAL_EXTRACTION_WINDOW_SECONDS):
        raise ValueError("Snapshot extraction window violates canonical policy.")
    entries = manifest.get("extracts") or []
    names = {entry.get("name") for entry in entries}
    if set(REQUIRED_EXTRACTS) != names:
        raise ValueError("Snapshot manifest has missing or unexpected extracts.")
    sums: list[str] = []
    for entry in entries:
        path = _safe_relative(root, str(entry.get("path", "")))
        if not path.is_file():
            raise ValueError(f"Snapshot extract missing: {entry.get('name')}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry.get("sha256"):
            raise ValueError(f"Snapshot extract hash mismatch: {entry.get('name')}")
        frame = pd.read_csv(path, compression="gzip")
        if _frame_hash(frame) != entry.get("ordered_content_hash"):
            raise ValueError(f"Snapshot extract ordered content hash mismatch: {entry.get('name')}")
        if int(len(frame)) != int(entry.get("row_count", -1)):
            raise ValueError(f"Snapshot extract row count mismatch: {entry.get('name')}")
        sums.append(f"{entry['sha256']}  {entry['path']}")
    sums_path = _safe_relative(root, "SHA256SUMS")
    if not sums_path.is_file() or sums_path.read_text(encoding="utf-8").splitlines() != sorted(sums):
        raise ValueError("Snapshot SHA256SUMS mismatch.")
    vt_contract = manifest.get("vt_source_contract") or {}
    wide_entry = next(entry for entry in entries if entry["name"] == "vt_wide_rows")
    long_entry = next(entry for entry in entries if entry["name"] == "vt_long_normalized")
    wide = pd.read_csv(_safe_relative(root, wide_entry["path"]), compression="gzip")
    observed_long = pd.read_csv(_safe_relative(root, long_entry["path"]), compression="gzip", keep_default_na=False)
    expected_long = derive_normalized_vt_rows(
        wide,
        snapshot_id=str(manifest["snapshot_id"]),
        engine_columns=list(vt_contract.get("engine_columns") or []),
        engine_aliases=dict(manifest.get("engine_alias_snapshot") or {}),
        snapshot_created_at_utc=str(manifest["created_at_utc"]),
    )
    try:
        pd.testing.assert_frame_equal(observed_long, expected_long)
    except AssertionError as exc:
        raise ValueError("Snapshot VT long derivative is not reproducible from sealed wide rows.") from exc
    return SealedSnapshot(root, manifest)


def create_synthetic_sealed_snapshot(root: Path, *, extraction_window_seconds: float = 5.0) -> SealedSnapshot:
    """Create a complete synthetic fixture; never calls a database."""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ValueError("Synthetic snapshot root must be empty.")
    if extraction_window_seconds < 0:
        raise ValueError("Synthetic snapshot extraction window cannot be negative.")
    created = _utc_now()
    created_dt = datetime.fromisoformat(created)
    primary_completed = created_dt + timedelta(seconds=float(extraction_window_seconds) / 3)
    permission_started = created_dt + timedelta(seconds=2 * float(extraction_window_seconds) / 3)
    permission_completed = created_dt + timedelta(seconds=float(extraction_window_seconds))
    cohort_rows, metadata_rows, permission_rows, wide_rows = [], [], [], []
    names = ("alpha", "bravo", "charlie")
    for family, canonical in enumerate(names):
        for index in range(20):
            sample_id = family * 100 + index
            base = {"sample_id": sample_id, "sha256": f"{family:02x}{index:02x}".ljust(64, "0"), "family_id": family, "family_canonical": canonical, "android_package_name": f"com.synthetic.{canonical}.p{index}", "authority_priority": 100}
            cohort_rows.append(base)
            if index == 0: cohort_rows.append({**base, "authority_priority": 10})
            metadata_rows.append({"sample_id": sample_id, "meta__target_min_version": 21 if index % 2 else None, "meta__target_sdk_version": 30 if index % 3 else None})
            permission_rows.append({"sample_id": sample_id, "permission_string": "android.permission.CAMERA", "permission_string_norm": "android.permission.camera", "permission_source": "AOSP", "is_aosp_dict_match": 1, "protection_level": "DANGEROUS"})
            wide_rows.append({"sample_id": sample_id, "updated_at": f"2026-07-16T00:{index:02d}:00Z", "alpha_engine": "undetected", "beta_engine": "Trojan.X" if family else "harmless"})
    selected, audit = govern_duplicate_authority_rows(pd.DataFrame(cohort_rows))
    frames = {
        "cohort_candidates": selected.drop(columns="authority_priority"),
        "android_metadata": pd.DataFrame(metadata_rows),
        "vt_wide_rows": pd.DataFrame(wide_rows),
        "permission_observations": pd.DataFrame(permission_rows),
        "permission_knowledge": pd.DataFrame([
            {"knowledge_kind": "permission_dictionary", "payload_json": json.dumps([{"permission_string_norm": "android.permission.camera", "permission_authority": "AOSP"}])},
            {"knowledge_kind": "authority_classification", "payload_json": json.dumps([{"permission_string_norm": "android.permission.camera", "authority": "AOSP"}])},
            {"knowledge_kind": "protection_level_classification", "payload_json": json.dumps([{"permission_string_norm": "android.permission.camera", "protection_level": "DANGEROUS"}])},
            {"knowledge_kind": "approved_oem_google_tokens", "payload_json": json.dumps([])},
            {"knowledge_kind": "alias_map", "payload_json": json.dumps({})},
            {"knowledge_kind": "known_missing_protection_policy", "payload_json": json.dumps("retain_known_token_in_known_count_exclude_from_protection_group")},
        ]),
        "taxonomy_aliases": pd.DataFrame({"family_id": [0, 1, 2], "family_canonical": list(names), "active": [True, True, True], "alias": ["a", "b", "c"]}),
        "engine_metadata": pd.DataFrame({"engine_name": ["alpha_engine", "beta_engine"], "active": [1, 1], "trusted": [0, 0]}),
        "duplicate_label_audit": audit,
    }
    snapshot_id = "snapshot_" + hash_payload({name: _frame_hash(frame) for name, frame in sorted(frames.items())} | {"vt_wide_rows": _frame_hash(frames["vt_wide_rows"]), "created": created})[:20]
    frames["vt_long_normalized"] = derive_normalized_vt_rows(frames["vt_wide_rows"], snapshot_id=snapshot_id, engine_columns=["alpha_engine", "beta_engine"], engine_aliases={}, snapshot_created_at_utc=created)
    extract_source = {
        "cohort_candidates": ("synthetic_primary", "family_authority_view"),
        "android_metadata": ("synthetic_primary", "android_metadata_view"),
        "vt_wide_rows": ("synthetic_primary", "virustotal_sample_vendor_engine_verdicts"),
        "vt_long_normalized": ("derived_from_sealed_snapshot", "vt_wide_rows"),
        "permission_observations": ("synthetic_permission", "permission_observations"),
        "permission_knowledge": ("synthetic_permission", "permission_knowledge"),
        "taxonomy_aliases": ("synthetic_primary", "taxonomy_aliases"),
        "engine_metadata": ("synthetic_primary", "engine_metadata"),
        "duplicate_label_audit": ("derived_from_sealed_snapshot", "authority_governance"),
    }
    extracts = []
    for name in REQUIRED_EXTRACTS:
        entry = _write_frame(root, name, snapshot_id, frames[name])
        database, source_object = extract_source[name]
        entry.update({
            "source_database": database,
            "source_object": source_object,
            "query_hash": hash_payload({"synthetic": name}),
            "extraction_timestamp_utc": created,
            "temporal_classification": "MUTABLE_LATEST_STATE_CAPTURE" if database != "derived_from_sealed_snapshot" else "DERIVED_FROM_SEALED_SNAPSHOT",
        })
        extracts.append(entry)
    manifest = {
        "snapshot_id": snapshot_id, "schema_version": SNAPSHOT_SCHEMA_VERSION, "state": "SEALED",
        "lifecycle_history": [{"state": state, "at_utc": created} for state in SNAPSHOT_STATES],
        "classification": "synthetic_validation", "created_at_utc": created, "as_of_utc": created,
        "source_commit": "synthetic", "extractor_version": "synthetic_fixture_v1",
        "primary_database_identity": "synthetic_primary", "permission_database_identity": "synthetic_permission",
        "source_query_hashes": {name: hash_payload({"synthetic": name}) for name in REQUIRED_EXTRACTS},
        "temporal_limitation_classification": "MUTABLE_LATEST_STATE_CAPTURE",
        "vt_temporal_semantics": "mutable latest-state row captured at snapshot extraction time",
        "engine_alias_snapshot": {}, "cross_database_atomicity": "not guaranteed",
        "cross_database_extraction_window_seconds": float(extraction_window_seconds), "extracts": extracts,
        "extraction_sequence": {
            "primary_started_at_utc": created,
            "primary_completed_at_utc": primary_completed.isoformat(),
            "permission_started_at_utc": permission_started.isoformat(),
            "permission_completed_at_utc": permission_completed.isoformat(),
        },
        "vt_source_contract": {
            "source_table": "virustotal_sample_vendor_engine_verdicts",
            "engine_columns": ["alpha_engine", "beta_engine"],
            "row_identity": "snapshot_row_id derived from complete source_wide_row_hash",
        },
    }
    _write_manifest(root / "source_snapshot_manifest.json", manifest)
    sums = sorted(f"{entry['sha256']}  {entry['path']}" for entry in extracts)
    (root / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return validate_sealed_snapshot(root)
