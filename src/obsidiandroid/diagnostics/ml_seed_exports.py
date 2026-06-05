"""Minimum deep-learning seed exports for the post-V3 Neptune/Iapetus phase."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.common import output_hygiene as oh


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _resolve_existing_path(diagnostics_dir: Path, stem: str, run_id: str, suffix: str) -> Path | None:
    run_path = diagnostics_dir / f"{stem}_{run_id}{suffix}"
    if run_path.is_file():
        return run_path
    latest = diagnostics_dir / f"{stem}.latest{suffix}"
    if latest.is_file():
        return latest
    return None


def _build_sample_label_fact(
    samples_df: pd.DataFrame | None,
    *,
    profile: dict[str, Any],
) -> pd.DataFrame:
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty:
        return pd.DataFrame()
    training_field = str(profile.get("training_label_field", "") or "").strip() or "family_id"
    out = pd.DataFrame({"sample_id": samples_df["sample_id"]})
    for column in (
        "family_id",
        "family_canonical",
        "type_slug",
        "sha256",
        "sample_label_kind",
        "package_name",
    ):
        if column in samples_df.columns:
            out[column] = samples_df[column]
    if training_field == "type_slug" and "type_slug" in samples_df.columns:
        out["supervised_label"] = samples_df["type_slug"]
        out["supervised_label_namespace"] = "malware_type_slug"
    elif training_field == "family_within_type":
        family = samples_df.get("family_canonical", pd.Series([""] * len(samples_df), index=samples_df.index)).fillna("").astype(str).str.strip()
        type_slug = samples_df.get("type_slug", pd.Series([""] * len(samples_df), index=samples_df.index)).fillna("").astype(str).str.strip()
        combined = pd.Series([""] * len(samples_df), index=samples_df.index, dtype="object")
        mask = family.ne("") & type_slug.ne("")
        combined.loc[mask] = type_slug.loc[mask] + "::" + family.loc[mask]
        out["supervised_label"] = combined
        out["supervised_label_namespace"] = "malware_family_within_type"
    else:
        label_col = "family_id" if "family_id" in samples_df.columns else "family_canonical"
        out["supervised_label"] = samples_df[label_col]
        out["supervised_label_namespace"] = "malware_family"
    out["training_label_field"] = training_field
    out["profile_id"] = str(profile.get("profile_id", "") or "")
    return out


def _build_permission_vocabulary(diagnostics_dir: Path, run_id: str) -> dict[str, Any]:
    alias_json = _resolve_existing_path(diagnostics_dir, "permission_alias_map", run_id, ".json")
    alias_csv = _resolve_existing_path(diagnostics_dir, "permission_alias_map", run_id, ".csv")
    entries: list[dict[str, Any]] = []
    if alias_json is not None:
        payload = _read_json(alias_json)
        rows = payload.get("aliases") if isinstance(payload.get("aliases"), list) else payload.get("rows", [])
        if isinstance(rows, list):
            entries = [row for row in rows if isinstance(row, dict)]
    elif alias_csv is not None:
        df = _read_csv_if_exists(alias_csv)
        if not df.empty:
            entries = df.to_dict(orient="records")
    return {
        "vocabulary_version": "ml_permission_vocabulary_v1",
        "run_id": run_id,
        "source_artifact": str(alias_json or alias_csv or ""),
        "entry_count": len(entries),
        "entries": entries,
    }


def _build_permission_pattern_fact(diagnostics_dir: Path, run_id: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    specs = (
        ("permission_type_enrichment", "type_vs_global"),
        ("permission_family_enrichment", "family_vs_global"),
        ("family_permission_similarity", "family_vs_type"),
        ("type_permission_similarity", "family_vs_type"),
    )
    for stem, scope in specs:
        path = _resolve_existing_path(diagnostics_dir, stem, run_id, ".csv")
        if path is None:
            continue
        df = _read_csv_if_exists(path)
        if df.empty:
            continue
        chunk = df.copy()
        chunk["comparison_scope"] = scope
        chunk["source_artifact"] = path.name
        frames.append(chunk)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def _build_split_export(diagnostics_dir: Path, run_id: str, manifest: dict[str, Any]) -> pd.DataFrame:
    split_meta = manifest.get("split") if isinstance(manifest.get("split"), dict) else {}
    split_path = str(split_meta.get("split_audit_path", "") or "").strip()
    if not split_path:
        split_path = str(getattr(app_config, "RUNTIME_SPLIT_AUDIT_PATH", "") or "").strip()
    if split_path:
        df = _read_csv_if_exists(Path(split_path))
        if not df.empty:
            return df
    for stem in (f"split_freeze_headline_{run_id}", "split_audit"):
        path = _resolve_existing_path(diagnostics_dir, stem.replace(f"_{run_id}", ""), run_id, ".csv")
        if path is not None:
            df = _read_csv_if_exists(path)
            if not df.empty:
                return df
    headline = diagnostics_dir / f"split_freeze_headline_{run_id}.csv"
    return _read_csv_if_exists(headline)


def _build_ml_run_manifest(
    *,
    run_id: str,
    profile: dict[str, Any],
    manifest: dict[str, Any],
    manifest_context: dict[str, Any] | None,
) -> dict[str, Any]:
    ctx = manifest_context if isinstance(manifest_context, dict) else {}
    return {
        "export_version": "ml_run_manifest_v1",
        "run_id": run_id,
        "profile_id": str(profile.get("profile_id", "") or manifest.get("profile_id", "")),
        "training_label_field": str(profile.get("training_label_field", "") or "family_id"),
        "cohort_size": int(manifest.get("cohort_size", 0) or 0),
        "train_sample_count": manifest.get("train_sample_count"),
        "test_sample_count": manifest.get("test_sample_count"),
        "split_hash": (manifest.get("split") or {}).get("split_hash") if isinstance(manifest.get("split"), dict) else None,
        "dataset_hash": manifest.get("dataset_hash"),
        "feature_matrix_cols_post_prune": manifest.get("feature_matrix_cols_post_prune"),
        "trained_models": list(manifest.get("trained_models", []) or []),
        "claim_surface": str(ctx.get("claim_surface", "") or manifest.get("claim_surface_label", "")),
        "run_mode": str(ctx.get("run_mode", "") or getattr(app_config, "RUNTIME_RUN_MODE", "")),
        "seed_artifact_refs": {
            "v3_label_contract": f"v3_label_contract_{run_id}.json",
            "permission_pattern_contract": f"permission_pattern_contract_{run_id}.json",
            "taxonomy_target_surfaces": f"taxonomy_target_surfaces_{run_id}.json",
            "run_manifest": "run_manifest.json",
        },
        "downstream_phase": "neptune_iapetus_deep_learning_prep",
        "notes": "Curated seed export only; does not train or run deep-learning models.",
    }


def export_ml_seed_artifacts(
    *,
    diagnostics_dir: Path,
    run_id: str,
    profile: dict[str, Any],
    samples_df: pd.DataFrame | None,
    manifest: dict[str, Any],
    manifest_context: dict[str, Any] | None = None,
) -> list[str]:
    """Write minimum ML seed artifacts from existing run outputs."""
    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    label_df = _build_sample_label_fact(samples_df, profile=profile)
    label_path = diagnostics_dir / f"ml_sample_label_fact_{run_id}.csv"
    label_df.to_csv(label_path, index=False)
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=label_path.name,
        csv_text=label_path.read_text(encoding="utf-8"),
        global_latest_name="ml_sample_label_fact.latest.csv",
    )
    paths.append(str(label_path))

    vocab_payload = _build_permission_vocabulary(diagnostics_dir, run_id)
    vocab_path = diagnostics_dir / f"ml_permission_vocabulary_{run_id}.json"
    vocab_path.write_text(json.dumps(vocab_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    oh.mirror_json_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=vocab_path.name,
        payload=vocab_payload,
        global_latest_name="ml_permission_vocabulary.latest.json",
    )
    paths.append(str(vocab_path))

    ml_manifest = _build_ml_run_manifest(
        run_id=run_id,
        profile=profile,
        manifest=manifest,
        manifest_context=manifest_context,
    )
    ml_manifest_path = diagnostics_dir / f"ml_run_manifest_{run_id}.json"
    ml_manifest_path.write_text(json.dumps(ml_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    oh.mirror_json_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=ml_manifest_path.name,
        payload=ml_manifest,
        global_latest_name="ml_run_manifest.latest.json",
    )
    paths.append(str(ml_manifest_path))

    pattern_df = _build_permission_pattern_fact(diagnostics_dir, run_id)
    if not pattern_df.empty:
        pattern_path = diagnostics_dir / f"ml_permission_pattern_fact_{run_id}.csv"
        pattern_df.to_csv(pattern_path, index=False)
        oh.mirror_csv_text_run_then_global(
            diagnostics_dir=diagnostics_dir,
            run_filename=pattern_path.name,
            csv_text=pattern_path.read_text(encoding="utf-8"),
            global_latest_name="ml_permission_pattern_fact.latest.csv",
        )
        paths.append(str(pattern_path))

    split_df = _build_split_export(diagnostics_dir, run_id, manifest)
    if not split_df.empty:
        split_path = diagnostics_dir / f"ml_train_validation_test_split_{run_id}.csv"
        split_df.to_csv(split_path, index=False)
        oh.mirror_csv_text_run_then_global(
            diagnostics_dir=diagnostics_dir,
            run_filename=split_path.name,
            csv_text=split_path.read_text(encoding="utf-8"),
            global_latest_name="ml_train_validation_test_split.latest.csv",
        )
        paths.append(str(split_path))

    return paths
