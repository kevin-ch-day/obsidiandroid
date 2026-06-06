"""V3 deep-learning handoff summary for operators and offline validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.json_io import read_json_dict
from obsidiandroid.diagnostics.run_artifact_resolve import resolve_run_artifact_path


def build_v3_dl_handoff_summary_payload(
    *,
    diagnostics_dir: Path,
    run_id: str,
    profile: dict[str, Any],
    manifest: dict[str, Any],
    manifest_context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Summarize Neptune/Iapetus seed-chain readiness from on-disk artifacts."""
    diagnostics_dir = Path(diagnostics_dir)
    ctx = manifest_context if isinstance(manifest_context, dict) else {}
    ml_manifest = read_json_dict(diagnostics_dir / f"ml_run_manifest_{run_id}.json")
    seed_refs = ml_manifest.get("seed_artifact_refs") if isinstance(ml_manifest.get("seed_artifact_refs"), dict) else {}
    optional_refs = (
        ml_manifest.get("optional_seed_artifact_refs")
        if isinstance(ml_manifest.get("optional_seed_artifact_refs"), dict)
        else {}
    )
    required = (
        "v3_label_contract",
        "permission_pattern_contract",
        "ml_sample_label_fact",
        "ml_permission_vocabulary",
    )
    missing_refs: list[str] = []
    present_refs: dict[str, str] = {}
    for key in required:
        filename = str(seed_refs.get(key, "") or "").strip()
        if not filename:
            missing_refs.append(key)
            continue
        path = diagnostics_dir / filename
        if not path.is_file():
            suffix = Path(filename).suffix
            stem = filename[: -len(suffix)] if suffix else filename
            if stem.endswith(f"_{run_id}"):
                stem = stem[: -len(f"_{run_id}")]
            resolved = resolve_run_artifact_path(diagnostics_dir, stem=stem, run_id=run_id, suffix=suffix)
            if resolved is None:
                missing_refs.append(key)
                continue
            path = resolved
        present_refs[key] = str(path)
    split_hash = None
    split_meta = manifest.get("split") if isinstance(manifest.get("split"), dict) else {}
    if isinstance(split_meta, dict):
        split_hash = str(split_meta.get("split_hash", "") or "").strip() or None
    split_export = optional_refs.get("ml_train_validation_test_split") or (
        f"ml_train_validation_test_split_{run_id}.csv"
    )
    split_path = diagnostics_dir / str(split_export)
    split_present = split_path.is_file()
    dataset_hash = str(
        ml_manifest.get("dataset_hash")
        or manifest.get("dataset_hash")
        or ctx.get("dataset_hash")
        or ""
    ).strip()
    vocab_count = int(ml_manifest.get("vocabulary_entry_count", 0) or 0)
    sample_rows = int(ml_manifest.get("sample_label_rows", 0) or 0)
    ready = (
        not missing_refs
        and bool(dataset_hash)
        and vocab_count > 0
        and sample_rows > 0
        and (not split_hash or split_present)
    )
    caveats: list[str] = []
    if missing_refs:
        caveats.append("missing required seed refs: " + ", ".join(missing_refs))
    if not dataset_hash:
        caveats.append("dataset_hash missing")
    if vocab_count <= 0:
        caveats.append("ml_permission_vocabulary entry_count is zero")
    if sample_rows <= 0:
        caveats.append("ml_sample_label_fact has zero rows")
    if split_hash and not split_present:
        caveats.append("split_hash present but ml_train_validation_test_split export missing")
    return {
        "summary_version": "v3_dl_handoff_summary_v1",
        "run_id": run_id,
        "profile_id": str(profile.get("profile_id", "") or manifest.get("profile_id", "")),
        "dl_seed_status": "ready" if ready else "incomplete",
        "dataset_hash": dataset_hash or None,
        "cohort_persistence_source": ctx.get("cohort_persistence_source"),
        "cohort_size": int(manifest.get("cohort_size", 0) or 0),
        "sample_label_rows": sample_rows,
        "vocabulary_entry_count": vocab_count,
        "split_hash": split_hash,
        "split_export_present": split_present,
        "seed_refs_present": present_refs,
        "missing_seed_refs": missing_refs,
        "optional_seed_refs": dict(optional_refs),
        "caveats": caveats,
    }


def build_v3_dl_handoff_observability_block(
    *,
    diagnostics_dir: Path,
    run_id: str,
    manifest: dict[str, Any],
    manifest_context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the ``v3_dl_handoff`` block for run observability summaries."""
    diagnostics_dir = Path(diagnostics_dir)
    ctx = manifest_context if isinstance(manifest_context, dict) else {}
    handoff_path = diagnostics_dir / f"v3_dl_handoff_summary_{run_id}.json"
    if handoff_path.is_file():
        handoff = read_json_dict(handoff_path)
    else:
        handoff = build_v3_dl_handoff_summary_payload(
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            profile={"profile_id": str(manifest.get("profile_id", "") or "")},
            manifest=manifest,
            manifest_context=ctx,
        )
    dataset_hash = str(
        handoff.get("dataset_hash")
        or manifest.get("dataset_hash")
        or ctx.get("dataset_hash")
        or ""
    ).strip()
    return {
        "dataset_hash": dataset_hash or None,
        "cohort_persistence_source": str(
            handoff.get("cohort_persistence_source") or ctx.get("cohort_persistence_source", "") or ""
        ).strip()
        or None,
        "dl_seed_status": handoff.get("dl_seed_status"),
        "vocabulary_entry_count": int(handoff.get("vocabulary_entry_count", 0) or 0) or None,
        "sample_label_rows": int(handoff.get("sample_label_rows", 0) or 0) or None,
        "split_hash": handoff.get("split_hash"),
        "split_export_present": bool(handoff.get("split_export_present")),
        "ml_run_manifest": str(diagnostics_dir / f"ml_run_manifest_{run_id}.json"),
        "ml_sample_label_fact": str(diagnostics_dir / f"ml_sample_label_fact_{run_id}.csv"),
        "ml_permission_vocabulary": str(diagnostics_dir / f"ml_permission_vocabulary_{run_id}.json"),
        "v3_dl_handoff_summary": str(handoff_path),
    }


def export_v3_dl_handoff_summary(
    *,
    diagnostics_dir: Path,
    run_id: str,
    profile: dict[str, Any],
    manifest: dict[str, Any],
    manifest_context: dict[str, Any] | None = None,
) -> Path:
    """Write run-scoped V3 DL handoff summary JSON."""
    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    payload = build_v3_dl_handoff_summary_payload(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile=profile,
        manifest=manifest,
        manifest_context=manifest_context,
    )
    path = diagnostics_dir / f"v3_dl_handoff_summary_{run_id}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    oh.mirror_json_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=path.name,
        payload=payload,
        global_latest_name="v3_dl_handoff_summary.latest.json",
    )
    return path
