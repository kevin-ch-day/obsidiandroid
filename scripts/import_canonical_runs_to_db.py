#!/usr/bin/env python3
"""Read-only legacy canonical-artifact planner; never a Core DB importer."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts._bootstrap import prepare_script_runtime

REPO_ROOT = prepare_script_runtime(__file__)


def _display_path(path: Path) -> str:
    """Prefer repo-relative paths in dry-run reports for portable baselines."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(resolved)

from obsidiandroid.common.json_io import read_json_dict  # noqa: E402
from obsidiandroid.common.run_slots import (  # noqa: E402
    CANONICAL_PROFILES,
    _SLOT_BY_PROFILE,
    is_canonical_profile,
)
from obsidiandroid.diagnostics.run_artifact_resolve import (  # noqa: E402
    permission_trends_bundle_dirs,
    resolve_run_artifact_path,
)

# This planner retains the v2.2 fixture-artifact checks only.  Its historical
# row labels describe the retired 13-table design and must never be interpreted
# as the Core v1 destination schema or a permission to write to any database.
PLAN_SCOPE = "retired_v2_2_canonical_artifact_plan"

REQUIRED_ARTIFACTS = (
    "label_contract",
    "permission_pattern_contract",
    "ml_run_manifest",
    "ml_sample_label_fact",
    "run_observability_summary.json",
    "run_manifest.json",
)

OPTIONAL_ARTIFACTS = (
    "ml_permission_vocabulary",
    "ml_permission_pattern_fact",
    "ml_train_validation_test_split",
    "ml_sample_permission_feature",
    "model_comparison_summary",
    "ablation_summary",
    "prediction_errors",
    "claim_readiness_summary",
    "taxonomy_consistency_mismatches",
)

TAG_READY_PIPELINE_STATUSES = frozenset({"PASS", "PASS_WITH_WARNINGS"})

TABLE_INSERT_ORDER = (
    "profiles",
    "runs",
    "samples",
    "sample_label_facts",
    "profile_membership",
    "permission_vocabulary",
    "sample_permission_facts",
    "permission_pattern_facts",
    "model_metrics",
    "prediction_facts",
    "quality_flags",
    "split_assignments",
    "release_manifests",
)


@dataclass
class ImportPlan:
    """Aggregated dry-run import plan for one run folder."""

    run_root: Path
    diagnostics_dir: Path
    run_id: str = ""
    profile_id: str = ""
    artifacts_present: list[str] = field(default_factory=list)
    artifacts_missing: list[str] = field(default_factory=list)
    artifacts_optional_present: list[str] = field(default_factory=list)
    artifacts_optional_missing: list[str] = field(default_factory=list)
    planned_rows: dict[str, int] = field(default_factory=dict)
    sample_ids: set[int] = field(default_factory=set)
    blocking_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return bool(self.blocking_errors)


def _resolve_diagnostics_dir(run_root: Path) -> Path:
    candidate = run_root / "diagnostics"
    if candidate.is_dir():
        return candidate
    if run_root.name == "diagnostics" and run_root.is_dir():
        return run_root
    return candidate


def _artifact_present(diag: Path, run_id: str, stem: str, *, slot_root: Path, local_only: bool = False) -> bool:
    if stem == "run_manifest.json":
        return (slot_root / "run_manifest.json").is_file()
    if stem == "run_observability_summary.json":
        return (diag / "run_observability_summary.json").is_file()
    if local_only:
        return _artifact_path_local(diag, run_id, stem) is not None
    if stem.endswith(".json"):
        direct = diag / stem
        if direct.is_file():
            return True
        stamped = diag / f"{stem.replace('.json', '')}_{run_id}.json"
        return stamped.is_file()
    for suffix in (".json", ".csv", ".md"):
        if resolve_run_artifact_path(diag, stem=stem, run_id=run_id, suffix=suffix) is not None:
            return True
    return False


def _artifact_path_local(diag: Path, run_id: str, stem: str) -> Path | None:
    """Resolve an artifact under the run diagnostics tree only (no global mirrors)."""
    if stem == "run_observability_summary.json":
        path = diag / stem
        return path if path.is_file() else None
    for suffix in (".json", ".csv", ".md"):
        run_scoped = diag / f"{stem}_{run_id}{suffix}"
        if run_scoped.is_file():
            return run_scoped
        latest = diag / f"{stem}.latest{suffix}"
        if latest.is_file():
            return latest
        for bundle_dir in permission_trends_bundle_dirs(diag, run_id):
            for candidate in (
                bundle_dir / f"{stem}_{run_id}{suffix}",
                bundle_dir / f"{stem}.latest{suffix}",
            ):
                if candidate.is_file():
                    return candidate
    return None


def _artifact_path(diag: Path, run_id: str, stem: str) -> Path | None:
    """Resolve run-local artifact path for import planning (no global mirrors)."""
    return _artifact_path_local(diag, run_id, stem)


def _global_mirror_available(diag: Path, run_id: str, stem: str) -> bool:
    """Return True when a global diagnostics mirror exists but run-local file does not."""
    if _artifact_path_local(diag, run_id, stem) is not None:
        return False
    for suffix in (".json", ".csv", ".md"):
        resolved = resolve_run_artifact_path(diag, stem=stem, run_id=run_id, suffix=suffix)
        if resolved is not None:
            return True
    return False


def _count_csv_rows(path: Path | None) -> int:
    if path is None or not path.is_file():
        return 0
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            return sum(1 for _ in reader)
    except OSError:
        return 0


def _read_csv_sample_ids(path: Path | None, *, column: str = "sample_id") -> set[int]:
    ids: set[int] = set()
    if path is None or not path.is_file():
        return ids
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or column not in reader.fieldnames:
                return ids
            for row in reader:
                token = str(row.get(column, "") or "").strip()
                if token.isdigit():
                    ids.add(int(token))
    except OSError:
        return ids
    return ids


def _count_json_vocabulary_entries(path: Path | None) -> int:
    if path is None or not path.is_file():
        return 0
    payload = read_json_dict(path)
    entries = payload.get("entries")
    if isinstance(entries, list):
        return len(entries)
    return int(payload.get("entry_count", 0) or 0)


def _count_quality_flags(
    diag: Path,
    run_id: str,
    *,
    observability: dict[str, Any],
    claim_path: Path | None,
    taxonomy_path: Path | None,
) -> int:
    count = 0
    pipeline_status = str(observability.get("pipeline_status", "") or "").strip()
    if pipeline_status and pipeline_status not in TAG_READY_PIPELINE_STATUSES:
        count += 1
    research_validity_status = str(observability.get("research_validity_status", "") or "").strip()
    if research_validity_status and research_validity_status.upper() not in {"PASS", "OK"}:
        count += 1
    partial = observability.get("research_validity_partial_failures")
    if isinstance(partial, list):
        count += len(partial)
    if claim_path is not None:
        claim = read_json_dict(claim_path)
        for key in ("blocking_issues", "warnings"):
            items = claim.get(key)
            if isinstance(items, list):
                count += len(items)
    count += _count_csv_rows(taxonomy_path)
    return count


def _detect_run_and_profile(slot_root: Path, diag: Path, run_id_override: str, profile_override: str) -> tuple[str, str]:
    manifest_path = slot_root / "run_manifest.json"
    manifest = read_json_dict(manifest_path) if manifest_path.is_file() else {}
    run_id = str(run_id_override or manifest.get("run_id", "") or "").strip()
    profile_id = str(profile_override or manifest.get("profile_id", "") or "").strip()
    if not run_id:
        ml_manifests = sorted(diag.glob("ml_run_manifest_*.json"))
        if ml_manifests:
            stem = ml_manifests[-1].stem
            if stem.startswith("ml_run_manifest_"):
                run_id = stem[len("ml_run_manifest_") :]
                ml_payload = read_json_dict(ml_manifests[-1])
                if not profile_id:
                    profile_id = str(ml_payload.get("profile_id", "") or "").strip()
    return run_id, profile_id


def build_import_plan(
    run_root: Path,
    *,
    run_id: str = "",
    profile_id: str = "",
    release_tag: str = "",
    allow_mixed: bool = False,
    strict: bool = True,
) -> ImportPlan:
    """Validate a run folder and compute a dry-run import plan."""

    run_root = run_root.resolve()
    slot_root = run_root.parent if run_root.name == "diagnostics" else run_root
    diag = _resolve_diagnostics_dir(slot_root)
    plan = ImportPlan(run_root=slot_root, diagnostics_dir=diag)

    if not slot_root.is_dir():
        plan.blocking_errors.append(f"run root does not exist: {slot_root}")
        return plan
    if not diag.is_dir():
        plan.blocking_errors.append(f"diagnostics directory missing: {diag}")
        return plan

    detected_run_id, detected_profile_id = _detect_run_and_profile(slot_root, diag, run_id, profile_id)
    plan.run_id = detected_run_id
    plan.profile_id = detected_profile_id

    if not plan.run_id:
        plan.blocking_errors.append("could not detect run_id from run_manifest.json or ml_run_manifest_*.json")
    if not plan.profile_id:
        plan.blocking_errors.append("could not detect profile_id from run_manifest.json or ml_run_manifest_*.json")

    for stem in REQUIRED_ARTIFACTS:
        if _artifact_present(diag, plan.run_id, stem, slot_root=slot_root):
            plan.artifacts_present.append(stem)
        else:
            plan.artifacts_missing.append(stem)

    for stem in OPTIONAL_ARTIFACTS:
        if _artifact_present(diag, plan.run_id, stem, slot_root=slot_root, local_only=True):
            plan.artifacts_optional_present.append(stem)
        else:
            plan.artifacts_optional_missing.append(stem)

    if strict and plan.artifacts_missing:
        plan.blocking_errors.append(
            "missing required artifacts: " + ", ".join(plan.artifacts_missing)
        )

    manifest_path = slot_root / "run_manifest.json"
    run_manifest = read_json_dict(manifest_path) if manifest_path.is_file() else {}
    ml_manifest_path = _artifact_path(diag, plan.run_id, "ml_run_manifest")
    ml_manifest = read_json_dict(ml_manifest_path) if ml_manifest_path is not None else {}
    observability = read_json_dict(diag / "run_observability_summary.json")

    manifest_run_id = str(run_manifest.get("run_id", "") or "").strip()
    manifest_profile_id = str(run_manifest.get("profile_id", "") or "").strip()
    ml_run_id = str(ml_manifest.get("run_id", "") or "").strip()
    ml_profile_id = str(ml_manifest.get("profile_id", "") or "").strip()

    if plan.run_id and manifest_run_id and manifest_run_id != plan.run_id:
        plan.blocking_errors.append(
            f"run_id mismatch: CLI/manifest={plan.run_id}, run_manifest.json={manifest_run_id}"
        )
    if plan.profile_id and manifest_profile_id and manifest_profile_id != plan.profile_id:
        plan.blocking_errors.append(
            f"profile_id mismatch: CLI/manifest={plan.profile_id}, run_manifest.json={manifest_profile_id}"
        )
    if plan.run_id and ml_run_id and ml_run_id != plan.run_id:
        plan.warnings.append(f"ml_run_manifest run_id ({ml_run_id}) differs from resolved run_id ({plan.run_id})")
    if plan.profile_id and ml_profile_id and ml_profile_id != plan.profile_id:
        plan.warnings.append(
            f"ml_run_manifest profile_id ({ml_profile_id}) differs from resolved profile_id ({plan.profile_id})"
        )

    if plan.profile_id and not is_canonical_profile(plan.profile_id):
        plan.warnings.append(f"profile_id={plan.profile_id} is outside the four canonical profiles")

    pipeline_status = str(observability.get("pipeline_status", "") or "").strip()
    if pipeline_status and pipeline_status not in TAG_READY_PIPELINE_STATUSES and not allow_mixed:
        plan.blocking_errors.append(
            f"pipeline_status={pipeline_status} is not tag-ready "
            f"(expected {sorted(TAG_READY_PIPELINE_STATUSES)}); pass --allow-mixed to override"
        )

    label_fact_path = _artifact_path(diag, plan.run_id, "ml_sample_label_fact")
    split_path = _artifact_path(diag, plan.run_id, "ml_train_validation_test_split")
    permission_feature_path = _artifact_path(diag, plan.run_id, "ml_sample_permission_feature")
    pattern_fact_path = _artifact_path(diag, plan.run_id, "ml_permission_pattern_fact")
    vocab_path = _artifact_path(diag, plan.run_id, "ml_permission_vocabulary")
    model_comparison_path = _artifact_path(diag, plan.run_id, "model_comparison_summary")
    ablation_path = _artifact_path(diag, plan.run_id, "ablation_summary")
    prediction_path = _artifact_path(diag, plan.run_id, "prediction_errors")
    claim_path = _artifact_path(diag, plan.run_id, "claim_readiness_summary")
    taxonomy_path = _artifact_path(diag, plan.run_id, "taxonomy_consistency_mismatches")

    for stem in OPTIONAL_ARTIFACTS:
        if stem in plan.artifacts_optional_missing and _global_mirror_available(diag, plan.run_id, stem):
            plan.warnings.append(
                f"{stem} missing run-local but a global diagnostics mirror exists; import plan ignores global mirrors"
            )

    label_rows = _count_csv_rows(label_fact_path)
    split_rows = _count_csv_rows(split_path)
    permission_rows = _count_csv_rows(permission_feature_path)
    pattern_rows = _count_csv_rows(pattern_fact_path)
    vocab_rows = _count_json_vocabulary_entries(vocab_path)
    model_rows = _count_csv_rows(model_comparison_path) + _count_csv_rows(ablation_path)
    prediction_rows = _count_csv_rows(prediction_path)
    quality_rows = _count_quality_flags(
        diag,
        plan.run_id,
        observability=observability,
        claim_path=claim_path,
        taxonomy_path=taxonomy_path,
    )

    sample_ids: set[int] = set()
    sample_ids |= _read_csv_sample_ids(label_fact_path)
    sample_ids |= _read_csv_sample_ids(split_path)
    sample_ids |= _read_csv_sample_ids(permission_feature_path)
    sample_ids |= _read_csv_sample_ids(prediction_path)
    plan.sample_ids = sample_ids

    if label_fact_path is not None and label_rows > 0:
        seen: set[int] = set()
        dupes: set[int] = set()
        try:
            with label_fact_path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                if reader.fieldnames and "sample_id" in reader.fieldnames:
                    for row in reader:
                        token = str(row.get("sample_id", "") or "").strip()
                        if not token.isdigit():
                            continue
                        sample_id = int(token)
                        if sample_id in seen:
                            dupes.add(sample_id)
                        seen.add(sample_id)
        except OSError:
            pass
        if dupes:
            plan.blocking_errors.append(
                "duplicate sample_id in ml_sample_label_fact: " + ", ".join(str(v) for v in sorted(dupes))
            )

    manifest_label_rows = int(ml_manifest.get("sample_label_rows", 0) or 0)
    if manifest_label_rows > 0 and label_rows > 0 and manifest_label_rows != label_rows:
        plan.warnings.append(
            f"ml_run_manifest sample_label_rows ({manifest_label_rows}) != label fact rows ({label_rows})"
        )

    split_hash = str(run_manifest.get("split_hash", "") or ml_manifest.get("split_hash", "") or "").strip()
    if split_path is not None and not split_hash:
        plan.warnings.append("split export present but split_hash missing from manifests")
    if split_path is None and split_rows == 0:
        plan.warnings.append(
            "ml_train_validation_test_split missing; profile_membership and split_assignments counts are provisional"
        )
    if permission_feature_path is None:
        plan.warnings.append(
            "ml_sample_permission_feature missing; sample_permission_facts import deferred until export exists"
        )

    membership_rows = split_rows if split_rows > 0 else label_rows

    plan.planned_rows = {
        "profiles": 1 if plan.profile_id else 0,
        "runs": 1 if plan.run_id else 0,
        "samples": len(sample_ids),
        "sample_label_facts": label_rows,
        "profile_membership": membership_rows,
        "permission_vocabulary": vocab_rows,
        "sample_permission_facts": permission_rows,
        "permission_pattern_facts": pattern_rows,
        "model_metrics": model_rows,
        "prediction_facts": prediction_rows,
        "quality_flags": quality_rows,
        "split_assignments": split_rows,
        "release_manifests": 1 if release_tag and plan.run_id and plan.profile_id else 0,
    }

    return plan


def dry_run_all_slots(
    *,
    runs_root: Path,
    release_tag: str = "",
    allow_mixed: bool = False,
    strict: bool = True,
    skip_missing_slots: bool = False,
) -> list[tuple[str, ImportPlan | None]]:
    """Build dry-run import plans for all canonical profile slots under runs_root."""
    runs_root = runs_root.resolve()
    results: list[tuple[str, ImportPlan | None]] = []
    for profile_id in CANONICAL_PROFILES:
        run_slot = _SLOT_BY_PROFILE.get(profile_id, "")
        slot_root = runs_root / run_slot
        manifest_path = slot_root / "run_manifest.json"
        if not manifest_path.is_file():
            if skip_missing_slots:
                results.append((profile_id, None))
                continue
            results.append(
                (
                    profile_id,
                    ImportPlan(
                        run_root=slot_root,
                        diagnostics_dir=slot_root / "diagnostics",
                        profile_id=profile_id,
                        blocking_errors=[f"missing run_manifest.json under {slot_root}"],
                    ),
                )
            )
            continue
        results.append(
            (
                profile_id,
                build_import_plan(
                    slot_root,
                    release_tag=release_tag,
                    allow_mixed=allow_mixed,
                    strict=strict,
                ),
            )
        )
    return results


def dry_run_all_slots_cli(
    *,
    runs_root: Path,
    release_tag: str = "",
    allow_mixed: bool = False,
    strict: bool = True,
    skip_missing_slots: bool = False,
) -> int:
    """Dry-run import plans for all canonical profile slots under runs_root."""
    exit_code = 0
    for profile_id, plan in dry_run_all_slots(
        runs_root=runs_root,
        release_tag=release_tag,
        allow_mixed=allow_mixed,
        strict=strict,
        skip_missing_slots=skip_missing_slots,
    ):
        run_slot = _SLOT_BY_PROFILE.get(profile_id, "")
        if plan is None:
            print(f"[skip] {profile_id}: missing slot under {runs_root / run_slot}")
            continue
        status = "BLOCKED" if plan.blocked else "READY"
        print(
            f"[{status}] {profile_id} ({run_slot}) run_id={plan.run_id or '(missing)'} "
            f"samples={len(plan.sample_ids)} errors={len(plan.blocking_errors)} "
            f"warnings={len(plan.warnings)}"
        )
        if plan.blocked:
            exit_code = 1
    return exit_code


def import_plan_to_dict(plan: ImportPlan, *, release_tag: str = "") -> dict[str, Any]:
    """Serialize an import plan for JSON output or tests."""
    return {
        "plan_scope": PLAN_SCOPE,
        "run_root": _display_path(plan.run_root),
        "diagnostics_dir": _display_path(plan.diagnostics_dir),
        "run_id": plan.run_id,
        "profile_id": plan.profile_id,
        "release_tag": release_tag,
        "artifacts_present": plan.artifacts_present,
        "artifacts_missing": plan.artifacts_missing,
        "artifacts_optional_present": plan.artifacts_optional_present,
        "artifacts_optional_missing": plan.artifacts_optional_missing,
        "planned_rows": plan.planned_rows,
        "sample_id_count": len(plan.sample_ids),
        "blocking_errors": plan.blocking_errors,
        "warnings": plan.warnings,
        "blocked": plan.blocked,
    }


def _format_plan(plan: ImportPlan, *, release_tag: str) -> str:
    lines: list[str] = []
    lines.append("ObsidianDroid retired canonical-artifact plan (read-only)")
    lines.append(f"plan scope: {PLAN_SCOPE}")
    lines.append(f"run_root: {plan.run_root}")
    lines.append(f"diagnostics: {plan.diagnostics_dir}")
    lines.append("")
    lines.append("Detected")
    lines.append(f"  run_id: {plan.run_id or '(missing)'}")
    lines.append(f"  profile_id: {plan.profile_id or '(missing)'}")
    if release_tag:
        lines.append(f"  release_tag: {release_tag}")
    lines.append("")
    lines.append("Artifacts (required)")
    for stem in REQUIRED_ARTIFACTS:
        mark = "present" if stem in plan.artifacts_present else "MISSING"
        lines.append(f"  [{mark}] {stem}")
    lines.append("")
    lines.append("Artifacts (optional)")
    for stem in OPTIONAL_ARTIFACTS:
        mark = "present" if stem in plan.artifacts_optional_present else "missing"
        lines.append(f"  [{mark}] {stem}")
    lines.append("")
    lines.append("Historical draft row mapping (not Core v1 inserts)")
    for table in TABLE_INSERT_ORDER:
        lines.append(f"  {table}: {plan.planned_rows.get(table, 0)}")
    lines.append(f"  unique sample_ids (lazy registry): {len(plan.sample_ids)}")
    lines.append("")
    if plan.blocking_errors:
        lines.append("Blocking errors")
        for item in plan.blocking_errors:
            lines.append(f"  ERROR: {item}")
        lines.append("")
    if plan.warnings:
        lines.append("Warnings")
        for item in plan.warnings:
            lines.append(f"  WARN: {item}")
        lines.append("")
    if plan.blocked:
        lines.append("Result: BLOCKED (no database connection or writes performed)")
    else:
        lines.append("Result: READY FOR ARTIFACT REVIEW (read-only; no database connection or writes performed)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate canonical artifacts and print a retired-draft row mapping (read-only)."
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        default=None,
        help="Path to output/runs/<slot>/ or an archived run tree (with diagnostics/).",
    )
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=None,
        help="Parent of canonical slot dirs; dry-runs all four canonical profiles.",
    )
    parser.add_argument(
        "--skip-missing-slots",
        action="store_true",
        help="With --runs-root, skip slots without run_manifest.json instead of failing.",
    )
    parser.add_argument("--run-id", default="", help="Override detected run_id.")
    parser.add_argument("--profile-id", default="", help="Override detected profile_id.")
    parser.add_argument(
        "--release-tag",
        default="",
        help="Optional historical release tag (e.g. v2.2.0) for retired-draft row planning.",
    )
    parser.add_argument(
        "--allow-mixed",
        action="store_true",
        help="Do not block on non-tag-ready pipeline_status values.",
    )
    parser.add_argument(
        "--strict",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Treat missing required artifacts as blocking errors (default: true).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of plain text.",
    )
    args = parser.parse_args(argv)

    if args.runs_root is not None:
        if args.run_root is not None:
            parser.error("use either --run-root or --runs-root, not both")
        release_tag = str(args.release_tag or "").strip()
        if args.json:
            payload = {
                "plan_scope": PLAN_SCOPE,
                "runs_root": _display_path(args.runs_root),
                "release_tag": release_tag,
                "profiles": [],
            }
            exit_code = 0
            for profile_id, plan in dry_run_all_slots(
                runs_root=args.runs_root,
                release_tag=release_tag,
                allow_mixed=bool(args.allow_mixed),
                strict=bool(args.strict),
                skip_missing_slots=bool(args.skip_missing_slots),
            ):
                entry: dict[str, Any] = {"profile_id": profile_id}
                if plan is None:
                    entry["status"] = "skipped"
                else:
                    entry["status"] = "blocked" if plan.blocked else "ready"
                    entry.update(import_plan_to_dict(plan, release_tag=release_tag))
                    if plan.blocked:
                        exit_code = 1
                payload["profiles"].append(entry)
            print(json.dumps(payload, indent=2, sort_keys=True))
            return exit_code
        return dry_run_all_slots_cli(
            runs_root=args.runs_root,
            release_tag=release_tag,
            allow_mixed=bool(args.allow_mixed),
            strict=bool(args.strict),
            skip_missing_slots=bool(args.skip_missing_slots),
        )

    if args.run_root is None:
        parser.error("--run-root is required unless --runs-root is provided")

    plan = build_import_plan(
        args.run_root,
        run_id=str(args.run_id or "").strip(),
        profile_id=str(args.profile_id or "").strip(),
        release_tag=str(args.release_tag or "").strip(),
        allow_mixed=bool(args.allow_mixed),
        strict=bool(args.strict),
    )

    release_tag = str(args.release_tag or "").strip()
    if args.json:
        print(json.dumps(import_plan_to_dict(plan, release_tag=release_tag), indent=2, sort_keys=True))
    else:
        print(_format_plan(plan, release_tag=release_tag))

    return 1 if plan.blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
