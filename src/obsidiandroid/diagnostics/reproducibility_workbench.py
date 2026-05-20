"""Post-run reproducibility, research validity, and run comparison helpers.

These routines support the operator menu **without** training models. They prefer
run-scoped paths under ``output/runs/<run_id>/diagnostics/`` and fall back to
legacy global ``output/diagnostics/`` when needed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Mapping
from typing import Any, Callable, Iterable

import pandas as pd

from config import app_config

from obsidiandroid.common.cohort_artifacts import load_cohort_contract_state
from obsidiandroid.common.cohort_presentation import cohort_methodology_summary
from obsidiandroid.common.cohort_methodology import resolve_cohort_lock_status
from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common import output_paths
from obsidiandroid.common.json_io import read_json_dict
from obsidiandroid.common.publication_readiness import coalesce_publication_ready_status
from obsidiandroid.governance.evidence_mode_resolver import coalesce_manifest_publication_mode
from obsidiandroid.diagnostics.diagnostic_provenance import latest_post_run_enrichment_dir
from obsidiandroid.diagnostics.split_ledger_resolve import resolve_split_freeze_csv


def run_scoped_diagnostics(output_root: Path, run_id: str) -> Path:
    """Return ``runs/<run_id>/diagnostics`` (may not exist yet)."""
    return Path(output_root) / "runs" / str(run_id).strip() / "diagnostics"


def global_diagnostics(output_root: Path) -> Path:
    return Path(output_root) / "diagnostics"


def pick_first_existing(paths: Iterable[Path]) -> tuple[Path | None, list[str]]:
    """Return first existing path and list of candidates tried (for diagnostics text)."""
    tried: list[str] = []
    for p in paths:
        tried.append(str(p))
        if p.is_file():
            return p, tried
    return None, tried


def _df_to_markdown_table(df: pd.DataFrame) -> str:
    """Render a small dataframe as a GitHub-flavored markdown table (no extra deps)."""
    if df.empty:
        return "_Empty table._\n"
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in df.iterrows():
        cells = [str(row[c]) if row[c] is not None else "" for c in df.columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _ablation_macro_f1_by_experiment(diagnostics_dir: Path, run_id: str) -> dict[str, float | None]:
    """Best Macro-F1 per experiment label from feature_set_ablation_summary.csv when present."""
    out: dict[str, float | None] = {
        "permissions_raw": None,
        "full_fused": None,
    }
    path = oh.resolve_feature_set_ablation_summary_path(diagnostics_dir, run_id)
    if not path.is_file():
        return out
    try:
        ab = pd.read_csv(path)
    except Exception:
        return out
    if ab.empty or "experiment" not in ab.columns or "macro_f1_score" not in ab.columns:
        return out
    ab = ab.copy()
    ab["macro_f1_score"] = pd.to_numeric(ab["macro_f1_score"], errors="coerce")
    for exp in ("permissions_raw", "full_fused"):
        sub = ab[ab["experiment"].astype(str).str.strip() == exp]
        if sub.empty:
            continue
        try:
            out[exp] = float(sub["macro_f1_score"].max())
        except (TypeError, ValueError):
            out[exp] = None
    return out

def _collect_cohort_methodology(output_root: Path, run_id: str) -> dict[str, Any]:
    """Read run-scoped cohort methodology artifacts for cross-run comparisons."""
    state = load_cohort_contract_state(
        diagnostics_dir=run_scoped_diagnostics(output_root, run_id),
        run_id=run_id,
    )
    return {
        "cohort_membership_mode": state.get("cohort_membership_mode", "standard_contract_filters"),
        "min_malicious_detections_threshold": state.get("min_malicious_detections_threshold", 0),
        "rescued_unknown_consensus": state.get("min_malicious_detections_rescued_unknown_consensus", 0),
    }


def list_run_ids_newest_first(*, limit: int | None = None) -> list[str]:
    """Run IDs under ``output/runs`` with ``run_manifest.json``, newest first."""
    # Lazy import avoids importing CLI packages when this module is loaded from tests only.
    from obsidiandroid.cli.menu import run_locator as rl

    runs_dir = output_paths.runs_root()
    if not runs_dir.exists():
        return []
    scored: list[tuple[tuple[int, datetime, str], str]] = []
    for child in runs_dir.iterdir():
        if not child.is_dir():
            continue
        if not (child / "run_manifest.json").is_file():
            continue
        rid = child.name.strip()
        if not rid:
            continue
        manifest_payload = rl.read_json_object(child / "run_manifest.json")
        key = rl.candidate_sort_key(run_id=rid, manifest_payload=manifest_payload)
        if key is None:
            continue
        scored.append((key, rid))
    scored.sort(key=lambda item: item[0], reverse=True)
    out = [rid for _, rid in scored]
    if limit is not None:
        return out[: max(0, limit)]
    return out


def _warn_plain(name: str, chosen: Path | None, tried: list[str]) -> str:
    if chosen is not None:
        return ""
    if name == "parser_quality_snapshot":
        return (
            "No parser quality CSV found (checked run-scoped parser_quality_final_*.csv, "
            "then parser_quality_<run_id>.csv or legacy output/diagnostics/parser_quality.latest.csv). "
            "Vendor stage may be skipped or exports only run-scoped finals."
        )
    if name == "run_paths_manifest_exists":
        return (
            "Run paths manifest missing in both run diagnostics and global diagnostics. "
            "Manifest finalization may not have completed."
        )
    return f"Missing artifact; checked: {' | '.join(tried[:4])}"


def build_filesystem_artifact_checks(
    *,
    output_root: Path,
    effective_run_id: str,
    canonical_manifest: dict[str, Any],
    run_root: Path,
    run_summary: dict[str, Any],
    timestamp_source: str,
) -> tuple[list[dict[str, str]], int, int]:
    """Return health rows plus warn/fail counts for filesystem-backed checks."""
    rows: list[dict[str, str]] = []
    fail_count = 0
    warn_count = 0

    def add(
        name: str,
        status: str,
        detail: str,
        *,
        plain: str = "",
        bucket: str = "infra",
    ) -> None:
        nonlocal fail_count, warn_count
        st = status.upper().strip()
        if st == "FAIL":
            fail_count += 1
        elif st == "WARN":
            warn_count += 1
        rows.append(
            {
                "check": name,
                "status": st,
                "detail": detail,
                "plain_language": plain,
                "bucket": bucket,
            }
        )

    gdiag = global_diagnostics(output_root)
    rdiag = run_scoped_diagnostics(output_root, effective_run_id)

    if effective_run_id and run_root.exists():
        add("run_root_exists", "PASS", str(run_root))
    elif effective_run_id:
        add("run_root_exists", "WARN", f"Missing run-scoped directory: {run_root}")

    if run_summary:
        add("run_summary_exists", "PASS", str(run_root / "run_summary.json"))
        run_status = str(run_summary.get("run_status", "")).strip().lower()
        if run_status == "failed":
            add(
                "run_summary_status",
                "FAIL",
                str(run_summary.get("failure_reason", "run_summary.json marks run as failed")),
            )
        else:
            add("run_summary_status", "PASS", run_status or "complete")
    elif run_root.exists():
        add(
            "run_summary_exists",
            "WARN",
            f"Missing canonical run summary: {run_root / 'run_summary.json'}",
        )

    if timestamp_source:
        try:
            parsed_ts = datetime.fromisoformat(timestamp_source.replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - parsed_ts).total_seconds() / 3600.0
            if age_hours > 48:
                add("latest_run_freshness", "WARN", f"Run age is {age_hours:.1f}h (>48h).")
            else:
                add("latest_run_freshness", "PASS", f"Run age is {age_hours:.1f}h.")
        except ValueError:
            add("latest_run_freshness", "WARN", f"Unparseable UTC timestamp: {timestamp_source}")
    else:
        add("latest_run_freshness", "WARN", "No timestamp found in manifest.")

    split_path = str((canonical_manifest.get("split") or {}).get("split_audit_path", "")).strip()
    if split_path:
        split_file = Path(split_path)
        add(
            "split_audit_exists",
            "PASS" if split_file.exists() else "FAIL",
            str(split_file),
            bucket="core",
        )
    else:
        picked = resolve_split_freeze_csv(rdiag, effective_run_id)
        tried = [
            str(rdiag / f"split_freeze_headline_{effective_run_id}.csv"),
            str(rdiag / "split_freeze_headline.latest.csv"),
            str(oh.global_diagnostics_root() / "split_freeze_headline.latest.csv"),
            str(rdiag / f"split_freeze_audit_{effective_run_id}.csv"),
            str(rdiag / "split_freeze_audit.latest.csv"),
            str(oh.global_diagnostics_root() / "split_freeze_audit.latest.csv"),
        ]
        if picked is not None:
            add("split_audit_exists", "PASS", str(picked), bucket="core")
        else:
            add(
                "split_audit_exists",
                "WARN",
                "No split_audit_path in manifest and no run-scoped split CSV found.",
                plain="Split ledger not linked from manifest; check training stage.",
                bucket="core",
            )

    model_config_path = str(canonical_manifest.get("model_config_snapshot_path", "")).strip()
    if model_config_path:
        model_config_file = Path(model_config_path)
    else:
        model_config_file = gdiag / "model_config_snapshot.latest.json"
    add(
        "model_config_snapshot_exists",
        "PASS" if model_config_file.exists() else "FAIL",
        str(model_config_file),
        bucket="core",
    )

    vendor_gate_path = str(canonical_manifest.get("vendor_gate_debug_path", "")).strip()
    if vendor_gate_path:
        vendor_gate_file = Path(vendor_gate_path)
        add(
            "vendor_gate_debug_exists",
            "PASS" if vendor_gate_file.exists() else "WARN",
            str(vendor_gate_file),
        )
    else:
        add("vendor_gate_debug_exists", "WARN", "No vendor_gate_debug_path recorded in manifest.")

    pq_candidates = [
        oh.resolve_parser_quality_final_path(rdiag, effective_run_id),
        oh.resolve_parser_quality_path(rdiag, effective_run_id),
    ]
    pq_path, pq_tried = pick_first_existing(pq_candidates)
    pq_status = "PASS" if pq_path is not None else "WARN"
    add(
        "parser_quality_snapshot_exists",
        pq_status,
        str(pq_path) if pq_path else pq_tried[0],
        plain=_warn_plain("parser_quality_snapshot", pq_path, pq_tried),
    )

    cov_candidates = [oh.resolve_vendor_parser_coverage_path(rdiag, effective_run_id)]
    cov_path, cov_tried = pick_first_existing(cov_candidates)
    add(
        "parser_coverage_snapshot_exists",
        "PASS" if cov_path is not None else "WARN",
        str(cov_path) if cov_path else cov_tried[0],
    )

    rpm_candidates = [
        rdiag / f"run_paths_manifest_{effective_run_id}.json",
        gdiag / f"run_paths_manifest_{effective_run_id}.json",
    ]
    rpm_path, rpm_tried = pick_first_existing(rpm_candidates)
    rpm_status = "PASS" if rpm_path is not None else "WARN"
    add(
        "run_paths_manifest_exists",
        rpm_status,
        str(rpm_path) if rpm_path else rpm_tried[0],
        plain=_warn_plain("run_paths_manifest_exists", rpm_path, rpm_tried),
        bucket="core",
    )

    research_artifacts: list[tuple[str, list[Path], str]] = [
        (
            "diagnostics_index_md",
            [rdiag / "index.md", gdiag / "index.md"],
            "Diagnostics index / artifact map",
        ),
        (
            "dataset_foundation_summary_md",
            [rdiag / "dataset_foundation_summary.md", gdiag / "dataset_foundation_summary.md"],
            "Q1 dataset foundation summary",
        ),
        (
            "modality_contribution_summary_md",
            [rdiag / "modality_contribution_summary.md", gdiag / "modality_contribution_summary.md"],
            "Q2 modality contribution summary",
        ),
        (
            "model_and_family_failure_summary_md",
            [rdiag / "model_and_family_failure_summary.md", gdiag / "model_and_family_failure_summary.md"],
            "Q3 model/family failure summary",
        ),
        (
            "headline_score_scope_md",
            [rdiag / "headline_score_scope.md", gdiag / "headline_score_scope.md"],
            "Headline score scope",
        ),
        (
            "high_score_audit_md",
            [rdiag / "high_score_audit.md", gdiag / "high_score_audit.md"],
            "High-score skeptic audit",
        ),
        (
            "feature_contract_json",
            [oh.resolve_feature_contract_path(rdiag, effective_run_id)],
            "Feature contract",
        ),
        (
            "leakage_assessment_txt",
            [oh.resolve_leakage_assessment_path(rdiag, effective_run_id)],
            "Leakage assessment",
        ),
        (
            "modality_method_contract_json",
            [oh.resolve_modality_method_contract_path(rdiag, effective_run_id)],
            "Modality method contract",
        ),
        (
            "split_freeze_headline_csv",
            [resolve_split_freeze_csv(rdiag, effective_run_id) or (rdiag / f"split_freeze_headline_{effective_run_id}.csv")],
            "Split freeze headline ledger",
        ),
    ]

    for check_key, candidates, label in research_artifacts:
        picked, tried = pick_first_existing(candidates)
        st = "PASS" if picked is not None else "WARN"
        add(
            check_key,
            st,
            str(picked) if picked else tried[0],
            plain="" if picked else f"{label}: optional research artifact not found.",
            bucket="research",
        )

    return rows, fail_count, warn_count


def write_run_health_artifact_reports(
    *,
    diagnostics_out_dir: Path,
    payload: dict[str, Any],
) -> tuple[Path, Path]:
    """Write JSON + Markdown summaries under diagnostics."""
    diagnostics_out_dir.mkdir(parents=True, exist_ok=True)
    md_path = diagnostics_out_dir / "run_health_artifact_check.md"
    json_path = diagnostics_out_dir / "run_health_artifact_check.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    meta = payload.get("meta") or {}
    summary = payload.get("summary") or {}
    lines = [
        "# Run health & artifact check",
        "",
        f"- **Run ID:** `{meta.get('run_id', '')}`",
        f"- **Status:** {meta.get('run_status', 'n/a')}",
        f"- **Profile:** {meta.get('profile_id', 'n/a')}",
        f"- **Run root:** `{meta.get('run_root', '')}`",
        "",
        "## Summary",
        "",
        f"- PASS: **{summary.get('pass', 0)}** · WARN: **{summary.get('warn', 0)}** · FAIL: **{summary.get('fail', 0)}**",
        "",
        "## Checks",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for row in payload.get("checks") or []:
        if isinstance(row, dict):
            lines.append(
                f"| `{row.get('check', '')}` | {row.get('status', '')} | {row.get('detail', '')} |"
            )
    warn_plain = [r for r in (payload.get("checks") or []) if str(r.get("status")) == "WARN" and r.get("plain_language")]
    if warn_plain:
        lines.extend(["", "## Warnings (plain language)", ""])
        for r in warn_plain:
            lines.append(f"- **{r.get('check')}:** {r.get('plain_language')}")
    interp = str(payload.get("interpretation") or "").strip()
    if interp:
        lines.extend(["", "## Interpretation", "", interp, ""])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path


def write_research_validity_review(
    *,
    output_root: Path,
    run_id: str,
    print_fn: Callable[[str], None] | None = None,
) -> tuple[Path, Path]:
    """Aggregate existing diagnostics into a single review artifact (no training)."""
    pr = print_fn or (lambda _s: None)
    rdiag = run_scoped_diagnostics(output_root, run_id)
    gdiag = global_diagnostics(output_root)

    def load_rel(names: list[str]) -> tuple[dict[str, Any], Path | None]:
        for name in names:
            for base in (rdiag, gdiag):
                p = base / name
                blob = read_json_dict(p)
                if blob:
                    return blob, p
        return {}, None

    q1, _ = load_rel(["dataset_foundation_summary.json"])
    q2, _ = load_rel(["modality_contribution_summary.json"])
    q3, _ = load_rel(["model_and_family_failure_summary.json"])
    scope, _ = load_rel(["headline_score_scope.json"])
    skeptical, _ = load_rel(["high_score_audit.json"])
    taxonomy_path = oh.resolve_taxonomy_consistency_summary_path(rdiag, run_id)
    taxonomy = read_json_dict(taxonomy_path) if taxonomy_path.is_file() else {}

    from obsidiandroid.diagnostics.headline_ablation_parity import build_feature_contract_comparison

    feature_contract = build_feature_contract_comparison(rdiag, run_id, manifest_context=None)

    macros = _ablation_macro_f1_by_experiment(rdiag, run_id)
    if all(v is None for v in macros.values()):
        macros = _ablation_macro_f1_by_experiment(gdiag, run_id)

    leak_csv = rdiag / "leakage_safe_score_comparison.csv"
    if not leak_csv.is_file():
        leak_csv = gdiag / "leakage_safe_score_comparison.csv"

    fam_csv = rdiag / "family_label_taxonomy_audit.csv"
    fam_avail = fam_csv.is_file()
    support_md = rdiag / "support_threshold_preview.md"
    support_avail = support_md.is_file()
    latest_enrichment = latest_post_run_enrichment_dir(rdiag)
    fam_post_avail = False
    support_post_avail = False
    if latest_enrichment is not None:
        fam_post_avail = (latest_enrichment / "family_label_taxonomy_audit.csv").is_file()
        support_post_avail = (latest_enrichment / "support_threshold_preview.md").is_file()

    headline_task = scope.get("trainable_family_classification_task") or {}
    aligned_sup = q1.get("aligned_supervised_samples")
    trainable_q1 = q1.get("trainable_after_support_filter")
    dropped_est = None
    try:
        if aligned_sup not in (None, "") and trainable_q1 not in (None, ""):
            dropped_est = max(0, int(aligned_sup) - int(trainable_q1))
    except (TypeError, ValueError):
        dropped_est = None

    payload: dict[str, Any] = {
        "run_id": run_id,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "dataset": {
            "governed_samples": q1.get("governed_samples"),
            "governed_families": q1.get("families_represented"),
            "malware_types": q1.get("malware_types_represented"),
            "aligned_supervised_samples": aligned_sup,
            "trainable_samples": headline_task.get("samples_after_support_filter") or trainable_q1,
            "trainable_families": headline_task.get("families_after_support_filter"),
            "samples_dropped_before_training": headline_task.get("samples_dropped_before_training") or dropped_est,
            "families_dropped_est": headline_task.get("families_dropped_before_training_est"),
        },
        "feature_signal": {
            "permission_signal_pct": q2.get("permission_signal_pct"),
            "vendor_merge_pct": q2.get("vendor_merge_pct"),
            "permissions_raw_macro_f1": macros.get("permissions_raw"),
            "full_fused_macro_f1": macros.get("full_fused"),
        },
        "high_score_caution": {
            "headline_macro_f1": q3.get("macro_f1"),
            "headline_model": q3.get("headline_model"),
            "notes": (skeptical.get("interpretation") if isinstance(skeptical, dict) else None),
        },
        "taxonomy": {
            "taxonomy_mismatch_count": taxonomy.get("taxonomy_mismatch_count"),
            "paper_facing_taxonomy_mismatch_count": taxonomy.get("paper_facing_taxonomy_mismatch_count"),
            "type_mapping_mismatch_count": taxonomy.get("type_mismatch_count"),
            "type_missing_label_count": taxonomy.get("type_missing_label_count"),
            "type_noncanonical_count": taxonomy.get("type_noncanonical_count"),
            "family_label_mismatch_count": taxonomy.get("family_label_mismatch_count"),
            "prediction_error_count": taxonomy.get("prediction_error_count"),
        },
        "feature_contract_comparison": feature_contract,
        "artifacts_used": {
            "dataset_foundation_summary": bool(q1),
            "modality_contribution_summary": bool(q2),
            "model_and_family_failure_summary": bool(q3),
            "headline_score_scope": bool(scope),
            "high_score_audit": bool(skeptical),
            "taxonomy_consistency_summary": bool(taxonomy),
            "family_label_taxonomy_audit_csv": fam_avail,
            "support_threshold_preview_md": support_avail,
            "family_label_taxonomy_audit_csv_post_run": fam_post_avail,
            "support_threshold_preview_md_post_run": support_post_avail,
            "leakage_safe_score_comparison_csv": leak_csv.is_file(),
            "headline_vs_ablation_contract_comparison": bool(
                oh.resolve_headline_vs_ablation_contract_comparison_path(rdiag, run_id).is_file()
            ),
            "taxonomy_type_authority_review": bool(
                oh.resolve_taxonomy_type_authority_review_path(rdiag, run_id).is_file()
            ),
        },
        "claim_readiness": _build_claim_readiness(
            q1, q2, q3, taxonomy, scope, feature_contract=feature_contract
        ),
    }

    md_lines = [
        "# Research validity review",
        "",
        f"Run: `{run_id}`",
        "",
        "## Dataset",
        "",
        f"- Governed cohort: **{payload['dataset'].get('governed_samples', '—')}** samples · "
        f"**{payload['dataset'].get('governed_families', '—')}** family labels · "
        f"**{payload['dataset'].get('malware_types', '—')}** malware types",
        f"- Headline supervised task: **{payload['dataset'].get('trainable_samples', '—')}** samples · "
        f"**{payload['dataset'].get('trainable_families', '—')}** supported families",
        f"- Dropped by support filter (estimate): **{payload['dataset'].get('samples_dropped_before_training', '—')}** samples",
        "",
        "## Feature signal",
        "",
        f"- Permission signal (share of cohort): **{payload['feature_signal'].get('permission_signal_pct', '—')}**%",
        f"- Parsed vendor merge authority: **{payload['feature_signal'].get('vendor_merge_pct', '—')}**%",
        f"- permissions_raw Macro-F1 (ablation): **{payload['feature_signal'].get('permissions_raw_macro_f1', '—')}**",
        f"- full_fused Macro-F1 (ablation): **{payload['feature_signal'].get('full_fused_macro_f1', '—')}**",
        "",
        "## High-score caution",
        "",
        f"- Headline model Macro-F1 (Q3 summary): **{payload['high_score_caution'].get('headline_macro_f1', '—')}** "
        f"({payload['high_score_caution'].get('headline_model', '—')})",
        "- Applies to the **supported-family** benchmark when support filtering is active — see `headline_score_scope.json`.",
        "",
        "## Taxonomy consistency",
        "",
        f"- Taxonomy-flag rows (union): **{payload['taxonomy'].get('taxonomy_mismatch_count', '—')}**",
        f"- Claim-facing taxonomy rows: **{payload['taxonomy'].get('paper_facing_taxonomy_mismatch_count', '—')}**",
        f"- Type mapping (cohort vs label-derived): **{payload['taxonomy'].get('type_mapping_mismatch_count', '—')}**",
        f"- Missing type in label string: **{payload['taxonomy'].get('type_missing_label_count', '—')}**",
        f"- Noncanonical label-derived type: **{payload['taxonomy'].get('type_noncanonical_count', '—')}**",
        f"- Label family vs predicted token: **{payload['taxonomy'].get('family_label_mismatch_count', '—')}**",
        f"- Family prediction errors (model vs cohort): **{payload['taxonomy'].get('prediction_error_count', '—')}**",
        "",
        "## Feature contract comparison",
        "",
        f"- Headline hash: `{payload.get('feature_contract_comparison', {}).get('headline_feature_column_hash') or '—'}`",
        f"- Ablation full_fused hash: `{payload.get('feature_contract_comparison', {}).get('ablation_full_fused_feature_column_hash') or '—'}`",
        f"- Split hash: `{payload.get('feature_contract_comparison', {}).get('split_hash') or '—'}`",
        f"- Apples-to-apples: **{'yes' if payload.get('feature_contract_comparison', {}).get('apples_to_apples') is True else 'no' if payload.get('feature_contract_comparison', {}).get('apples_to_apples') is False else 'unknown'}**",
        "",
        "## Claim readiness",
        "",
    ]
    for bucket in ("strong", "needs_caution", "next_steps"):
        items = (payload.get("claim_readiness") or {}).get(bucket) or []
        if items:
            md_lines.append(f"### {bucket.replace('_', ' ').title()}")
            md_lines.append("")
            for line in items:
                md_lines.append(f"- {line}")
            md_lines.append("")

    md_lines.extend(
        [
            "## Optional audits",
            "",
            f"- Family label taxonomy audit CSV present (pipeline-native): **{fam_avail}** (`family_label_taxonomy_audit.csv`)",
            f"- Support threshold preview present (pipeline-native): **{support_avail}**",
            f"- Family label taxonomy audit CSV present (post-run enrichment): **{fam_post_avail}**",
            f"- Support threshold preview present (post-run enrichment): **{support_post_avail}**",
            "",
        ]
    )

    out_json = rdiag / "research_validity_review.json"
    out_md = rdiag / "research_validity_review.md"
    out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    pr("")
    pr("RESEARCH VALIDITY REVIEW")
    pr("-------------------------")
    pr(f"Run: {run_id}")
    pr(f"Outputs: {out_md}")
    pr("")
    return out_json, out_md


def _build_claim_readiness(
    q1: dict[str, Any],
    q2: dict[str, Any],
    q3: dict[str, Any],
    taxonomy: dict[str, Any],
    scope: dict[str, Any],
    *,
    feature_contract: Mapping[str, Any] | None = None,
) -> dict[str, list[str]]:
    strong: list[str] = []
    caution: list[str] = []
    nxt: list[str] = []

    if q1:
        strong.append("Dataset foundation summary present — cohort gates and alignment described.")
    if q2:
        strong.append("Modality contribution summary present — permission vs fused signal summarized.")
        ps = q2.get("permission_signal_pct")
        if ps is not None:
            try:
                strong.append(
                    f"Permission features carry cohort-scale signal (permission_signal_pct ≈ {float(ps):.1f}%)."
                )
            except (TypeError, ValueError):
                strong.append("Permission features carry cohort-scale signal (see modality contribution).")
        strong.append(
            "AV detection / vendor-modality structure carries signal for ablation experiments "
            "(see modality contribution and ablation summary)."
        )

    gov_f = (scope.get("governed_cohort") or {}).get("families")
    train_f = (scope.get("trainable_family_classification_task") or {}).get("families_after_support_filter")
    if gov_f is not None and train_f is not None:
        try:
            if int(train_f) < int(gov_f):
                caution.append(
                    f"Headline scores apply to **{train_f}** supported families, not all **{gov_f}** governed labels."
                )
        except (TypeError, ValueError):
            pass

    fc = dict(feature_contract) if isinstance(feature_contract, dict) else {}
    la_txt = str(fc.get("label_target") or "").strip()
    if la_txt:
        strong.append(f"Label authority for headline training (from evaluation contract): {la_txt}.")
    tt = scope.get("trainable_family_classification_task") or {}
    if tt.get("families_after_support_filter") is not None:
        strong.append(
            f"The current all-malicious headline run retains **{tt.get('families_after_support_filter')}** "
            "supported families for multiclass training after the support filter (see headline_score_scope)."
        )

    if isinstance(q1, dict) and q1.get("supervised_family_claims_suitable") is False:
        caution.append("`supervised_family_claims_suitable=false` — use guarded language for family-level scientific claims.")

    conc = (q1.get("concentration") or {}).get("top5_share_pct") if isinstance(q1, dict) else None
    if conc is not None:
        try:
            if float(conc) > 50.0:
                caution.append(f"Top-family concentration remains high (top-5 share ≈ {float(conc):.1f}%).")
        except (TypeError, ValueError):
            pass

    tm = taxonomy.get("taxonomy_mismatch_count")
    paper_tm = taxonomy.get("paper_facing_taxonomy_mismatch_count")
    type_map_n = taxonomy.get("type_mismatch_count")
    if tm:
        try:
            if int(paper_tm if paper_tm is not None else tm) == 0 and int(tm) > 0:
                caution.append(
                    "Current taxonomy flags are diagnostic-only for this run; none are marked claim-facing under the active strict policy."
                )
            elif int(tm) > 0 and type_map_n is not None and int(type_map_n) > 0:
                caution.append(
                    "Most taxonomy flags are often **type_mapping_mismatch** (authority), not family prediction errors — "
                    "see taxonomy_type_authority_review."
                )
            elif int(tm) > 0:
                caution.append("Taxonomy consistency artifacts reported — review taxonomy_type_authority_review before type-level claims.")
        except (TypeError, ValueError):
            caution.append("Taxonomy consistency artifacts warrant review.")
    caution.append(
        "Type-level claims using generated `classification_label` strings are not publication-safe until cohort vs label-derived type is reconciled."
    )

    if fc.get("apples_to_apples") is False:
        caution.append(
            "Headline vs ablation `full_fused` metrics are not directly comparable — feature contracts differ "
            "(see headline_vs_ablation_contract_comparison)."
        )

    if not q3:
        nxt.append("Re-run modeling stage or export three-question summaries if model_and_family_failure_summary is missing.")

    nxt.extend(
        [
            "Run `scripts/family_label_taxonomy_audit.py` when extending family coverage claims.",
            "Review `support_threshold_preview.*` when debating minimum family support.",
        ]
    )
    return {"strong": strong, "needs_caution": caution, "next_steps": nxt}


def collect_run_comparison_row(output_root: Path, run_id: str) -> dict[str, Any]:
    """One row of run-to-run comparison using run_summary + diagnostics JSON."""
    run_root = Path(output_root) / "runs" / run_id
    rdiag = run_scoped_diagnostics(output_root, run_id)
    gdiag = global_diagnostics(output_root)
    summary = read_json_dict(run_root / "run_summary.json")
    manifest = read_json_dict(run_root / "run_manifest.json")

    profile = str(
        summary.get("profile_id") or (manifest.get("profile_params") or {}).get("profile_id") or ""
    )

    ev_on = coalesce_manifest_publication_mode(manifest)
    cohort_methodology = _collect_cohort_methodology(output_root, run_id)
    cohort_lock_status = resolve_cohort_lock_status(manifest)
    publication_ready_status = coalesce_publication_ready_status(manifest)

    min_support = getattr(app_config, "MIN_FAMILY_SUPPORT", "")
    mp = manifest.get("profile_params") if isinstance(manifest.get("profile_params"), dict) else {}
    if isinstance(mp, dict):
        min_support = mp.get("min_family_support", min_support)

    q1 = read_json_dict(rdiag / "dataset_foundation_summary.json") or read_json_dict(
        gdiag / "dataset_foundation_summary.json"
    )
    scope = read_json_dict(rdiag / "headline_score_scope.json") or read_json_dict(
        gdiag / "headline_score_scope.json"
    )
    q3 = read_json_dict(rdiag / "model_and_family_failure_summary.json") or read_json_dict(
        gdiag / "model_and_family_failure_summary.json"
    )
    modality = read_json_dict(rdiag / "modality_contribution_summary.json") or read_json_dict(
        gdiag / "modality_contribution_summary.json"
    )
    taxonomy = read_json_dict(oh.resolve_taxonomy_consistency_summary_path(rdiag, run_id))

    macros = _ablation_macro_f1_by_experiment(rdiag, run_id)
    if all(v is None for v in macros.values()):
        macros = _ablation_macro_f1_by_experiment(gdiag, run_id)

    headline_task = scope.get("trainable_family_classification_task") or {}

    smote_on = summary.get("smote_enabled")
    if smote_on is None:
        smote_on = manifest.get("smote_enabled")

    gov_n = q1.get("governed_samples")
    train_n = headline_task.get("samples_after_support_filter") or q1.get("trainable_after_support_filter")
    fam_cov = None
    try:
        if gov_n and train_n:
            fam_cov = round(100.0 * float(train_n) / float(gov_n), 2)
    except (TypeError, ValueError, ZeroDivisionError):
        fam_cov = None

    return {
        "run_id": run_id,
        "profile": profile,
        "governed_samples": gov_n,
        "trainable_samples": train_n,
        "governed_families": q1.get("families_represented"),
        "trainable_families": headline_task.get("families_after_support_filter"),
        "sample_coverage_pct": fam_cov,
        "permission_signal_pct": modality.get("permission_signal_pct"),
        "vendor_merge_pct": modality.get("vendor_merge_pct"),
        "headline_model": q3.get("headline_model"),
        "headline_macro_f1": q3.get("macro_f1"),
        "permissions_raw_macro_f1": macros.get("permissions_raw"),
        "full_fused_macro_f1": macros.get("full_fused"),
        "taxonomy_mismatch_count": taxonomy.get("taxonomy_mismatch_count"),
        "support_threshold": min_support,
        "smote_enabled": smote_on,
        "evidence_mode": ev_on,
        "publication_ready_status": publication_ready_status or "unknown",
        "cohort_lock_status": cohort_lock_status,
        "cohort_membership_mode": cohort_methodology.get("cohort_membership_mode", "standard_contract_filters"),
        "min_malicious_detections_threshold": cohort_methodology.get("min_malicious_detections_threshold", 0),
        "rescued_unknown_consensus": cohort_methodology.get("rescued_unknown_consensus", 0),
        "cohort_methodology_summary": cohort_methodology_summary(
            {
                "cohort_lock_status": cohort_lock_status,
                "cohort_membership_mode": cohort_methodology.get("cohort_membership_mode", "standard_contract_filters"),
                "min_malicious_detections_threshold": cohort_methodology.get("min_malicious_detections_threshold", 0),
                "min_malicious_detections_rescued_unknown_consensus": cohort_methodology.get("rescued_unknown_consensus", 0),
            }
        ),
    }


def write_run_comparison_summary(
    *,
    output_root: Path,
    run_ids: list[str],
    print_fn: Callable[[str], None] | None = None,
) -> tuple[Path, Path]:
    """Write CSV + Markdown comparison table for selected runs."""
    pr = print_fn or (lambda _s: None)
    rows = [collect_run_comparison_row(output_root, rid) for rid in run_ids]
    df = pd.DataFrame(rows)
    gdiag = global_diagnostics(output_root)
    gdiag.mkdir(parents=True, exist_ok=True)
    csv_path = gdiag / "run_comparison_summary.csv"
    md_path = gdiag / "run_comparison_summary.md"
    df.to_csv(csv_path, index=False)
    md_lines = ["# Run comparison summary", "", _df_to_markdown_table(df)]
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    pr("")
    pr("COMPARE RUNS / EXPERIMENT SERIES")
    pr("----------------------------------")
    pr(f"Wrote: {csv_path}")
    pr("")
    return csv_path, md_path


def write_evidence_paper_readiness(
    *,
    output_root: Path,
    latest_run_id: str | None,
    locked_run_id: str | None,
    latest_evidence_mode: bool,
    latest_paper_exports: bool,
    print_fn: Callable[[str], None] | None = None,
) -> tuple[Path, Path]:
    """Summarize evidence/publication gates for operator review."""
    pr = print_fn or (lambda _s: None)
    gdiag = global_diagnostics(output_root)
    gdiag.mkdir(parents=True, exist_ok=True)

    publication_ready_status = coalesce_publication_ready_status(
        {
            "publication_ready_status": (
                "ready" if bool(latest_evidence_mode and latest_paper_exports and locked_run_id) else "not_ready"
            )
        }
    )
    cohort_lock_status = "locked" if bool(locked_run_id) else "unlocked"
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "latest_run_id": latest_run_id or "",
        "locked_evidence_run_id": locked_run_id or "",
        "latest_run_evidence_mode": latest_evidence_mode,
        "latest_publication_exports": latest_paper_exports,
        "evidence_readiness": {
            "latest_run_evidence_mode": bool(latest_evidence_mode),
            "latest_publication_exports": bool(latest_paper_exports),
        },
        "publication_ready_status": publication_ready_status,
        "cohort_lock_status": cohort_lock_status,
        "available": [
            "Development health checks",
            "Research validity review",
            "Run comparison (non-evidence)",
        ],
        "unavailable_without_evidence": [
            "Evidence bundle checker (strict paths)",
            "Strict reproducibility evidence_bundle aggregation",
            "Publication export compliance bundles",
        ],
        "to_enable": [
            "Run pipeline with evidence mode enabled in profile.",
            "Lock evidence run pointer when preparing publication freeze.",
        ],
    }
    payload["evidence_paper_readiness"] = dict(payload)
    json_path = gdiag / "evidence_paper_readiness.json"
    md_path = gdiag / "evidence_paper_readiness.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Evidence readiness",
        "",
        f"- Latest run: `{payload['latest_run_id'] or '—'}`",
        f"- Evidence mode (latest): **{latest_evidence_mode}**",
        f"- Publication exports (latest): **{latest_paper_exports}**",
        f"- Locked evidence run: **{payload['locked_evidence_run_id'] or 'none'}**",
        "",
        "## Available now",
        "",
    ]
    for a in payload["available"]:
        lines.append(f"- {a}")
    lines.extend(["", "## Unavailable until evidence mode / lock", ""])
    for u in payload["unavailable_without_evidence"]:
        lines.append(f"- {u}")
    lines.extend(["", "## Interpretation", "", "_Current workspace is suited to analysis and tuning, not final publication evidence unless the gates above are satisfied._", ""])
    md_path.write_text("\n".join(lines), encoding="utf-8")

    pr("")
    pr("EVIDENCE READINESS")
    pr("---------------------------")
    pr(f"Wrote: {md_path}")
    pr("")
    return json_path, md_path


__all__ = [
    "build_filesystem_artifact_checks",
    "collect_run_comparison_row",
    "global_diagnostics",
    "list_run_ids_newest_first",
    "pick_first_existing",
    "run_scoped_diagnostics",
    "write_evidence_paper_readiness",
    "write_research_validity_review",
    "write_run_comparison_summary",
    "write_run_health_artifact_reports",
]
