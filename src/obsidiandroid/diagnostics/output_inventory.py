"""Scan run output, classify artifacts, write inventory + evidence index."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from obsidiandroid.common.cohort_artifacts import load_cohort_contract_state
from obsidiandroid.common.cohort_presentation import cohort_filter_highlight_lines
from obsidiandroid.common import output_hygiene as oh
from . import output_artifact_policy
from obsidiandroid.cli.ui import display as du
from obsidiandroid.common.publication_readiness import evaluate_publication_ready_status
from obsidiandroid.common import ml_console


def _iter_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file():
            out.append(p)
    return sorted(out, key=lambda x: str(x))


def build_inventory_rows(run_root: Path) -> list[dict[str, Any]]:
    """Return flat inventory rows for every file under ``run_root``."""
    rows: list[dict[str, Any]] = []
    rr = run_root.resolve()
    provenance_path = rr / "diagnostics" / "diagnostic_provenance.json"
    post_run_paths: set[str] = set()
    if provenance_path.is_file():
        blob = _load_json(provenance_path)
        for entry in blob.get("entries", []) if isinstance(blob.get("entries"), list) else []:
            if bool(entry.get("generated_during_pipeline", False)):
                continue
            for artifact in entry.get("artifacts", []) if isinstance(entry.get("artifacts"), list) else []:
                rel = str(artifact.get("path", "") or "").strip()
                if rel and not rel.startswith("/"):
                    post_run_paths.add(rel)
    for path in _iter_files(rr):
        meta = output_artifact_policy.classify_file(path, base=rr)
        rel = meta.pop("relative_path", path.relative_to(rr).as_posix())
        lifecycle_class = meta.get("lifecycle_class")
        if rel in post_run_paths:
            lifecycle_class = "post_run_enrichment"
        try:
            sz = path.stat().st_size
        except OSError:
            sz = -1
        rows.append(
            {
                "path": rel,
                "artifact_type": meta.get("artifact_bucket"),
                "lifecycle_class": lifecycle_class,
                "producer_module": meta.get("producer_module"),
                "run_scoped": "yes" if meta.get("run_scoped") else "no",
                "required_for_paper_mode": "yes" if meta.get("required_for_paper_mode") else "no",
                "safe_to_delete_after_run": "yes" if meta.get("safe_to_delete_after_run") else "no",
                "duplicate_latest_copy": "yes" if meta.get("duplicate_latest_copy") else "no",
                "bytes": sz,
                "human_description": meta.get("human_description"),
            }
        )
    return rows


def _bucket_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        b = str(row.get("artifact_type", ""))
        counts[b] = counts.get(b, 0) + 1
    return counts


def write_virtual_layout(run_root: Path) -> Path | None:
    """Write logical buckets mapping paths → logical folders (no moves on disk)."""
    rows = build_inventory_rows(run_root)
    buckets: dict[str, list[str]] = {
        "evidence": [],
        "diagnostics/required": [],
        "diagnostics/optional": [],
        "diagnostics/debug": [],
        "diagnostics/post_run_enrichment": [],
        "models": [],
        "logs": [],
        "operator_misc": [],
    }
    for row in rows:
        rel = row["path"]
        typ = str(row.get("artifact_type", ""))
        lifecycle = str(row.get("lifecycle_class", ""))
        if lifecycle == "post_run_enrichment":
            buckets["diagnostics/post_run_enrichment"].append(rel)
        elif typ == "evidence_required":
            buckets["evidence"].append(rel)
        elif typ in {"diagnostics_required"}:
            buckets["diagnostics/required"].append(rel)
        elif typ in {"debug_only"}:
            buckets["diagnostics/debug"].append(rel)
        elif "models" in rel.replace("\\", "/"):
            buckets["models"].append(rel)
        elif "logs" in rel.replace("\\", "/"):
            buckets["logs"].append(rel)
        elif typ in {"diagnostics_optional"}:
            buckets["diagnostics/optional"].append(rel)
        else:
            buckets["operator_misc"].append(rel)
    path = run_root / "diagnostics" / "virtual_layout.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(buckets, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path
    except OSError:
        return None


def write_artifact_inventory_bundle(
    *,
    run_root: Path,
    diagnostics_dir: Path,
    run_id: str,
    manifest_paths: list[str] | None,
    extra_summary: dict[str, Any] | None,
) -> tuple[list[str], dict[str, Any]]:
    """Write CSV/MD/JSON inventory under ``diagnostics_dir`` and return paths + summary."""
    rows = build_inventory_rows(run_root)
    counts = _bucket_counts(rows)
    dup_latest_run = sum(
        1
        for r in rows
        if str(r.get("duplicate_latest_copy")) == "yes"
        and ".latest." in str(r.get("path", ""))
    )
    dup_latest_legacy_compat = sum(
        1
        for r in rows
        if str(r.get("duplicate_latest_copy")) == "yes"
        and ".latest." in str(r.get("path", ""))
        and str(r.get("lifecycle_class", "")) == "legacy_compatibility"
    )

    summary = {
        "run_id": run_id,
        "total_artifacts": len(rows),
        "bucket_counts": counts,
        "duplicate_latest_inside_run": dup_latest_run,
        "duplicate_latest_inside_run_legacy_compatibility": dup_latest_legacy_compat,
        "duplicate_latest_inside_run_policy_drift": max(
            dup_latest_run - dup_latest_legacy_compat,
            0,
        ),
        "manifest_path_count": len(manifest_paths or []),
    }
    if extra_summary:
        summary.update(extra_summary)

    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    json_path = diagnostics_dir / "artifact_inventory.json"
    csv_path = diagnostics_dir / "artifact_inventory.csv"
    md_path = diagnostics_dir / "artifact_inventory.md"

    json_payload = {"summary": summary, "rows": rows}
    json_path.write_text(json.dumps(json_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    fieldnames = [
        "path",
        "artifact_type",
        "lifecycle_class",
        "producer_module",
        "run_scoped",
        "required_for_paper_mode",
        "safe_to_delete_after_run",
        "duplicate_latest_copy",
        "bytes",
        "human_description",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in fieldnames})

    md_lines = [
        "# Artifact inventory",
        "",
        f"**run_id:** `{run_id}`",
        "",
        "## Summary",
        "",
        "```json",
        json.dumps(summary, indent=2, sort_keys=True),
        "```",
        "",
        "## Rows",
        "",
        "```json",
        json.dumps(rows, indent=2)[:120000],
        "```",
        "",
    ]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    return [str(json_path), str(csv_path), str(md_path)], summary


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _authority_coverage_report_path(*, diagnostics_dir: Path, run_id: str) -> Path | None:
    path = diagnostics_dir / f"family_type_authority_coverage_{run_id}.md"
    return path if path.exists() else None


def _taxonomy_authority_split_report_path(*, diagnostics_dir: Path, run_id: str) -> Path | None:
    path = diagnostics_dir / f"taxonomy_authority_split_{run_id}.md"
    return path if path.exists() else None


def write_run_evidence_index_md(
    *,
    run_root: Path,
    diagnostics_dir: Path,
    run_id: str,
    profile_id: str,
    paper_mode: bool,
    cohort_size: int,
    manifest: dict[str, Any] | None,
    manifest_context: dict[str, Any] | None,
    trained_models: list[str] | None,
    paper_safe_status: str,
    paper_safe_reasons: list[str],
) -> Path | None:
    """First-stop Markdown summary for researchers."""
    summary_obs = _load_json(diagnostics_dir / "run_observability_summary.json")
    counts_mirror = summary_obs.get("counts") if isinstance(summary_obs.get("counts"), dict) else {}

    cohort_display = cohort_size
    if counts_mirror.get("cohort_prepared_row_count") is not None:
        cohort_display = int(counts_mirror["cohort_prepared_row_count"])
    elif counts_mirror.get("governed_cohort_rows") is not None:
        cohort_display = int(counts_mirror["governed_cohort_rows"])

    aligned_training_n = int((manifest or {}).get("cohort_size", cohort_display) or 0)
    ms = (manifest or {}).get("model_summary", {}) if isinstance(manifest, dict) else {}
    top_model = str(ms.get("top_model", "") or "")
    top_f1 = ms.get("top_macro_f1")
    train_n = (manifest or {}).get("train_sample_count") if isinstance(manifest, dict) else None
    test_n = (manifest or {}).get("test_sample_count") if isinstance(manifest, dict) else None
    feat_n = (manifest or {}).get("feature_matrix_cols_post_prune") if isinstance(manifest, dict) else None
    if feat_n in (None, "") and isinstance(manifest, dict):
        feat_n = manifest.get("feature_matrix_row_count")
    if train_n in (None, "") and counts_mirror.get("train_rows") is not None:
        train_n = counts_mirror["train_rows"]
    if test_n in (None, "") and counts_mirror.get("test_rows") is not None:
        test_n = counts_mirror["test_rows"]
    feats_obs = summary_obs.get("features") if isinstance(summary_obs.get("features"), dict) else {}
    if feat_n in (None, "") and feats_obs.get("post_prune") is not None:
        feat_n = feats_obs["post_prune"]
    row_auth = (manifest or {}).get("main_training_row_authority") if isinstance(manifest, dict) else None
    trained_n = (manifest or {}).get("trained_model_count") if isinstance(manifest, dict) else None
    if trained_n is None and trained_models:
        trained_n = len(trained_models)

    gap_path = diagnostics_dir / "ablation_cohort_gap_summary.json"
    ablation_ok = True
    ablation_note = "No ablation cohort audit found (stage skipped or not exported)."
    if gap_path.exists():
        gap = _load_json(gap_path)
        zfill = bool(gap.get("ablation_cohort_reindex_zero_fill", True))
        ablation_ok = True
        rows_g = gap.get("feature_set_rows") if isinstance(gap.get("feature_set_rows"), list) else []
        if rows_g:
            for row in rows_g:
                if str(row.get("status", "")).upper() not in {"OK", ""}:
                    if row.get("status"):
                        ablation_ok = False
        ablation_note = (
            f"zero_fill_policy={zfill}; rows_exported={len(rows_g)} "
            f"(see `{gap_path.name}`)."
        )

    feat_before = manifest.get("feature_count_pre_prune") if isinstance(manifest, dict) else None
    feat_after = manifest.get("feature_count_post_prune") if isinstance(manifest, dict) else None
    dropped = None
    if isinstance(feat_before, int) and isinstance(feat_after, int):
        dropped = max(feat_before - feat_after, 0)

    cov_path = oh.resolve_feature_build_coverage_path(diagnostics_dir, run_id)
    missing_n = None
    if cov_path.exists():
        cov = _load_json(cov_path)
        missing_n = cov.get("missing_from_feature_matrix_count") or cov.get("missing_count")
    authority_md = _authority_coverage_report_path(diagnostics_dir=diagnostics_dir, run_id=run_id)
    taxonomy_split_md = _taxonomy_authority_split_report_path(diagnostics_dir=diagnostics_dir, run_id=run_id)

    lines = [
        "# Run evidence index",
        "",
        "**Open this file first.** It routes you to cohort definitions, audits, and publication-ready artifacts.",
        "",
        "**Canonical rollup:** `run_observability_summary.json` in diagnostics (mirror of observability verdicts; aligns with terminal **Run Health**).",
        "",
        "## Run identity",
        "",
        f"- **run_id:** `{run_id}`",
        f"- **profile:** `{profile_id}`",
        f"- **evidence / publication-ready mode:** `{'on' if paper_mode else 'off'}`",
        "",
        "## Observability mirror (from run_observability_summary.json when present)",
        "",
    ]
    if summary_obs:
        pipe_st = summary_obs.get("pipeline_status")
        rv_st = summary_obs.get("research_validity_status")
        rv_skip = summary_obs.get("research_validity_skip_reason")
        ha_st = summary_obs.get("hostile_audit_status")
        ha_skip = summary_obs.get("hostile_audit_skip_reason")
        ps_safe = summary_obs.get("publication_ready_status") or summary_obs.get("paper_safe_status")
        rv_line = f"`{rv_st}`"
        if str(rv_skip or "").strip():
            rv_line = f"`{rv_st}` ({rv_skip})"
        ha_line = f"`{ha_st}`"
        if str(ha_skip or "").strip():
            ha_line = f"`{ha_st}` ({ha_skip})"
        lines.extend(
            [
                f"- **pipeline_status:** `{pipe_st}`",
                f"- **research_validity_status:** {rv_line}",
                f"- **hostile_audit_status:** {ha_line}",
                f"- **publication_ready_status:** `{ps_safe}`",
                f"- **cohort funnel (rollup):** {summary_obs.get('cohort_funnel_plain','')}".rstrip(),
                "",
            ]
        )
    else:
        lines.extend(
            [
                "_Summary not yet on disk — re-open after finalize completes._",
                "",
            ]
        )

    lines.extend(
        [
            "## Cohort & features",
            "",
            f"- **Cohort size (manifest):** {cohort_display}",
            f"- **Aligned training size (best-effort):** {aligned_training_n}",
            f"- **Train shard (split audit):** {train_n}",
            f"- **Test shard (split audit):** {test_n}",
            f"- **Fitted feature columns (post-prune):** {feat_n}",
            f"- **main_training_row_authority:** `{row_auth}`",
            f"- **Trained model count:** {trained_n}",
            f"- **Missing-from-feature-matrix count (coverage export):** {missing_n if missing_n is not None else 'see feature_build_coverage*.json'}",
            f"- **Feature count pre/post prune:** {feat_before} → {feat_after} (dropped {dropped if dropped is not None else 'n/a'})",
            "",
            "## Models",
            "",
            f"- **Trained models:** {', '.join(trained_models or []) or 'see run_manifest.json'}",
            f"- **Top model (Macro-F1):** `{top_model}` ({top_f1})",
            "",
            "## Ablation cohort integrity",
            "",
            f"- **Status:** {'PASS' if ablation_ok else 'REVIEW'} — {ablation_note}",
            "",
            "## Publication-ready gate",
            "",
            f"- **publication_ready_status:** `{paper_safe_status}`",
        ]
    )
    if paper_safe_reasons and paper_safe_status == "FAIL":
        lines.append(f"- **reasons:** {', '.join(paper_safe_reasons)}")
    lines.extend(
        [
            "",
            "## Primary paths",
            "",
            f"- Run manifest: `{run_root / 'run_manifest.json'}`",
            f"- Run summary JSON: `{run_root / 'run_summary.json'}`",
            f"- Observability summary JSON: `{diagnostics_dir / 'run_observability_summary.json'}`",
            f"- Diagnostics dir: `{diagnostics_dir}`",
            f"- Inventory: `{diagnostics_dir / 'artifact_inventory.md'}`",
            f"- Virtual layout (logical buckets): `{diagnostics_dir / 'virtual_layout.json'}`",
            "",
        ]
    )
    if authority_md is not None:
        lines.insert(-1, f"- Authority coverage diagnostic: `{authority_md}`")
    if taxonomy_split_md is not None:
        lines.insert(-1, f"- Taxonomy authority split: `{taxonomy_split_md}`")
    out = run_root / "run_evidence_index.md"
    try:
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out
    except OSError:
        return None


def write_run_science_index_md(
    *,
    run_root: Path,
    diagnostics_dir: Path,
    run_id: str,
    profile_id: str,
    evidence_mode: bool,
    cohort_locked: bool,
    publication_ready_status: str,
) -> Path | None:
    """Write a compact operator-first run science index with lifecycle guidance."""
    rows = build_inventory_rows(run_root)
    by_lifecycle: dict[str, list[str]] = {}
    for row in rows:
        key = str(row.get("lifecycle_class", "diagnostics_optional"))
        by_lifecycle.setdefault(key, []).append(str(row.get("path", "")))

    provenance_path = diagnostics_dir / "diagnostic_provenance.json"
    provenance = _load_json(provenance_path)
    summary_obs = _load_json(diagnostics_dir / "run_observability_summary.json")
    cohort_state = load_cohort_contract_state(diagnostics_dir=diagnostics_dir, run_id=run_id)
    post_entries = [
        row
        for row in (provenance.get("entries") if isinstance(provenance.get("entries"), list) else [])
        if not bool(row.get("generated_during_pipeline", False))
    ]

    mode_tags: list[str] = ["evidence" if evidence_mode else "exploratory"]
    if cohort_locked:
        mode_tags.append("cohort-locked")
    if str(publication_ready_status).strip():
        mode_tags.append(f"publication-ready={publication_ready_status}")

    authoritative_paths = [
        run_root / "run_manifest.json",
        run_root / "run_summary.json",
        diagnostics_dir / "run_observability_summary.json",
        diagnostics_dir / "cohort_foundation.json",
        diagnostics_dir / "cohort_funnel.md",
        run_root / "run_evidence_index.md",
        diagnostics_dir / "artifact_inventory.json",
    ]
    authority_md = _authority_coverage_report_path(diagnostics_dir=diagnostics_dir, run_id=run_id)
    taxonomy_split_md = _taxonomy_authority_split_report_path(diagnostics_dir=diagnostics_dir, run_id=run_id)

    lines = [
        f"# Run Science Index ({run_id})",
        "",
        "**Open this file first for run-science review.**",
        "",
        "## Run",
        "",
        f"- run_id: `{run_id}`",
        f"- profile_id: `{profile_id}`",
        f"- mode: `{', '.join(mode_tags)}`",
        "",
        "## Authoritative files",
        "",
    ]
    lines.extend([f"- `{path}`" for path in authoritative_paths if path.exists()])
    if authority_md is not None:
        lines.extend(
            [
                "",
                "## Advisory Authority Diagnostic",
                "",
                f"- `{authority_md}`",
            ]
        )
    if taxonomy_split_md is not None:
        lines.extend(
            [
                "",
                "## Taxonomy Authority Split",
                "",
                f"- `{taxonomy_split_md}`",
            ]
        )
    lines.extend([
        "",
        "## Observability mirror",
        "",
    ])
    if summary_obs:
        rv_st = summary_obs.get("research_validity_status")
        rv_skip = summary_obs.get("research_validity_skip_reason")
        ha_st = summary_obs.get("hostile_audit_status")
        ha_skip = summary_obs.get("hostile_audit_skip_reason")
        pipe_st = summary_obs.get("pipeline_status")
        ps_safe = summary_obs.get("publication_ready_status") or summary_obs.get("paper_safe_status")
        rv_line = f"`{rv_st}`"
        if str(rv_skip or "").strip():
            rv_line = f"`{rv_st}` ({rv_skip})"
        ha_line = f"`{ha_st}`"
        if str(ha_skip or "").strip():
            ha_line = f"`{ha_st}` ({ha_skip})"
        lines.extend([
            f"- **pipeline_status:** `{pipe_st}`",
            f"- **research_validity_status:** {rv_line}",
            f"- **hostile_audit_status:** {ha_line}",
            f"- **publication_ready_status:** `{ps_safe}`",
            "",
        ])
    else:
        lines.extend([
            "- observability summary unavailable",
            "",
        ])
    lines.extend([
        "## Cohort Filter Highlights",
        "",
    ])
    lines.extend(cohort_filter_highlight_lines(cohort_state))
    lines.extend([
        "Post-run audits do not change the authoritative record of the original pipeline run.",
        "",
        "## Mirrors And Compatibility",
        "",
        f"- operator_convenience_mirror: **{len(by_lifecycle.get('operator_convenience_mirror', []))}**",
        f"- legacy_compatibility: **{len(by_lifecycle.get('legacy_compatibility', []))}**",
        "- Warnings: prefer run-scoped artifacts over any `.latest` file.",
        f"- Provenance ledger: `{provenance_path}`",
        "",
        "## Post-Run Enrichments",
        "",
    ])
    if not post_entries:
        lines.append("- none recorded")
    else:
        lines.append(
            f"- Stored under: `{diagnostics_dir / 'post_run_enrichments'}`"
        )
        for entry in post_entries:
            lines.append(
                f"- `{entry.get('entry_id', '')}` via `{entry.get('source_command', '')}` "
                f"at `{entry.get('generated_at_utc', '')}`"
            )
            for artifact in (entry.get("artifacts") if isinstance(entry.get("artifacts"), list) else [])[:8]:
                lines.append(f"  path: `{artifact.get('path', '')}`")
    lines.extend(
        [
            "",
            "## Lifecycle Counts",
            "",
        ]
    )
    for key in (
        "canonical_run_evidence",
        "diagnostics_required",
        "diagnostics_optional",
        "operator_convenience_mirror",
        "legacy_compatibility",
        "post_run_enrichment",
        "debug_only",
    ):
        lines.append(f"- {key}: **{len(by_lifecycle.get(key, []))}**")

    out_path = diagnostics_dir / "run_science_index.md"
    try:
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out_path
    except OSError:
        return None


def print_output_hygiene_terminal_summary(
    *,
    run_root: Path,
    summary: dict[str, Any],
    evidence_index_path: Path | None,
    paper_safe_status: str,
) -> None:
    if ml_console.is_minimal():
        return
    bc = summary.get("bucket_counts") if isinstance(summary, dict) else {}
    du.print_section("Output Summary")
    du.print_stat("Run folder", str(run_root))
    du.print_stat("Total artifacts", summary.get("total_artifacts"))
    du.print_stat("Evidence-classified rows", bc.get("evidence_required", 0))
    du.print_stat("Required diagnostics rows", bc.get("diagnostics_required", 0))
    du.print_stat("Optional diagnostics rows", bc.get("diagnostics_optional", 0))
    du.print_stat("Debug rows", bc.get("debug_only", 0))
    du.print_stat(
        "Run-local .latest policy drift",
        summary.get("duplicate_latest_inside_run_policy_drift", summary.get("duplicate_latest_inside_run", 0)),
    )
    legacy_latest = summary.get("duplicate_latest_inside_run_legacy_compatibility", 0)
    if int(legacy_latest or 0) > 0:
        du.print_stat(
            "Legacy .latest compatibility copies",
            legacy_latest,
        )
    du.print_stat("Publication-ready status", paper_safe_status)


def evaluate_paper_safe_status(
    *,
    paper_mode: bool,
    manifest: dict[str, Any] | None,
    compliance_report: dict[str, Any] | None,
) -> tuple[str, list[str]]:
    """Return paper_safe_status string for operator summary (strict checks remain in compliance JSON)."""
    return evaluate_publication_ready_status(
        paper_mode=paper_mode,
        manifest=manifest,
        compliance_report=compliance_report,
    )


__all__ = [
    "build_inventory_rows",
    "evaluate_paper_safe_status",
    "print_output_hygiene_terminal_summary",
    "write_artifact_inventory_bundle",
    "write_run_evidence_index_md",
    "write_run_science_index_md",
    "write_virtual_layout",
]
