"""Curated terminal narrative and diagnostics index for research/operator workflows.

Heavy diagnostic detail belongs in diagnostics artifacts; the terminal focuses on
cohort semantics, modality coverage, model leaderboard context, and claim hygiene.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd

from config import app_config
from obsidiandroid.common.json_io import read_json_dict
from obsidiandroid.common import output_hygiene as oh

# Internal experiment keys → human-readable modality descriptions (CSV keeps internal keys).
ABLATION_FEATURE_SET_LABELS: dict[str, str] = {
    "vendor_full": "vendor_parsed_full",
    "vendor_no_parsed_family": "vendor_parsed_no_family",
    "vendor_no_family_no_type": "vendor_parsed_no_family_no_type",
    "vendor_detection_binary_only": "vendor_detection_binary_only",
    "vendor_consensus_scores_only": "vendor_consensus_scores_only",
    "permissions_raw": "permissions_raw",
    "permissions_grouped": "permissions_grouped",
    "permissions_grouped_plus_vendor_no_family": "permissions_grouped_plus_vendor_safe",
    "full_fused": "full_fused",
}


def format_feature_set_label(internal_key: str) -> str:
    return ABLATION_FEATURE_SET_LABELS.get(str(internal_key), str(internal_key))


def clear_operator_state() -> None:
    """Reset per-run operator narrative buffers (call at pipeline start)."""
    setattr(app_config, "RUNTIME_OPERATOR_ISSUES", [])
    setattr(app_config, "RUNTIME_OPERATOR_ARTIFACT_COUNTS", {})
    setattr(app_config, "RUNTIME_SMOTE_WARNING_LAST", "")
    setattr(app_config, "RUNTIME_SMOTE_WARNING_EMITTED", False)
    setattr(app_config, "RUNTIME_SMOTE_AUDIT_LAST", None)
    setattr(app_config, "RUNTIME_SMOTE_AUDIT_BY_MODEL", {})


def record_operator_issue(
    *,
    tag: str,
    title: str,
    lines: Sequence[str],
) -> None:
    """Queue a structured issue for the end-of-run ISSUES FOUND block."""
    bucket = getattr(app_config, "RUNTIME_OPERATOR_ISSUES", None)
    if not isinstance(bucket, list):
        bucket = []
    entry = {"tag": str(tag), "title": str(title), "lines": [str(x) for x in lines]}
    bucket.append(entry)
    setattr(app_config, "RUNTIME_OPERATOR_ISSUES", bucket)


def bump_artifact_counter(group: str, n: int = 1) -> None:
    counts = getattr(app_config, "RUNTIME_OPERATOR_ARTIFACT_COUNTS", None)
    if not isinstance(counts, dict):
        counts = {}
    counts[str(group)] = int(counts.get(str(group), 0)) + int(n)
    setattr(app_config, "RUNTIME_OPERATOR_ARTIFACT_COUNTS", counts)


def _queue_runtime_operator_issues(
    *,
    diagnostics_dir: Path,
    manifest_context: Mapping[str, Any],
) -> None:
    """Promote major runtime caveats into the end-of-run operator issue queue."""

    contract = (
        manifest_context.get("paper_cohort_contract")
        if isinstance(manifest_context.get("paper_cohort_contract"), dict)
        else {}
    )
    validation = contract.get("validation") if isinstance(contract.get("validation"), dict) else {}
    runtime_drift = contract.get("sample_id_lock", {}).get("runtime_db_drift") if isinstance(contract.get("sample_id_lock"), dict) else {}
    if str(validation.get("status", "")).strip().lower() == "degraded_live_db_drift":
        matched = int(runtime_drift.get("matched_sample_count", 0) or 0)
        missing = int(runtime_drift.get("missing_from_db_count", 0) or 0)
        expected = int(runtime_drift.get("lock_sample_count", 0) or 0)
        record_operator_issue(
            tag="COHORT_LOCK",
            title="Locked cohort drift downgraded to count-only semantics",
            lines=[
                f"Preserved lock expected {expected} sample_ids; {matched} matched the live DB and {missing} are now absent.",
                "Publication-ready status passed, but exact historical sample membership is no longer fully recoverable.",
            ],
        )

    smote_warning = str(getattr(app_config, "RUNTIME_SMOTE_WARNING_LAST", "") or "").strip()
    if smote_warning:
        record_operator_issue(
            tag="REPRO",
            title="SMOTE remained enabled in evidence/publication mode",
            lines=[
                smote_warning,
                "Review `smote_effect_check.md` and consider `OBSIDIAN_DISABLE_SMOTE_IN_EVIDENCE_MODE=1` for stricter reproducibility.",
            ],
        )

    profile_id = str(getattr(app_config, "RUNTIME_PROFILE_ID", "") or "").strip()
    split_algorithm = str(getattr(app_config, "RUNTIME_LAST_SPLIT_ALGORITHM", "") or "").strip()
    if profile_id.startswith("malicious_temporal_") and split_algorithm:
        split_algo_norm = split_algorithm.lower()
        if "temporal" not in split_algo_norm and "year_holdout" not in split_algo_norm:
            record_operator_issue(
                tag="TEMPORAL",
                title="Temporal profile used a non-temporal holdout policy",
                lines=[
                    f"Profile `{profile_id}` executed with split algorithm `{split_algorithm}`.",
                    "Interpret results as random/group holdout evidence, not forward-in-time generalization.",
                ],
            )

    run_id = str(manifest_context.get("run_id", "") or "").strip()
    taxonomy = read_json_dict(oh.resolve_taxonomy_consistency_summary_path(diagnostics_dir, run_id))
    if taxonomy:
        total = int(taxonomy.get("taxonomy_mismatch_count", 0) or 0)
        paper_facing = int(taxonomy.get("paper_facing_taxonomy_mismatch_count", total) or 0)
        if total > 0:
            counts = taxonomy.get("mismatch_reason_counts")
            top_bits: list[str] = []
            if isinstance(counts, list):
                for row in counts[:3]:
                    if not isinstance(row, dict):
                        continue
                    reason = str(row.get("mismatch_reason", "") or "").strip()
                    count = int(row.get("count", 0) or 0)
                    if reason and count > 0:
                        top_bits.append(f"{reason}={count}")
            detail = ", ".join(top_bits) if top_bits else "see taxonomy_consistency_mismatches CSV"
            record_operator_issue(
                tag="TAXONOMY",
                title="Taxonomy mismatch backlog present",
                lines=[
                    f"Taxonomy mismatches: total={total}; claim-facing={paper_facing}.",
                    f"Top mismatch buckets: {detail}.",
                ],
            )


def _safe_pct(num: float, den: float) -> str:
    if den <= 0:
        return "n/a"
    return f"{100.0 * float(num) / float(den):.1f}%"


def resolve_feature_column_survival_path(*, diagnostics_dir: Path, run_id: str) -> Path:
    """Resolve feature-column survival CSV after run-local `.latest` suppression cleanup."""
    return oh.resolve_feature_column_survival_path(diagnostics_dir, run_id)


def _perm_top_from_survival(surv_path: Path, *, prefix: str, top_n: int = 8) -> list[tuple[str, int]]:
    if not surv_path.is_file():
        return []
    try:
        df = pd.read_csv(surv_path)
    except Exception:
        return []
    if "feature_name" not in df.columns or "nonzero_count_final_training" not in df.columns:
        return []
    sub = df[df["feature_name"].astype(str).str.startswith(prefix)].copy()
    if sub.empty:
        return []
    sub["nz"] = pd.to_numeric(sub["nonzero_count_final_training"], errors="coerce").fillna(0).astype(int)
    sub = sub.sort_values("nz", ascending=False).head(top_n)
    return [(str(r["feature_name"]), int(r["nz"])) for _, r in sub.iterrows()]


def _rf_perm_importance_top(model_results: dict[str, Any], *, top_n: int = 8) -> list[tuple[str, float]]:
    rf = model_results.get("random_forest") if isinstance(model_results, dict) else None
    if not isinstance(rf, dict):
        return []
    named = rf.get("metadata", {}).get("feature_importances_named")
    if not isinstance(named, list):
        return []
    rows: list[tuple[str, float]] = []
    for item in named:
        if not isinstance(item, dict):
            continue
        name = str(item.get("feature_name") or "")
        imp = item.get("importance")
        if imp is None:
            continue
        try:
            imp_f = float(imp)
        except (TypeError, ValueError):
            continue
        if name.startswith(("perm__", "perm_grp__")):
            rows.append((name, imp_f))
    rows.sort(key=lambda x: -x[1])
    return rows[:top_n]


def _classification_report_family_insights(model_results: dict[str, Any], model_key: str) -> dict[str, Any]:
    res = model_results.get(model_key) if isinstance(model_results, dict) else None
    if not isinstance(res, dict):
        return {}
    creport = res.get("metadata", {}).get("classification_report")
    if not isinstance(creport, dict):
        return {}
    per_class: list[tuple[str, float, float, float, int]] = []
    for label, stats in creport.items():
        if not isinstance(stats, dict):
            continue
        if label in {"accuracy", "macro avg", "weighted avg"}:
            continue
        try:
            p = float(stats.get("precision", 0))
            r = float(stats.get("recall", 0))
            f1 = float(stats.get("f1-score", 0))
            sup = int(float(stats.get("support", 0)))
        except (TypeError, ValueError):
            continue
        per_class.append((str(label), p, r, f1, sup))
    if not per_class:
        return {}
    lowest_recall = sorted(per_class, key=lambda x: x[2])[:5]
    lowest_prec = sorted(per_class, key=lambda x: x[1])[:5]
    macro_gap_candidates = sorted(per_class, key=lambda x: (x[3] - x[2]))[:5]
    return {
        "lowest_recall": lowest_recall,
        "lowest_precision": lowest_prec,
        "largest_macro_vs_f1_gap": macro_gap_candidates,
    }


def top_confusion_pairs_for_model(
    model_results: dict[str, Any],
    model_key: str,
    *,
    top_n: int = 5,
) -> list[tuple[str, str, int]]:
    """Public wrapper for holdout confusion off-diagonal pairs (true, pred, count)."""
    return _top_confusion_pairs(model_results, model_key, top_n=top_n)


def _top_confusion_pairs(
    model_results: dict[str, Any],
    model_key: str,
    *,
    top_n: int = 5,
) -> list[tuple[str, str, int]]:
    """Largest off-diagonal confusion counts from the holdout confusion matrix (cheap science cue)."""
    res = model_results.get(model_key) if isinstance(model_results, dict) else None
    if not isinstance(res, dict):
        return []
    ev = res.get("evaluation", {})
    if not isinstance(ev, dict):
        return []
    cm = ev.get("confusion_matrix")
    labels = ev.get("class_labels") or ev.get("decoded_labels")
    if cm is None or not labels:
        return []
    arr = np.asarray(cm)
    if arr.ndim != 2 or arr.shape[0] != arr.shape[1]:
        return []
    lab_list = [str(x) for x in labels]
    n = arr.shape[0]
    triples: list[tuple[int, int, int]] = []
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            triples.append((i, j, int(arr[i, j])))
    triples.sort(key=lambda t: -t[2])
    out: list[tuple[str, str, int]] = []
    for i, j, c in triples[: max(1, int(top_n))]:
        li = lab_list[i] if i < len(lab_list) else str(i)
        lj = lab_list[j] if j < len(lab_list) else str(j)
        out.append((li, lj, c))
    return out


def _read_model_comparison_leaderboard(path: Path) -> tuple[list[dict[str, Any]], str]:
    """Return sorted rows by Macro F1 descending and best internal model key."""
    if not path.is_file():
        return [], ""
    try:
        df = pd.read_csv(path)
    except Exception:
        return [], ""
    if df.empty or "Macro F1-Score" not in df.columns:
        cols = [c for c in df.columns if str(c).lower().replace("-", "").replace("_", "") == "macrof1score"]
        metric_col = cols[0] if cols else None
    else:
        metric_col = "Macro F1-Score"
    if metric_col is None or "Model" not in df.columns:
        return [], ""
    work = df.copy()
    work["_m"] = pd.to_numeric(work[metric_col], errors="coerce")
    work = work.dropna(subset=["_m"]).sort_values("_m", ascending=False)
    rows_out = []
    for _, row in work.iterrows():
        rows_out.append(dict(row.drop(labels=["_m"])))
    best = ""
    try:
        best = str(work.iloc[0]["Model"]).strip().lower().replace(" ", "_")
    except Exception:
        best = ""
    return rows_out, best


def write_diagnostics_index_md(
    diagnostics_dir: Path,
    *,
    run_id: str,
    artifact_list: Sequence[str],
) -> Path | None:
    """Emit ``diagnostics/index.md`` with standard sections + artifact map excerpt."""
    if not diagnostics_dir.exists():
        return None
    rel = diagnostics_dir.resolve()
    lines: list[str] = []
    lines.append(f"# Diagnostics index — `{run_id}`")
    lines.append("")
    lines.append(f"Root: `{rel}`")
    lines.append("")
    lines.append("## Run overview")
    lines.append("")
    lines.append("| Artifact | Purpose |")
    lines.append("| --- | --- |")
    staples = [
        ("dataset_foundation_summary", "Q1 dataset validity (cohort, concentration, gates)."),
        ("modality_contribution_summary", "Q2 modality coverage + ablation pointers."),
        ("model_and_family_failure_summary", "Q3 headline metrics, confusion, type vs family."),
        ("run_health_summary_", "High-level cohort/model health snapshot (JSON)."),
        ("model_comparison_summary_", "Model leaderboard CSV for this run."),
        ("experiment_registry_", "Experiment registry wiring + profile context."),
        ("cohort_foundation", "Structured cohort demographics + funnel narrative."),
        ("feature_contract", "Frozen training feature-column contract."),
        ("leakage_assessment.txt", "Leakage posture / modality coupling summary."),
        ("modality_method_contract.json", "Per-modality method + fusion accounting."),
        ("feature_column_survival", "Feature survival through pruning gates."),
        ("ablation_summary_", "Methodology grid (when enabled)."),
        ("pipeline_stage_summary.csv", "Stage timings + throughput."),
        ("split_freeze_headline_", "Headline train/test membership ledger."),
    ]
    for prefix, purpose in staples:
        lines.append(f"| `{prefix}*` | {purpose} |")
    lines.append("")
    sections = [
        ("Cohort and label distribution", ["cohort_foundation", "analysis_snapshot", "family_distribution"]),
        ("Dataset concentration", ["cohort_foundation", "family_distribution_report"]),
        ("Modality coverage", ["feature_modality_coverage", "feature_build_coverage", "permission_fuse_audit"]),
        ("Feature contracts", ["feature_contract", "feature_column_survival"]),
        ("Leakage assessment", ["leakage_assessment", "leakage_pruning_audit"]),
        ("Model comparison", ["model_comparison_summary", "model_config_snapshot"]),
        ("Ablation summary", ["ablation_summary", "ablation_per_family", "ablation_feature_schema_audit"]),
        ("Contract / taxonomy authority", ["headline_vs_ablation_contract_comparison", "taxonomy_type_authority_review"]),
        ("Permission diagnostics", ["permission_training_survival", "permission_fuse_audit"]),
        ("Vendor/parser diagnostics", ["parser_quality", "vendor_parser"]),
        ("Sample lineage", ["sample_stage_lineage", "feature_matrix_lineage_gate"]),
        ("Predictions / errors", ["headline_test_predictions", "headline_test_errors"]),
        ("Taxonomy", ["taxonomy_consistency", "taxonomy_authority"]),
    ]
    listing = sorted(p.name for p in diagnostics_dir.iterdir() if p.is_file())
    for sec_title, keys in sections:
        lines.append(f"## {sec_title}")
        lines.append("")
        hits: list[str] = []
        for n in listing:
            if not any(k.lower() in n.lower() for k in keys):
                continue
            if str(run_id) in n or "latest." in n:
                hits.append(n)
        uniq = sorted(set(hits))[:42]
        for name in uniq:
            lines.append(f"- `{name}`")
        if not uniq:
            lines.append("(no matching files)")
        lines.append("")
    lines.append("## Artifact map (this run enumeration)")
    lines.append("")
    art = [str(Path(p).name) for p in artifact_list if str(run_id) in str(p) or "/diagnostics/" in str(p)]
    for chunk in sorted(set(art))[:120]:
        lines.append(f"- `{chunk}`")
    if len(set(art)) > 120:
        lines.append(f"- … `{len(set(art)) - 120}` additional paths omitted")
    lines.append("")
    out_path = diagnostics_dir / "index.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def emit_research_operator_report(
    *,
    diagnostics_dir: Path,
    run_id: str,
    profile_id: str,
    manifest_context: Mapping[str, Any],
    samples_df: pd.DataFrame | None,
    model_results: dict[str, Any] | None,
    top_model: str | None,
    artifact_list: list[str],
    print_fn: Callable[[str], None] | None = None,
) -> None:
    """End-of-run operator dashboard: markdown index + TERMINAL blocks."""
    from obsidiandroid.cli.ui import display as du
    from obsidiandroid.diagnostics.contract_and_taxonomy_reports import (
        write_headline_vs_ablation_contract_reports,
        write_taxonomy_authority_split_reports,
        write_taxonomy_type_authority_reports,
    )
    from obsidiandroid.reporting import research_three_questions as research_rq

    pr = print_fn or (lambda s: du.print_info(s))

    try:
        _cm, _cc, parity = write_headline_vs_ablation_contract_reports(
            diagnostics_dir=diagnostics_dir,
            run_id=run_id,
            manifest_context=dict(manifest_context),
            runtime_headline_hash=str(
                getattr(app_config, "RUNTIME_HEADLINE_FEATURE_COLUMN_HASH", "") or ""
            ).strip()
            or None,
        )
        for p in (_cm, _cc):
            if p is not None and str(p) not in artifact_list:
                artifact_list.append(str(p))
        _tm, _tc = write_taxonomy_type_authority_reports(diagnostics_dir, run_id)
        _tsm, _tsj, _tsr, _tsp, _tsg = write_taxonomy_authority_split_reports(diagnostics_dir, run_id)
        for p in (_tm, _tc, _tsm, _tsj, _tsr, _tsp, _tsg):
            if p is not None and str(p) not in artifact_list:
                artifact_list.append(str(p))
    except Exception:
        parity = {}

    bundle = research_rq.write_research_question_artifacts(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id=profile_id,
        manifest_context=dict(manifest_context),
        samples_df=samples_df,
        model_results=model_results or {},
        top_model=top_model,
    )
    _queue_runtime_operator_issues(
        diagnostics_dir=diagnostics_dir,
        manifest_context={
            **dict(manifest_context),
            "run_id": run_id,
        },
    )
    extra_paths = bundle.get("_written_paths") or []
    combined_artifacts = list(artifact_list) + [p for p in extra_paths if p not in set(artifact_list)]

    md_path = write_diagnostics_index_md(
        diagnostics_dir, run_id=run_id, artifact_list=combined_artifacts
    )
    pr("")
    pr(f"Run ID: {run_id}  |  Profile: {profile_id}")
    pr("")
    research_rq.print_research_questions_terminal(bundle, pr=pr, du=du)

    if parity:
        du.print_section("FEATURE CONTRACT COMPARISON (headline vs ablation full_fused)")
        pr(f"  headline_feature_column_hash    : {parity.get('headline_feature_column_hash') or '—'}")
        pr(f"  ablation_full_fused_feature_hash: {parity.get('ablation_full_fused_feature_column_hash') or '—'}")
        pr(f"  split_hash                       : {parity.get('split_hash') or '—'}")
        pr(f"  label_target                     : {parity.get('label_target') or '—'}")
        am = parity.get("apples_to_apples")
        pr(f"  apples_to_apples                 : {'yes' if am is True else 'no' if am is False else 'unknown'}")
        if am is False:
            pr(f"  → {parity.get('incommensurable_message', '')}")
        pr(
            f"  Files: `{diagnostics_dir / f'headline_vs_ablation_contract_comparison_{run_id}.md'}`"
        )
        pr("")

    du.print_section("TAXONOMY AUTHORITY (type ground truth)")
    pr("  Cohort type_slug is authoritative for type-level reporting; label-derived type is a parser artifact.")
    pr(
        f"  Review: `{diagnostics_dir / f'taxonomy_type_authority_review_{run_id}.md'}` "
        f"and `taxonomy_type_authority_review_{run_id}.csv`"
    )
    pr(
        f"  Taxonomy authority split: `{diagnostics_dir / f'taxonomy_authority_split_{run_id}.md'}`"
    )
    pr("")

    surv = resolve_feature_column_survival_path(diagnostics_dir=diagnostics_dir, run_id=run_id)
    raw_pop = _perm_top_from_survival(surv, prefix="perm__android_", top_n=5)
    rf_perm = _rf_perm_importance_top(model_results or {}, top_n=5)
    if raw_pop or rf_perm:
        du.print_subheader("Permission feature survival / RF hints (see diagnostics for full detail)")
        if raw_pop:
            pr("  Top permission columns by training nonzero: " + ", ".join(f"{n}({z})" for n, z in raw_pop))
        if rf_perm:
            pr(
                "  RF top permission-ish importances: "
                + ", ".join(f"{n}={score:.4f}" for n, score in rf_perm)
            )
        pr("")

    du.print_section("ISSUES FOUND")
    issues = getattr(app_config, "RUNTIME_OPERATOR_ISSUES", []) or []
    if not isinstance(issues, list) or not issues:
        pr("(No structured governance issues queued — tail risks may still exist; see diagnostics.)")
    else:
        dedup_seen: set[str] = set()
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            key = issue.get("title", "") + "|" + "".join(str(x) for x in issue.get("lines") or ())
            if key in dedup_seen:
                continue
            dedup_seen.add(key)
            tag = issue.get("tag", "NOTE")
            pr(f"[{tag}] {issue.get('title', '')}")
            for ln in issue.get("lines") or []:
                pr(f"    {ln}")
            pr("")
    du.print_section("CLAIM READINESS")

    active_cls = ""
    mc_la = manifest_context.get("label_authority") if isinstance(manifest_context, dict) else None
    if isinstance(mc_la, dict) and mc_la.get("active_training_classes") is not None:
        active_cls = str(mc_la.get("active_training_classes"))

    lines_strong = [
        (
            f"A broad all_malicious-style run can retain **{active_cls or '—'}** active family classes "
            "for headline multiclass training when support filtering is configured accordingly."
        ),
        "Permission features and AV detection-structure modalities carry measurable signal (see modality contribution + ablation).",
    ]
    caution = [
        "`supervised_family_claims_suitable=false` in dataset foundation means guarded language for family-level scientific claims.",
        "Top-family concentration remains high — Macro-F1 and recall tails must lead interpretation.",
        "Type-level claims using generated `classification_label` strings are not publication-safe until cohort vs label-derived type authority is reconciled (see taxonomy_type_authority_review).",
        "Use `taxonomy_authority_split` to distinguish authority gaps, generic/coarse tokens, unknown-type families, rendering mismatches, and real model prediction errors.",
        "Headline leaderboard metrics vs ablation `full_fused` are not comparable unless feature hashes match (see FEATURE CONTRACT COMPARISON).",
        "Parsed vendor metadata is often sparse — do not describe it as cohort-wide dense labels.",
        "Vendor-derived parsed family/type features may couple to labels — separate detection binaries, consensus scores, and parsed strings.",
    ]
    nxt = [
        "Dominance-cap stability and temporal permission drift.",
        "Permission-only vs fused delta stability (feature_set_ablation_summary).",
        "Family-level failure explanations (top_confusion_pairs, lowest recall).",
    ]
    pr("Strong")
    for item in lines_strong:
        pr(f"  + {item}")
    pr("")
    pr("Needs caution")
    for item in caution:
        pr(f"  ! {item}")
    pr("")
    pr("Needs next analysis")
    for item in nxt:
        pr(f"  → {item}")
    du.print_section("ARTIFACT POINTER")
    pr(f"Diagnostics index : {md_path}")
    rr = getattr(app_config, "RUNTIME_RUN_ROOT", "") or ""
    pr(f"Run root            : {rr}")
    pr("Start here:")
    pr(f"  • `{diagnostics_dir / 'dataset_foundation_summary.md'}`")
    pr(f"  • `{diagnostics_dir / 'modality_contribution_summary.md'}`")
    pr(f"  • `{diagnostics_dir / 'model_and_family_failure_summary.md'}`")
    pr(f"  • `{diagnostics_dir / f'taxonomy_authority_split_{run_id}.md'}`")
    pr(f"  • `{diagnostics_dir / f'taxonomy_type_authority_review_{run_id}.md'}`")
    pr("Skeptic audits:")
    pr(f"  • `{diagnostics_dir / 'headline_score_scope.md'}`")
    pr(f"  • `{diagnostics_dir / 'split_contamination_audit.md'}`")
    pr(f"  • `{diagnostics_dir / 'smote_effect_check.md'}`")
    pr(f"  • `{diagnostics_dir / 'recommended_validation_plan.md'}`")
