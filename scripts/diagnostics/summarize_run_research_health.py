#!/usr/bin/env python3
"""Summarize research-relevant signals for one pipeline run (read-only).

Scans ``output/runs/<run_id>/diagnostics`` and the run root for:

- Pipeline stage summary (PASS/FAIL through recorded stages)
- Leakage / epistemic label (from ``leakage_assessment*.txt``)
- Cohort lock + profile (from ``cohort_lock_summary.json``)
- Feature matrix authority + vendor merge + permission PI coverage
  (from ``feature_build_coverage*.json`` / ``feature_modality_coverage_summary*.json``)
- Train/test split hygiene (from ``split_freeze_headline*.csv``: counts, overlap flags)
- Whether finalization artifacts exist (``run_manifest.json``, ``run_observability_summary.json``, …)
- Tail of ``pipeline_events.jsonl`` for last recorded stage transitions
- **Output navigator:** bucket counts from ``artifact_inventory.json`` (when manifest finalization wrote it),
  plus a checklist of “open first” / research bundle files. Use ``--tour`` to also list the largest files
  under the run tree (can be slow on huge runs).

Examples (from repo root)::

    python scripts/diagnostics/summarize_run_research_health.py --run-id 20260506T020839Z__a2ad43
    python scripts/diagnostics/summarize_run_research_health.py --latest
    python scripts/diagnostics/summarize_run_research_health.py --run-root output/runs/20260506T020839Z__a2ad43 --json
    python scripts/diagnostics/summarize_run_research_health.py --latest --tour
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_run_root(repo: Path, run_id: str | None, run_root: Path | None, latest: bool) -> Path:
    runs = repo / "output" / "runs"
    if run_root is not None:
        p = Path(run_root).resolve()
        if not p.is_dir():
            raise SystemExit(f"not a directory: {p}")
        return p
    if latest:
        if not runs.is_dir():
            raise SystemExit(f"missing runs directory: {runs}")
        candidates = [p for p in runs.iterdir() if p.is_dir()]
        if not candidates:
            raise SystemExit(f"no runs under {runs}")
        return max(candidates, key=lambda p: p.stat().st_mtime)
    if not run_id:
        raise SystemExit("provide --run-id, --run-root, or --latest")
    p = runs / run_id
    if not p.is_dir():
        raise SystemExit(f"run directory not found: {p}")
    return p.resolve()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _prefer_run_scoped(paths: list[Path], run_id: str) -> Path | None:
    """Prefer ``*_<run_id>.*`` over ``*.latest.*`` when multiple exist."""
    tagged = [p for p in paths if run_id in p.name]
    if tagged:
        return sorted(tagged, key=lambda p: len(p.name), reverse=True)[0]
    if paths:
        return sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)[0]
    return None


def _split_freeze_path(diag: Path, run_id: str) -> Path | None:
    globs = list(diag.glob("split_freeze_headline*.csv"))
    return _prefer_run_scoped(globs, run_id)


def _analyze_split_freeze(path: Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
    except OSError:
        return None
    if not rows:
        return {"rows": 0}
    roles = Counter(str(r.get("split_role") or "").strip().lower() for r in rows)
    overlap = sum(int(r.get("overlap_flag") or 0) for r in rows)
    dup_sha = sum(int(r.get("duplicate_sha_group_across_splits") or 0) for r in rows)
    active_cls = rows[0].get("active_class_count")
    label_target = rows[0].get("label_target")
    split_hash = rows[0].get("split_hash")
    return {
        "rows": len(rows),
        "split_role_counts": dict(roles),
        "overlap_rows": overlap,
        "duplicate_sha_groups_flagged": dup_sha,
        "active_class_count_sample": active_cls,
        "label_target": label_target,
        "split_hash": split_hash,
    }


def _tail_jsonl(path: Path, max_lines: int = 12) -> list[str]:
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return lines[-max_lines:]


def _jsonl_tail_has_message(path: Path, message: str, *, max_lines: int = 600) -> bool:
    """Scan recent JSONL lines for ``message`` (population / funnel transitions)."""
    for line in _tail_jsonl(path, max_lines):
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(ev.get("message") or "") == message:
            return True
    return False


def _parse_leakage(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip()
    return out


def _gather_output_navigator(run_root: Path, diag: Path, *, heavy_tour: bool) -> dict[str, Any]:
    """What was generated and where to click first (inventory + navigator paths from finalize/hygiene)."""
    nav: dict[str, Any] = {}
    inv_path = diag / "artifact_inventory.json"
    inv_blob = _read_json(inv_path)
    summary = inv_blob.get("summary") if isinstance(inv_blob, dict) else None
    if isinstance(summary, dict):
        nav["artifact_inventory"] = {
            "path": str(inv_path),
            "total_artifacts": summary.get("total_artifacts"),
            "bucket_counts": summary.get("bucket_counts"),
            "duplicate_latest_inside_run": summary.get("duplicate_latest_inside_run"),
            "manifest_path_count": summary.get("manifest_path_count"),
        }
    elif inv_path.is_file():
        nav["artifact_inventory"] = {"path": str(inv_path), "error": "could_not_parse_json"}
    else:
        nav["artifact_inventory"] = None
        nav["artifact_inventory_note"] = (
            "artifact_inventory.json missing — run may not have reached manifest/output hygiene, or inventory was skipped."
        )

    keys = {
        "run_evidence_index_md": run_root / "run_evidence_index.md",
        "run_artifact_index_md": diag / "run_artifact_index.md",
        "virtual_layout_json": diag / "virtual_layout.json",
        "artifact_inventory_md": diag / "artifact_inventory.md",
        "cohort_funnel_md": diag / "cohort_funnel.md",
        "pipeline_stage_summary_md": diag / "pipeline_stage_summary.md",
        "dataset_foundation_summary_json": diag / "dataset_foundation_summary.json",
        "model_and_family_failure_summary_json": diag / "model_and_family_failure_summary.json",
        "modality_contribution_summary_json": diag / "modality_contribution_summary.json",
    }
    nav["navigator_files_present"] = {k: v.is_file() for k, v in keys.items()}
    nav["navigator_paths"] = {k: str(v) for k, v in keys.items()}

    try:
        nav["diagnostics_file_count"] = (
            sum(1 for p in diag.rglob("*") if p.is_file()) if diag.is_dir() else 0
        )
    except OSError:
        nav["diagnostics_file_count"] = None

    if heavy_tour:
        largest: list[dict[str, Any]] = []
        try:
            scored: list[tuple[Path, int]] = []
            for p in run_root.rglob("*"):
                if not p.is_file():
                    continue
                try:
                    scored.append((p, p.stat().st_size))
                except OSError:
                    continue
            scored.sort(key=lambda t: t[1], reverse=True)
            for p, sz in scored[:20]:
                try:
                    rel = p.relative_to(run_root).as_posix()
                except ValueError:
                    rel = str(p)
                largest.append({"path": rel, "bytes": sz})
        except OSError:
            pass
        nav["largest_files_in_run_top20"] = largest

    return nav


def gather_report(repo: Path, run_root: Path, *, heavy_tour: bool = False) -> dict[str, Any]:
    run_id = run_root.name
    diag = run_root / "diagnostics"
    report: dict[str, Any] = {"run_id": run_id, "run_root": str(run_root)}

    # Stage summary
    ps = diag / "pipeline_stage_summary.csv"
    stages: list[dict[str, str]] = []
    if ps.is_file():
        try:
            with ps.open(encoding="utf-8", newline="") as fh:
                stages = list(csv.DictReader(fh))
        except OSError:
            pass
    report["pipeline_stages_recorded"] = len(stages)
    report["pipeline_stage_tail"] = [
        {
            "stage": r.get("stage_name"),
            "status": r.get("status"),
            "duration_sec": r.get("duration_sec"),
        }
        for r in stages[-8:]
    ]
    last_stage = stages[-1]["stage_name"] if stages else None
    report["pipeline_last_summarized_stage"] = last_stage

    # Leakage
    leakage_path = diag / "leakage_assessment.latest.txt"
    if not leakage_path.is_file():
        cand = sorted(diag.glob("leakage_assessment*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        leakage_path = cand[0] if cand else leakage_path
    lt = _read_text(leakage_path)
    report["leakage_file"] = str(leakage_path) if leakage_path.is_file() else None
    report["leakage_parsed"] = _parse_leakage(lt) if lt else None

    # Cohort lock
    cl = _read_json(diag / "cohort_lock_summary.json")
    report["cohort_lock_summary"] = cl

    # Feature authority
    fb = _read_json(diag / "feature_build_coverage.latest.json")
    if fb is None:
        cand = sorted(diag.glob("feature_build_coverage_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        fb = _read_json(cand[0]) if cand else None
    report["feature_build_coverage"] = fb

    fm = _read_json(diag / "feature_modality_coverage_summary.latest.json")
    if fm is None:
        cand = sorted(diag.glob("feature_modality_coverage_summary_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        fm = _read_json(cand[0]) if cand else None
    report["feature_modality_coverage_summary"] = fm

    # Split hygiene
    sf = _split_freeze_path(diag, run_id)
    report["split_freeze_csv"] = str(sf) if sf else None
    report["split_freeze_stats"] = _analyze_split_freeze(sf) if sf else None

    # Finalization / observability artifacts
    report["artifacts_present"] = {
        "run_manifest.json": (run_root / "run_manifest.json").is_file(),
        "run_summary.json": (run_root / "run_summary.json").is_file(),
        "run_observability_summary.json": (diag / "run_observability_summary.json").is_file(),
        "model_comparison_summary_csv": len(list(diag.glob("model_comparison_summary*.csv"))) > 0,
        "ablation_summary_csv": len(list(diag.glob("ablation_summary*.csv"))) > 0,
        "partial_failures_md": (diag / "partial_failures.md").is_file(),
    }

    # Events tail
    pe = diag / "pipeline_events.jsonl"
    tails = _tail_jsonl(pe, 14)
    report["pipeline_events_tail_raw"] = tails
    training_completed = False
    for line in tails:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("category") != "STAGE_END":
            continue
        # emit_stage_completion uses ``message=<stage_name>``; legacy events may use ``stage``.
        ended = str(ev.get("stage") or ev.get("message") or "").strip()
        if ended == "training":
            training_completed = True
            break
    report["pipeline_events_training_completed"] = training_completed

    # Gaps / hints
    hints: list[str] = []
    if not report["artifacts_present"]["run_manifest.json"]:
        hints.append("run_manifest.json missing — pipeline may still be running or stopped before finalize.")
    if not report["artifacts_present"]["run_observability_summary.json"]:
        hints.append("run_observability_summary.json missing — research validity bundle may be incomplete.")
    if stages and stages[-1].get("stage_name") == "alignment" and not training_completed:
        hints.append(
            "pipeline_stage_summary ends at alignment and events show no training STAGE_END — "
            "run may still be in training/finalizing, or the summary CSV was not flushed yet."
        )
    models_dir = run_root / "models"
    if (
        models_dir.is_dir()
        and any(models_dir.rglob("*.joblib"))
        and not report["artifacts_present"]["run_manifest.json"]
    ):
        hints.append(
            "Model artifacts exist but run_manifest.json is missing — pipeline likely has not reached manifest finalization yet."
        )
    lk = report.get("leakage_parsed") or {}
    risk = lk.get("Leakage risk classification", "")
    if "AV-label-informed" in risk:
        hints.append(
            "Leakage classification is AV-label-informed: scope behavioral claims accordingly (see modality_method_contract / science audit playbook)."
        )

    cl_n = cl.get("sample_count") if isinstance(cl, dict) else None
    sf_stats = report.get("split_freeze_stats") or {}
    sf_n = sf_stats.get("rows")
    try:
        ci = int(cl_n) if cl_n is not None else None
        si = int(sf_n) if sf_n is not None else None
    except (TypeError, ValueError):
        ci, si = None, None
    if ci is not None and si is not None and ci != si:
        post_low = "aligned_supervised_to_post_low_support_training"
        if _jsonl_tail_has_message(pe, post_low, max_lines=800):
            hints.append(
                f"cohort_lock sample_count ({ci}) vs split_freeze headline ({si}) rows: cohort lock reflects "
                f"pre–low-support training universe; supervised pool shrink is emitted in pipeline_events "
                f"({post_low}). Investigate further only if masking looks wrong."
            )
        else:
            hints.append(
                f"cohort_lock sample_count ({ci}) != split_freeze headline rows ({si}) — "
                "usually label-alignment / completeness drops; compare aligned_labels vs cohort_membership."
            )

    report["operator_hints"] = hints
    report["output_navigator"] = _gather_output_navigator(run_root, diag, heavy_tour=heavy_tour)

    return report


def _print_human(report: dict[str, Any]) -> None:
    rid = report["run_id"]
    print(f"Run research health summary — {rid}")
    print(f"  Root: {report['run_root']}")
    print()

    lk = report.get("leakage_parsed") or {}
    print("Epistemics (leakage assessment)")
    for key in (
        "Ground truth label source",
        "Leakage risk classification",
        "Parsed Family used in features",
        "Threat Class used",
        "Malware Type used",
    ):
        if key in lk:
            print(f"  {key}: {lk[key]}")
    print()

    fb = report.get("feature_build_coverage") or {}
    fm = report.get("feature_modality_coverage_summary") or {}
    print("Feature matrix authority")
    for key in (
        "cohort_unique_sample_count",
        "feature_matrix_unique_row_count",
        "vendor_merge_authority_unique_count",
        "row_authority_note",
    ):
        if key in fb:
            val = fb[key]
            if key == "row_authority_note" and isinstance(val, str) and len(val) > 200:
                val = val[:200] + "…"
            print(f"  {key}: {val}")
    print("Modality snapshot")
    for key in ("fused_matrix_row_n", "governed_cohort_n", "vendor_merge_n", "permission_pi_signal_positive_n"):
        if key in fm:
            print(f"  {key}: {fm[key]}")
    if "vendor_merge_n_note" in fm:
        note = fm["vendor_merge_n_note"]
        if isinstance(note, str) and len(note) > 180:
            note = note[:180] + "…"
        print(f"  vendor_merge_n_note: {note}")
    print()

    sf = report.get("split_freeze_stats") or {}
    if sf:
        print("Split freeze (headline)")
        print(f"  file: {report.get('split_freeze_csv')}")
        print(f"  rows: {sf.get('rows')}")
        print(f"  split_role_counts: {sf.get('split_role_counts')}")
        print(f"  overlap_rows (sum overlap_flag): {sf.get('overlap_rows')}")
        print(f"  duplicate_sha_groups_flagged: {sf.get('duplicate_sha_groups_flagged')}")
        print(f"  label_target / active_class_count: {sf.get('label_target')} / {sf.get('active_class_count_sample')}")
        print()

    cl = report.get("cohort_lock_summary") or {}
    if cl:
        print("Cohort lock")
        print(f"  profile_id: {cl.get('profile_id')}")
        print(f"  sample_count: {cl.get('sample_count')}  unique_family_count: {cl.get('unique_family_count')}")
        snap = cl.get("snapshot_lock") or {}
        if isinstance(snap, dict):
            print(f"  snapshot_lock.status: {snap.get('status')}")
        print()

    ap = report.get("artifacts_present") or {}
    print("Finalization / research artifacts")
    for name, ok in sorted(ap.items()):
        print(f"  [{'OK' if ok else '--'}] {name}")
    print()

    on = report.get("output_navigator") or {}
    inv = on.get("artifact_inventory")
    print("Output navigator (what was generated)")
    if isinstance(inv, dict) and inv.get("total_artifacts") is not None:
        print(f"  artifact_inventory: total files classified: {inv.get('total_artifacts')}")
        bc = inv.get("bucket_counts") or {}
        if isinstance(bc, dict) and bc:

            def _bc_key(item: tuple[str, Any]) -> tuple[int, str]:
                bname, val = item
                try:
                    return (-int(val), bname)
                except (TypeError, ValueError):
                    return (0, bname)

            for bucket, n in sorted(bc.items(), key=_bc_key):
                print(f"    {bucket}: {n}")
        dup = inv.get("duplicate_latest_inside_run")
        if dup is not None:
            print(f"    duplicate .latest inside run (policy tally): {dup}")
    elif isinstance(inv, dict) and inv.get("error"):
        print(f"  artifact_inventory.json: {inv.get('error')}")
    else:
        msg = str(on.get("artifact_inventory_note") or "artifact_inventory.json not found")
        print(f"  {msg}")
    nfp = on.get("navigator_files_present") or {}
    if nfp:
        print("  Key routing / research bundle files:")
        for name in sorted(nfp.keys()):
            print(f"    [{'OK' if nfp.get(name) else '--'}] {name}")
        dct = on.get("diagnostics_file_count")
        if dct is not None:
            print(f"  diagnostics/ file count: {dct}")
    largest = on.get("largest_files_in_run_top20") or []
    if largest:
        print("  Largest on-disk paths under run (see --tour):")
        for row in largest[:10]:
            b = int(row.get("bytes") or 0)
            mb = b / (1024 * 1024)
            print(f"    {mb:.2f} MiB  {row.get('path')}")
    print()

    print(f"Pipeline stages in summary CSV: {report.get('pipeline_stages_recorded')}")
    for row in report.get("pipeline_stage_tail") or []:
        print(f"  {row.get('stage')}: {row.get('status')} ({row.get('duration_sec')}s)")
    print(f"  training_completed (from events tail): {report.get('pipeline_events_training_completed')}")
    print()

    hints = report.get("operator_hints") or []
    if hints:
        print("Hints")
        for h in hints:
            print(f"  - {h}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default=None, help="Run id under output/runs/<id>")
    parser.add_argument("--run-root", type=Path, default=None, help="Explicit run root path")
    parser.add_argument("--latest", action="store_true", help="Use most recently modified run under output/runs")
    parser.add_argument(
        "--tour",
        action="store_true",
        help="Include largest-file scan under the run tree (can be slow for very large outputs).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    args = parser.parse_args()

    repo = _repo_root()
    run_root = _resolve_run_root(repo, args.run_id, args.run_root, args.latest)
    report = gather_report(repo, run_root, heavy_tour=args.tour)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _print_human(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
