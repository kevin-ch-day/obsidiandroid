#!/usr/bin/env python3
"""Validate V3 closure artifacts for the four canonical profiles."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from config import app_config  # noqa: E402
from obsidiandroid.common.json_io import read_json_dict  # noqa: E402
from obsidiandroid.common.run_slots import CANONICAL_V3_PROFILES, _SLOT_BY_PROFILE  # noqa: E402
from obsidiandroid.diagnostics import ml_seed_exports  # noqa: E402
from obsidiandroid.diagnostics.run_artifact_resolve import (  # noqa: E402
    resolve_run_artifact_path,
)

CANONICAL_PROFILES = tuple(CANONICAL_V3_PROFILES)

REQUIRED_ARTIFACTS = (
    "v3_label_contract",
    "permission_pattern_contract",
    "ml_run_manifest",
    "ml_sample_label_fact",
    "run_observability_summary.json",
    "run_manifest.json",
)

OPTIONAL_SEED_ARTIFACTS = (
    "ml_permission_vocabulary",
    "ml_permission_pattern_fact",
    "ml_train_validation_test_split",
)

REQUIRED_ML_MANIFEST_REFS = (
    "v3_label_contract",
    "permission_pattern_contract",
    "ml_sample_label_fact",
    "ml_permission_vocabulary",
)

TAG_READY_PIPELINE_STATUSES = frozenset({"PASS", "PASS_WITH_WARNINGS"})


def _default_runs_root() -> Path:
    output_root = str(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output") or "output").strip()
    return Path(output_root) / "runs"


def _diagnostics_dir() -> Path:
    token = str(getattr(app_config, "RUNTIME_DIAGNOSTICS_DIR", "") or "").strip()
    if token:
        return Path(token)
    run_root = str(getattr(app_config, "RUNTIME_RUN_ROOT", "") or "").strip()
    if run_root:
        return Path(run_root) / "diagnostics"
    return Path("output/diagnostics")


def _artifact_present(
    diag: Path,
    run_id: str,
    stem: str,
    *,
    slot_root: Path | None = None,
) -> bool:
    if stem == "run_manifest.json":
        candidates = []
        if slot_root is not None:
            candidates.append(slot_root / "run_manifest.json")
        candidates.extend([diag / "run_manifest.json"])
        return any(path.is_file() for path in candidates)
    if stem.endswith(".json"):
        return (
            (diag / stem).is_file()
            or (diag / f"{stem.replace('.json', '')}_{run_id}.json").is_file()
        )
    for suffix in (".json", ".md", ".csv"):
        if resolve_run_artifact_path(diag, stem=stem, run_id=run_id, suffix=suffix) is not None:
            return True
    return False


def _ref_file_exists(diag: Path, run_id: str, filename: str) -> bool:
    token = str(filename or "").strip()
    if not token:
        return False
    if (diag / token).is_file():
        return True
    for suffix in (".csv", ".json", ".md"):
        if not token.endswith(suffix):
            continue
        stem = token[: -len(suffix)]
        if stem.endswith(f"_{run_id}"):
            stem = stem[: -len(f"_{run_id}")]
        elif stem.endswith(".latest"):
            stem = stem[: -len(".latest")]
        if resolve_run_artifact_path(diag, stem=stem, run_id=run_id, suffix=suffix) is not None:
            return True
    return False


def _sample_label_row_count(diag: Path, run_id: str) -> int:
    path = resolve_run_artifact_path(diag, stem="ml_sample_label_fact", run_id=run_id, suffix=".csv")
    if path is None:
        return 0
    try:
        import pandas as pd

        df = pd.read_csv(path)
    except Exception:
        return 0
    return int(len(df))


def _verify_run(
    profile_id: str,
    run_id: str,
    *,
    diagnostics_dir: Path | None = None,
    run_root: Path | None = None,
    strict: bool = False,
) -> dict[str, object]:
    diag = diagnostics_dir or _diagnostics_dir()
    slot_root = run_root or (diag.parent if diag.name == "diagnostics" else diag)
    missing: list[str] = []
    present: list[str] = []
    for stem in REQUIRED_ARTIFACTS:
        if _artifact_present(diag, run_id, stem, slot_root=slot_root):
            present.append(stem)
        else:
            missing.append(stem)

    optional_present: list[str] = []
    for stem in OPTIONAL_SEED_ARTIFACTS:
        if _artifact_present(diag, run_id, stem, slot_root=slot_root):
            optional_present.append(stem)

    label_contract = diag / f"v3_label_contract_{run_id}.json"
    payload = read_json_dict(label_contract) if label_contract.is_file() else {}
    pattern_contract = read_json_dict(diag / f"permission_pattern_contract_{run_id}.json")
    pattern_levels = pattern_contract.get("pattern_scale", {})
    level_count = len(pattern_levels.get("levels", [])) if isinstance(pattern_levels, dict) else 0

    vocab = ml_seed_exports._build_permission_vocabulary(diag, run_id)
    vocab_count = int(vocab.get("entry_count", 0) or 0)
    persisted_vocab_path = diag / f"ml_permission_vocabulary_{run_id}.json"
    persisted_vocab = read_json_dict(persisted_vocab_path) if persisted_vocab_path.is_file() else {}
    persisted_vocab_count = int(persisted_vocab.get("entry_count", 0) or 0)
    sample_label_rows = _sample_label_row_count(diag, run_id)

    observability = read_json_dict(diag / "run_observability_summary.json")
    pipeline_status = str(observability.get("pipeline_status", "") or "").strip()
    research_validity_status = str(observability.get("research_validity_status", "") or "").strip()
    partial_rv_failures = observability.get("research_validity_partial_failures")
    rv_partial_count = len(partial_rv_failures) if isinstance(partial_rv_failures, list) else 0

    ml_manifest = read_json_dict(diag / f"ml_run_manifest_{run_id}.json")
    seed_refs = ml_manifest.get("seed_artifact_refs") if isinstance(ml_manifest.get("seed_artifact_refs"), dict) else {}
    optional_refs = (
        ml_manifest.get("optional_seed_artifact_refs")
        if isinstance(ml_manifest.get("optional_seed_artifact_refs"), dict)
        else {}
    )
    missing_seed_refs = [key for key in REQUIRED_ML_MANIFEST_REFS if not str(seed_refs.get(key, "") or "").strip()]
    phantom_optional_refs = [
        key
        for key, filename in optional_refs.items()
        if str(filename or "").strip() and not _ref_file_exists(diag, run_id, str(filename))
    ]

    manifest_cohort_size = int(ml_manifest.get("cohort_size", 0) or 0)
    manifest_label_rows = int(ml_manifest.get("sample_label_rows", 0) or 0)
    manifest_vocab_count = int(ml_manifest.get("vocabulary_entry_count", 0) or 0)
    manifest_dataset_hash = str(ml_manifest.get("dataset_hash", "") or "").strip()
    run_manifest_path = slot_root / "run_manifest.json"
    run_manifest = read_json_dict(run_manifest_path) if run_manifest_path.is_file() else {}
    top_level_dataset_hash = str(run_manifest.get("dataset_hash", "") or manifest_dataset_hash).strip()

    caveats: list[str] = []
    if vocab_count <= 0:
        caveats.append("ml_permission_vocabulary has no alias entries (check bundle contracts path)")
    if persisted_vocab_count > 0 and persisted_vocab_count < vocab_count:
        caveats.append(
            "ml_permission_vocabulary on disk is stale "
            f"(persisted={persisted_vocab_count}, live_rebuild={vocab_count}); "
            "run refresh_persisted_permission_vocabulary or rerun manifest finalize"
        )
    if persisted_vocab_count > 0 and str(persisted_vocab.get("vocabulary_version", "") or "") != str(
        vocab.get("vocabulary_version", "") or ""
    ):
        caveats.append(
            "ml_permission_vocabulary version mismatch between persisted export and live rebuild "
            f"({persisted_vocab.get('vocabulary_version')} vs {vocab.get('vocabulary_version')})"
        )
    if level_count != 10:
        caveats.append(f"permission_pattern_contract ladder expected 10 levels, saw {level_count}")
    if missing_seed_refs:
        caveats.append(
            "ml_run_manifest missing seed_artifact_refs: " + ", ".join(missing_seed_refs)
        )
    if sample_label_rows <= 0:
        caveats.append("ml_sample_label_fact has zero supervised rows")
    if pipeline_status and pipeline_status not in TAG_READY_PIPELINE_STATUSES:
        caveats.append(f"pipeline_status={pipeline_status} is outside tag-ready statuses")
    if phantom_optional_refs:
        caveats.append(
            "ml_run_manifest optional_seed_artifact_refs point to missing files: "
            + ", ".join(phantom_optional_refs)
        )
    if manifest_cohort_size > 0 and manifest_label_rows > 0 and manifest_label_rows != manifest_cohort_size:
        caveats.append(
            f"ml_run_manifest sample_label_rows ({manifest_label_rows}) != cohort_size ({manifest_cohort_size})"
        )
    if manifest_vocab_count > 0 and manifest_vocab_count != vocab_count:
        caveats.append(
            "ml_run_manifest vocabulary_entry_count is stale "
            f"(manifest={manifest_vocab_count}, live_rebuild={vocab_count}); "
            "run sync_ml_run_manifest_seed_counters or rerun manifest finalize"
        )
    if persisted_vocab_count > 0 and manifest_vocab_count > 0 and persisted_vocab_count != manifest_vocab_count:
        caveats.append(
            "ml_permission_vocabulary entry_count disagrees with ml_run_manifest "
            f"(vocab={persisted_vocab_count}, manifest={manifest_vocab_count})"
        )
    if not top_level_dataset_hash:
        caveats.append("dataset_hash missing from run_manifest / ml_run_manifest (DL reproducibility gate)")
    if research_validity_status == "FAIL":
        caveats.append("run_observability_summary research_validity_status=FAIL")
    if rv_partial_count > 0:
        caveats.append(
            f"run_observability_summary has {rv_partial_count} research_validity_partial_failures"
        )
    manifest_dataset_hash = str(ml_manifest.get("dataset_hash", "") or "").strip()
    if top_level_dataset_hash and manifest_dataset_hash and top_level_dataset_hash != manifest_dataset_hash:
        caveats.append(
            "ml_run_manifest dataset_hash disagrees with run_manifest "
            f"(manifest={manifest_dataset_hash}, run={top_level_dataset_hash})"
        )
    v3_dl_handoff = observability.get("v3_dl_handoff")
    if isinstance(v3_dl_handoff, dict):
        for key in (
            "ml_run_manifest",
            "ml_sample_label_fact",
            "ml_permission_vocabulary",
            "v3_dl_handoff_summary",
        ):
            ref = str(v3_dl_handoff.get(key, "") or "").strip()
            if ref and not Path(ref).is_file():
                caveats.append(f"v3_dl_handoff path missing on disk: {key}")
        if strict and v3_dl_handoff.get("dl_seed_status") != "ready":
            caveats.append(
                "run_observability_summary v3_dl_handoff dl_seed_status is not ready "
                f"(status={v3_dl_handoff.get('dl_seed_status')!r}; rerun finalize or make refresh-v3-handoff)"
            )
    if strict and not isinstance(v3_dl_handoff, dict):
        caveats.append("run_observability_summary missing v3_dl_handoff block (rerun manifest finalize)")
    handoff_summary_path = diag / f"v3_dl_handoff_summary_{run_id}.json"
    handoff_summary = read_json_dict(handoff_summary_path) if handoff_summary_path.is_file() else {}
    if handoff_summary_path.is_file():
        if handoff_summary.get("dl_seed_status") != "ready":
            caveats.append(
                "v3_dl_handoff_summary reports incomplete DL seed handoff: "
                + "; ".join(str(item) for item in (handoff_summary.get("caveats") or []))
            )
    elif strict:
        caveats.append("missing v3_dl_handoff_summary export (rerun manifest finalize or make refresh-v3-handoff)")
    split_hash = str(ml_manifest.get("split_hash", "") or "").strip()
    if split_hash and not _artifact_present(diag, run_id, "ml_train_validation_test_split", slot_root=slot_root):
        caveats.append("split_hash present in ml_run_manifest but ml_train_validation_test_split export is missing")

    ok = (
        not missing
        and bool(payload.get("profile_role"))
        and pipeline_status in TAG_READY_PIPELINE_STATUSES
        and not missing_seed_refs
        and not phantom_optional_refs
        and sample_label_rows > 0
        and vocab_count > 0
        and bool(top_level_dataset_hash)
    )
    if strict and caveats:
        ok = False

    return {
        "profile_id": profile_id,
        "run_id": run_id,
        "diagnostics_dir": str(diag),
        "present": present,
        "missing": missing,
        "optional_present": optional_present,
        "profile_role": payload.get("profile_role"),
        "target_label_namespace": payload.get("target_label_namespace"),
        "claim_surface_label": payload.get("claim_surface_label"),
        "permission_pattern_levels": level_count,
        "permission_vocabulary_entries": vocab_count,
        "sample_label_rows": sample_label_rows,
        "pipeline_status": pipeline_status,
        "missing_seed_refs": missing_seed_refs,
        "phantom_optional_refs": phantom_optional_refs,
        "manifest_cohort_size": manifest_cohort_size,
        "manifest_sample_label_rows": manifest_label_rows,
        "manifest_vocabulary_entries": manifest_vocab_count,
        "dataset_hash_present": bool(top_level_dataset_hash),
        "caveats": caveats,
        "ok": ok,
    }


def _verify_slot_profile(
    *,
    profile_id: str,
    runs_root: Path,
    strict: bool = False,
) -> dict[str, object]:
    run_slot = _SLOT_BY_PROFILE.get(profile_id, "")
    slot_root = runs_root / run_slot
    manifest_path = slot_root / "run_manifest.json"
    if not manifest_path.is_file():
        return {
            "profile_id": profile_id,
            "run_slot": run_slot,
            "ok": False,
            "error": f"missing run_manifest.json under {slot_root}",
        }
    manifest = read_json_dict(manifest_path)
    run_id = str(manifest.get("run_id") or manifest.get("run_instance_id") or "").strip()
    if not run_id:
        return {
            "profile_id": profile_id,
            "run_slot": run_slot,
            "ok": False,
            "error": f"run_manifest.json missing run_id under {slot_root}",
        }
    summary = _verify_run(
        profile_id,
        run_id,
        diagnostics_dir=slot_root / "diagnostics",
        run_root=slot_root,
        strict=strict,
    )
    summary["run_slot"] = run_slot
    summary["manifest_profile_id"] = manifest.get("profile_id")
    return summary


def verify_only_cli(
    *,
    runs_root: Path,
    strict: bool = False,
    skip_missing_slots: bool = False,
) -> int:
    results = [
        _verify_slot_profile(profile_id=profile_id, runs_root=runs_root, strict=strict)
        for profile_id in CANONICAL_PROFILES
    ]
    if skip_missing_slots:
        normalized: list[dict[str, object]] = []
        for row in results:
            error = str(row.get("error", "") or "").strip()
            if not row.get("ok") and error.startswith("missing run_manifest.json"):
                normalized.append(
                    {
                        **row,
                        "ok": True,
                        "skipped": True,
                        "skip_reason": error,
                    }
                )
                continue
            normalized.append(row)
        results = normalized
    evaluated = [row for row in results if not row.get("skipped")]
    tag_ready = bool(evaluated) and all(bool(row.get("ok")) for row in evaluated)
    caveats = sorted({item for row in results for item in (row.get("caveats") or [])})
    payload = {
        "tag_validation": "PASS" if tag_ready else "FAIL",
        "tag_readiness": "TAG_READY_WITH_CAVEATS" if tag_ready and caveats else ("TAG_READY" if tag_ready else "NOT_READY"),
        "caveats": caveats,
        "profiles": results,
    }
    print(json.dumps(payload, indent=2))
    return 0 if tag_ready else 1


def run_profiles_cli() -> int:
    import main  # noqa: E402

    results: list[dict[str, object]] = []
    for profile_id in CANONICAL_PROFILES:
        print(f"[V3] Running profile={profile_id} …", flush=True)
        code = main.run_pipeline(
            profile_ref=profile_id,
            selected_models=["logistic_regression"],
        )
        run_id = str(getattr(app_config, "RUNTIME_RUN_ID", "") or "").strip()
        summary = _verify_run(profile_id, run_id)
        summary["exit_code"] = int(code)
        results.append(summary)
        print(json.dumps(summary, indent=2), flush=True)
        if int(code) != 0:
            print(f"[V3] profile={profile_id} exit_code={code}", file=sys.stderr)

    all_ok = all(bool(row.get("ok")) and int(row.get("exit_code", 1)) == 0 for row in results)
    print(json.dumps({"tag_validation": "PASS" if all_ok else "FAIL", "profiles": results}, indent=2))
    return 0 if all_ok else 1


def main_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Validate existing canonical slot runs under output/runs without executing the pipeline.",
    )
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=None,
        help="Override runs root (default: <DEFAULT_OUTPUT_DIR>/runs).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat validation caveats (stale counters, hash gaps) as hard failures.",
    )
    parser.add_argument(
        "--skip-missing-slots",
        action="store_true",
        help="Treat absent canonical slot directories as skipped (for partial local output/runs trees).",
    )
    args = parser.parse_args(argv)
    runs_root = args.runs_root or _default_runs_root()
    if args.verify_only:
        return verify_only_cli(
            runs_root=runs_root,
            strict=bool(args.strict),
            skip_missing_slots=bool(args.skip_missing_slots),
        )
    return run_profiles_cli()


if __name__ == "__main__":
    raise SystemExit(main_cli())
