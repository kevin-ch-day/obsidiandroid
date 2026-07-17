"""Minimum deep-learning seed exports for the Neptune/Iapetus phase."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from config import app_config
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.diagnostics.cohort_persistence import resolve_effective_samples_df
from obsidiandroid.diagnostics.run_artifact_resolve import resolve_run_artifact_path
from obsidiandroid.common.run_slots import is_canonical_profile
from obsidiandroid.diagnostics.dl_handoff import (
    build_dl_handoff_summary_payload,
    export_dl_handoff_summary,
)


class MlSeedExportError(RuntimeError):
    """Raised when required ML seed exports cannot be produced."""


ML_SAMPLE_PERMISSION_FEATURE_COLUMNS = (
    "run_id",
    "profile_id",
    "sample_id",
    "sha256",
    "permission_name",
    "permission_present",
    "permission_authority_bucket",
    "permission_risk_tier",
    "permission_source",
)

_PERMISSION_AGGREGATE_COLUMN_NAMES = frozenset(
    {
        "perm__dangerous_count",
        "perm__normal_count",
        "perm__oem_count",
        "perm__total_count",
    }
)


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


def _resolve_existing_path(
    diagnostics_dir: Path,
    stem: str,
    run_id: str,
    suffix: str,
) -> Path | None:
    return resolve_run_artifact_path(
        diagnostics_dir,
        stem=stem,
        run_id=run_id,
        suffix=suffix,
    )


def _entries_from_alias_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("aliases")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    rows = payload.get("rows")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    alias_map = payload.get("alias_map")
    if isinstance(alias_map, dict):
        return [
            {"alias_from": str(key), "alias_to": str(value)}
            for key, value in sorted(alias_map.items(), key=lambda item: item[0])
        ]
    return []


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


def _alias_lookup_from_entries(entries: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for row in entries:
        alias_from = str(row.get("alias_from", "") or "").strip()
        alias_to = str(row.get("alias_to", "") or "").strip()
        if alias_from and alias_to:
            lookup[alias_from] = alias_to
    return lookup


def _permission_column_name(df: pd.DataFrame) -> str | None:
    for column in ("permission", "permission_string"):
        if column in df.columns:
            return column
    return None


def _collect_prevalence_permission_entries(
    diagnostics_dir: Path,
    run_id: str,
    *,
    alias_lookup: dict[str, str],
    alias_from: set[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Derive supervised permission tokens from prevalence tables when alias map is thin."""
    permission_stats: dict[str, dict[str, Any]] = {}
    source_artifacts: list[str] = []
    specs = (
        ("permission_prevalence_by_type", "type_level"),
        ("permission_prevalence_by_family", "family_level"),
    )
    for stem, scope in specs:
        path = _resolve_existing_path(diagnostics_dir, stem, run_id, ".csv")
        if path is None:
            continue
        df = _read_csv_if_exists(path)
        permission_column = _permission_column_name(df)
        if permission_column is None or df.empty:
            continue
        source_artifacts.append(str(path))
        prevalence_column = "prevalence_pct" if "prevalence_pct" in df.columns else None
        for _, row in df.iterrows():
            permission = str(row.get(permission_column, "") or "").strip()
            if not permission or permission in alias_from:
                continue
            canonical = alias_lookup.get(permission, permission)
            stats = permission_stats.setdefault(
                canonical,
                {
                    "permission": permission,
                    "canonical_permission": canonical,
                    "source_scope": set(),
                    "max_prevalence_pct": 0.0,
                },
            )
            stats["source_scope"].add(scope)
            if prevalence_column is not None:
                try:
                    prevalence = float(row.get(prevalence_column, 0.0) or 0.0)
                except (TypeError, ValueError):
                    prevalence = 0.0
                stats["max_prevalence_pct"] = max(float(stats["max_prevalence_pct"]), prevalence)

    entries: list[dict[str, Any]] = []
    for canonical in sorted(permission_stats):
        stats = permission_stats[canonical]
        entries.append(
            {
                "entry_kind": "permission",
                "permission": stats["permission"],
                "canonical_permission": canonical,
                "source_scope": sorted(stats["source_scope"]),
                "max_prevalence_pct": round(float(stats["max_prevalence_pct"]), 4),
            }
        )
    return entries, source_artifacts


def _build_permission_vocabulary(diagnostics_dir: Path, run_id: str) -> dict[str, Any]:
    alias_json = _resolve_existing_path(diagnostics_dir, "permission_alias_map", run_id, ".json")
    alias_csv = _resolve_existing_path(diagnostics_dir, "permission_alias_map", run_id, ".csv")
    alias_entries: list[dict[str, Any]] = []
    if alias_json is not None:
        alias_entries = _entries_from_alias_payload(_read_json(alias_json))
    elif alias_csv is not None:
        df = _read_csv_if_exists(alias_csv)
        if not df.empty:
            alias_entries = df.to_dict(orient="records")
    for row in alias_entries:
        row["entry_kind"] = "alias"

    alias_lookup = _alias_lookup_from_entries(alias_entries)
    permission_entries, prevalence_sources = _collect_prevalence_permission_entries(
        diagnostics_dir,
        run_id,
        alias_lookup=alias_lookup,
        alias_from=set(alias_lookup),
    )
    entries = alias_entries + permission_entries
    return {
        "vocabulary_version": "ml_permission_vocabulary_v2",
        "run_id": run_id,
        "source_artifact": str(alias_json or alias_csv or ""),
        "prevalence_source_artifacts": prevalence_sources,
        "alias_entry_count": len(alias_entries),
        "permission_entry_count": len(permission_entries),
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


def _permission_column_name_from_token(permission: str) -> str:
    sanitized = re.sub(r"[^a-z0-9]+", "_", str(permission or "").strip().lower()).strip("_") or "unknown"
    return f"perm__{sanitized}"


def _is_permission_feature_column(column: str) -> bool:
    name = str(column or "").strip()
    if not name.startswith("perm__") or name.startswith("perm_grp__"):
        return False
    if name in _PERMISSION_AGGREGATE_COLUMN_NAMES:
        return False
    if name.endswith("_count"):
        return False
    return True


def _permission_column_lookup(vocab_payload: dict[str, Any]) -> dict[str, str]:
    entries = vocab_payload.get("entries")
    if not isinstance(entries, list):
        return {}
    alias_lookup = _alias_lookup_from_entries([row for row in entries if isinstance(row, dict)])
    lookup: dict[str, str] = {}
    for row in entries:
        if not isinstance(row, dict):
            continue
        permission = str(row.get("permission", "") or row.get("canonical_permission", "") or "").strip()
        if not permission:
            continue
        column = _permission_column_name_from_token(permission)
        canonical = str(row.get("canonical_permission", "") or permission).strip()
        lookup[column] = alias_lookup.get(canonical, alias_lookup.get(permission, canonical or permission))
    return lookup


def _permission_name_from_column(column: str, column_lookup: dict[str, str]) -> str:
    token = str(column or "").strip()
    if token in column_lookup:
        return column_lookup[token]
    if token.startswith("perm__"):
        return token[len("perm__") :].replace("_", ".")
    return token


def _read_aligned_features(diagnostics_dir: Path, run_id: str) -> pd.DataFrame:
    path = oh.resolve_aligned_features_cache_path(diagnostics_dir, run_id)
    if not path.is_file():
        return pd.DataFrame()
    try:
        if str(path).endswith(".gz"):
            return pd.read_csv(path, compression="gzip")
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _build_sample_permission_feature(
    diagnostics_dir: Path,
    run_id: str,
    *,
    profile: dict[str, Any],
    label_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build present-only sparse long-form permission rows from aligned feature matrix."""
    features = _read_aligned_features(diagnostics_dir, run_id)
    if features.empty or "sample_id" not in features.columns:
        return pd.DataFrame(columns=list(ML_SAMPLE_PERMISSION_FEATURE_COLUMNS))

    perm_columns = [column for column in features.columns if _is_permission_feature_column(column)]
    if not perm_columns:
        return pd.DataFrame(columns=list(ML_SAMPLE_PERMISSION_FEATURE_COLUMNS))

    vocab_payload = _build_permission_vocabulary(diagnostics_dir, run_id)
    column_lookup = _permission_column_lookup(vocab_payload)
    profile_id = str(profile.get("profile_id", "") or "").strip()

    sha256_by_sample: dict[int, str] = {}
    if isinstance(label_df, pd.DataFrame) and not label_df.empty and "sample_id" in label_df.columns:
        if "sha256" in label_df.columns:
            for sample_id, sha256 in zip(label_df["sample_id"], label_df["sha256"]):
                if pd.isna(sha256):
                    continue
                token = str(sha256).strip()
                if str(sample_id).strip().isdigit() and token:
                    sha256_by_sample[int(sample_id)] = token

    melted = features[["sample_id", *perm_columns]].melt(
        id_vars=["sample_id"],
        value_vars=perm_columns,
        var_name="feature_column",
        value_name="feature_value",
    )
    melted["feature_value"] = pd.to_numeric(melted["feature_value"], errors="coerce").fillna(0)
    melted = melted[melted["feature_value"] > 0]
    if melted.empty:
        return pd.DataFrame(columns=list(ML_SAMPLE_PERMISSION_FEATURE_COLUMNS))

    melted["run_id"] = run_id
    melted["profile_id"] = profile_id
    melted["permission_name"] = melted["feature_column"].map(lambda col: _permission_name_from_column(col, column_lookup))
    melted["permission_present"] = 1
    melted["permission_authority_bucket"] = "unknown"
    melted["permission_risk_tier"] = "unknown"
    melted["permission_source"] = "aligned_features"
    melted["sample_id"] = pd.to_numeric(melted["sample_id"], errors="coerce")
    melted = melted[melted["sample_id"].notna()].copy()
    melted["sample_id"] = melted["sample_id"].astype(int)
    melted["sha256"] = melted["sample_id"].map(sha256_by_sample).fillna("")

    out = melted[list(ML_SAMPLE_PERMISSION_FEATURE_COLUMNS)].copy()
    return out.sort_values(["sample_id", "permission_name"]).reset_index(drop=True)


def _resolve_split_export_source(
    diagnostics_dir: Path,
    run_id: str,
    manifest: dict[str, Any],
) -> Path | None:
    """Resolve this run's frozen split ledger without copying it.

    The ML seed manifest stores a file name relative to ``diagnostics_dir``.
    A global ``latest`` ledger from another run is therefore not a valid
    substitute: it would produce a dangling relative reference and falsely
    report a canonical handoff as complete.
    """
    diagnostics_dir = Path(diagnostics_dir)

    def _run_local(path: Path | None) -> Path | None:
        if path is None or not path.is_file():
            return None
        try:
            path.resolve().relative_to(diagnostics_dir.resolve())
        except ValueError:
            return None
        return path

    # Prefer the exact run-scoped ledger before any runtime/global fallback.
    headline = _run_local(diagnostics_dir / f"split_freeze_headline_{run_id}.csv")
    if headline is not None:
        return headline

    split_meta = manifest.get("split") if isinstance(manifest.get("split"), dict) else {}
    split_path = str(split_meta.get("split_audit_path", "") or "").strip()
    if not split_path:
        split_path = str(getattr(app_config, "RUNTIME_SPLIT_AUDIT_PATH", "") or "").strip()
    if split_path:
        path = _run_local(Path(split_path))
        if path is not None:
            return path
    for stem in (f"split_freeze_headline_{run_id}", "split_audit"):
        path = _run_local(
            _resolve_existing_path(diagnostics_dir, stem.replace(f"_{run_id}", ""), run_id, ".csv")
        )
        if path is not None:
            return path
    return None


def _build_split_export(diagnostics_dir: Path, run_id: str, manifest: dict[str, Any]) -> pd.DataFrame:
    source_path = _resolve_split_export_source(diagnostics_dir, run_id, manifest)
    return _read_csv_if_exists(source_path) if source_path is not None else pd.DataFrame()


def _run_root_for_diagnostics(diagnostics_dir: Path) -> Path:
    return diagnostics_dir.parent if diagnostics_dir.name == "diagnostics" else diagnostics_dir


def _ref_if_exists(
    diagnostics_dir: Path,
    *,
    key: str,
    filename: str,
) -> tuple[str, str] | None:
    run_root = _run_root_for_diagnostics(diagnostics_dir)
    candidates = [diagnostics_dir / filename]
    if filename == "run_manifest.json":
        candidates = [run_root / filename, diagnostics_dir / filename]
    for path in candidates:
        if path.is_file():
            return key, filename
    return None


def _build_ml_run_manifest(
    *,
    run_id: str,
    profile: dict[str, Any],
    manifest: dict[str, Any],
    manifest_context: dict[str, Any] | None,
    seed_artifact_refs: dict[str, str],
    optional_seed_artifact_refs: dict[str, str],
    sample_label_rows: int,
    vocabulary_entry_count: int,
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
        "dataset_hash": manifest.get("dataset_hash") or ctx.get("dataset_hash"),
        "feature_matrix_cols_post_prune": manifest.get("feature_matrix_cols_post_prune"),
        "trained_models": list(manifest.get("trained_models", []) or []),
        "claim_surface": str(ctx.get("claim_surface", "") or manifest.get("claim_surface_label", "")),
        "run_mode": str(ctx.get("run_mode", "") or getattr(app_config, "RUNTIME_RUN_MODE", "")),
        "seed_artifact_refs": dict(seed_artifact_refs),
        "optional_seed_artifact_refs": dict(optional_seed_artifact_refs),
        "sample_label_rows": int(sample_label_rows),
        "vocabulary_entry_count": int(vocabulary_entry_count),
        "downstream_phase": "neptune_iapetus_deep_learning_prep",
        "notes": "Curated seed export only; does not train or run deep-learning models.",
    }


def refresh_persisted_permission_vocabulary(
    *,
    diagnostics_dir: Path,
    run_id: str,
) -> Path:
    """Rewrite on-disk ml_permission_vocabulary from current alias + prevalence sources."""
    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    vocab_payload = _build_permission_vocabulary(diagnostics_dir, run_id)
    vocab_path = diagnostics_dir / f"ml_permission_vocabulary_{run_id}.json"
    vocab_path.write_text(json.dumps(vocab_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    oh.mirror_json_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=vocab_path.name,
        payload=vocab_payload,
        global_latest_name="ml_permission_vocabulary.latest.json",
    )
    sync_ml_run_manifest_seed_counters(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        vocabulary_entry_count=int(vocab_payload.get("entry_count", 0) or 0),
    )
    return vocab_path


def sync_ml_run_manifest_seed_counters(
    *,
    diagnostics_dir: Path,
    run_id: str,
    vocabulary_entry_count: int | None = None,
    sample_label_rows: int | None = None,
) -> Path | None:
    """Patch persisted ml_run_manifest seed counters from on-disk or live rebuild sources."""
    diagnostics_dir = Path(diagnostics_dir)
    manifest_path = diagnostics_dir / f"ml_run_manifest_{run_id}.json"
    if not manifest_path.is_file():
        return None
    payload = _read_json(manifest_path)
    if not payload:
        return None

    if vocabulary_entry_count is None:
        vocab_payload = _build_permission_vocabulary(diagnostics_dir, run_id)
        vocabulary_entry_count = int(vocab_payload.get("entry_count", 0) or 0)
    payload["vocabulary_entry_count"] = int(vocabulary_entry_count)

    if sample_label_rows is None:
        label_path = _resolve_existing_path(diagnostics_dir, "ml_sample_label_fact", run_id, ".csv")
        if label_path is not None:
            label_df = _read_csv_if_exists(label_path)
            sample_label_rows = int(len(label_df))
    if sample_label_rows is not None:
        payload["sample_label_rows"] = int(sample_label_rows)

    run_root = diagnostics_dir.parent if diagnostics_dir.name == "diagnostics" else diagnostics_dir
    run_manifest_path = run_root / "run_manifest.json"
    if run_manifest_path.is_file():
        run_manifest = _read_json(run_manifest_path)
        dataset_hash = str(run_manifest.get("dataset_hash", "") or "").strip()
        if dataset_hash:
            payload["dataset_hash"] = dataset_hash

    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    oh.mirror_json_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=manifest_path.name,
        payload=payload,
        global_latest_name="ml_run_manifest.latest.json",
    )
    return manifest_path


def ensure_ml_split_export(
    *,
    diagnostics_dir: Path,
    run_id: str,
    manifest: dict[str, Any],
) -> Path | None:
    """Return the frozen split ledger and register it in the ML seed manifest.

    Historical runs may already contain the old copied ML-named export. New
    runs reference ``split_freeze_headline_<run_id>.csv`` directly.
    """
    diagnostics_dir = Path(diagnostics_dir)
    legacy_path = diagnostics_dir / f"ml_train_validation_test_split_{run_id}.csv"
    split_path = legacy_path if legacy_path.is_file() else _resolve_split_export_source(
        diagnostics_dir, run_id, manifest
    )
    if split_path is None:
        return None
    manifest_path = diagnostics_dir / f"ml_run_manifest_{run_id}.json"
    if manifest_path.is_file():
        payload = _read_json(manifest_path)
        optional_refs = payload.get("optional_seed_artifact_refs")
        if not isinstance(optional_refs, dict):
            optional_refs = {}
        optional_refs["ml_train_validation_test_split"] = split_path.name
        payload["optional_seed_artifact_refs"] = optional_refs
        manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        oh.mirror_json_text_run_then_global(
            diagnostics_dir=diagnostics_dir,
            run_filename=manifest_path.name,
            payload=payload,
            global_latest_name="ml_run_manifest.latest.json",
        )
    return split_path


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
    ctx = manifest_context if isinstance(manifest_context, dict) else {}
    if not str(manifest.get("dataset_hash", "") or "").strip() and str(ctx.get("dataset_hash", "") or "").strip():
        manifest = dict(manifest)
        manifest["dataset_hash"] = str(ctx.get("dataset_hash", "") or "").strip()
    paths: list[str] = []
    seed_refs: dict[str, str] = {}
    optional_refs: dict[str, str] = {}

    effective_samples = resolve_effective_samples_df(diagnostics_dir, run_id, samples_df)
    label_df = _build_sample_label_fact(effective_samples, profile=profile)
    if label_df.empty:
        raise MlSeedExportError(
            "ml_sample_label_fact requires a non-empty samples_df or aligned_labels export"
        )
    label_path = diagnostics_dir / f"ml_sample_label_fact_{run_id}.csv"
    label_df.to_csv(label_path, index=False)
    oh.mirror_csv_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=label_path.name,
        csv_text=label_path.read_text(encoding="utf-8"),
        global_latest_name="ml_sample_label_fact.latest.csv",
    )
    paths.append(str(label_path))
    seed_refs["ml_sample_label_fact"] = label_path.name

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
    seed_refs["ml_permission_vocabulary"] = vocab_path.name

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
        optional_refs["ml_permission_pattern_fact"] = pattern_path.name

    split_path = _resolve_split_export_source(diagnostics_dir, run_id, manifest)
    if split_path is not None:
        optional_refs["ml_train_validation_test_split"] = split_path.name

    permission_feature_df = _build_sample_permission_feature(
        diagnostics_dir,
        run_id,
        profile=profile,
        label_df=label_df,
    )
    if not permission_feature_df.empty:
        permission_feature_path = diagnostics_dir / f"ml_sample_permission_feature_{run_id}.csv"
        permission_feature_df.to_csv(permission_feature_path, index=False)
        oh.mirror_csv_text_run_then_global(
            diagnostics_dir=diagnostics_dir,
            run_filename=permission_feature_path.name,
            csv_text=permission_feature_path.read_text(encoding="utf-8"),
            global_latest_name="ml_sample_permission_feature.latest.csv",
        )
        paths.append(str(permission_feature_path))
        optional_refs["ml_sample_permission_feature"] = permission_feature_path.name

    for key, filename in (
        ("label_contract", f"label_contract_{run_id}.json"),
        ("permission_pattern_contract", f"permission_pattern_contract_{run_id}.json"),
        ("taxonomy_target_surfaces", f"taxonomy_target_surfaces_{run_id}.json"),
        ("run_manifest", "run_manifest.json"),
    ):
        ref = _ref_if_exists(diagnostics_dir, key=key, filename=filename)
        if ref is not None:
            seed_refs[ref[0]] = ref[1]

    ml_manifest = _build_ml_run_manifest(
        run_id=run_id,
        profile=profile,
        manifest=manifest,
        manifest_context=manifest_context,
        seed_artifact_refs=seed_refs,
        optional_seed_artifact_refs=optional_refs,
        sample_label_rows=len(label_df),
        vocabulary_entry_count=int(vocab_payload.get("entry_count", 0) or 0),
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

    handoff_path = export_dl_handoff_summary(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile=profile,
        manifest=manifest,
        manifest_context=manifest_context,
    )
    paths.append(str(handoff_path))
    if is_canonical_profile(str(profile.get("profile_id", "") or "")):
        handoff_payload = build_dl_handoff_summary_payload(
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            profile=profile,
            manifest=manifest,
            manifest_context=manifest_context,
        )
        if handoff_payload.get("dl_seed_status") != "ready":
            caveats = handoff_payload.get("caveats") or []
            raise MlSeedExportError(
                "canonical DL handoff incomplete: " + "; ".join(str(item) for item in caveats)
            )

    return paths
