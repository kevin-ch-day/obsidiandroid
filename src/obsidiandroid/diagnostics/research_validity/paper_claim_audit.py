"""Generated publication claim audit for paper alignment (strict row format)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.governance.evidence_mode_resolver import coalesce_manifest_publication_mode


def _primary_claim_surface(
    *,
    profile_id: str,
    publication_ready_mode: bool,
    support_floor_mode: str,
    benchmark_support_floor: Any,
) -> str:
    """Resolve the primary claim surface for the claim-audit artifact."""
    profile = str(profile_id or "").strip()
    if publication_ready_mode:
        return "locked_publication_surface"
    if profile == "android_malware_all_current":
        return "broad_current_corpus"
    if profile == "android_malware_expanded_families":
        return "expanded_family_exploratory"
    if profile == "android_malware_type_taxonomy":
        return "type_taxonomy_surface"
    if profile == "android_malware_major_families":
        return "major_family_benchmark"
    if support_floor_mode == "benchmark_eligibility" or benchmark_support_floor not in (None, "", 0):
        return "major_family_benchmark"
    return "broad_current_corpus"


def _claim_audit_filename(primary_surface: str) -> str:
    """Return the single run-scoped claim-audit name for a claim surface."""
    return {
        "locked_publication_surface": "publication_claim_audit.md",
        "major_family_benchmark": "benchmark_claim_audit.md",
        "type_taxonomy_surface": "benchmark_claim_audit.md",
        "broad_current_corpus": "research_claim_audit.md",
        "expanded_family_exploratory": "research_claim_audit.md",
    }.get(primary_surface, "research_claim_audit.md")


def _read_csv_exists(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    import pandas as pd

    return pd.read_csv(path).to_dict(orient="records")


def _ablation_status(diagnostics_dir: Path, run_id: str) -> tuple[str, str]:
    """Return a fail-closed status for ablation evidence in this run."""
    status_path = diagnostics_dir / "feature_set_ablation_summary.csv"
    for row in _read_csv_exists(status_path):
        if str(row.get("run_id", run_id)).strip() == str(run_id) and str(
            row.get("status", "")
        ).strip() in {"ablation_summary_unavailable_or_empty", "unavailable"}:
            return "unavailable", "ablation_disabled"
    scoped = diagnostics_dir / f"ablation_summary_{run_id}.csv"
    if not scoped.is_file():
        return "unavailable", "missing_run_scoped_ablation_artifact"
    return "available", ""


def _ablation_rows(diagnostics_dir: Path, run_id: str) -> list[dict[str, Any]]:
    # A diagnostic run writes this sentinel when ablations are disabled.  Do not
    # silently substitute an older global ``latest`` file, which would attach
    # another run's rows to the present claim audit.
    status, _reason = _ablation_status(diagnostics_dir, run_id)
    if status != "available":
        return []
    # Claim-generating reports must never consume a global/latest fallback.
    # A filename is insufficient provenance, so rows also require this run ID.
    rows = _read_csv_exists(diagnostics_dir / f"ablation_summary_{run_id}.csv")
    explicit_run_ids = {str(row.get("run_id", "")).strip() for row in rows}
    explicit_run_ids.discard("")
    if explicit_run_ids != {str(run_id)}:
        return []
    return rows


def _max_f1_by_experiment(
    rows: list[dict[str, Any]],
    *,
    label_targets: tuple[str, ...] = ("family_id", "family_canonical_default"),
) -> dict[str, float]:
    preferred_targets = tuple(str(target).strip() for target in label_targets if str(target).strip())
    if not preferred_targets:
        preferred_targets = ("family_id", "family_canonical_default")
    observed_targets = {str(row.get("label_target", "")).strip() for row in rows}
    active_target = next((target for target in preferred_targets if target in observed_targets), preferred_targets[0])
    per_exp: dict[str, list[float]] = {}
    for row in rows:
        if str(row.get("label_target", "")) != active_target:
            continue
        exp = str(row.get("experiment", ""))
        f1 = row.get("macro_f1_score")
        if not exp or f1 is None:
            continue
        per_exp.setdefault(exp, []).append(float(f1))
    return {k: max(v) for k, v in per_exp.items() if v}


def _model_top_macro_f1(diagnostics_dir: Path, run_id: str) -> tuple[str, float | None]:
    path = oh.resolve_model_comparison_summary_path(diagnostics_dir, run_id)
    if path.exists():
        import pandas as pd

        try:
            mcdf = pd.read_csv(path)
            if not mcdf.empty and "Model" in mcdf.columns:
                col = next(
                    (
                        candidate
                        for candidate in ("Macro-F1 Score", "Macro F1-Score", "MacroF1")
                        if candidate in mcdf.columns
                    ),
                    None,
                )
                if col is not None:
                    mcdf = mcdf.dropna(subset=[col])
                    if not mcdf.empty:
                        top = mcdf.loc[mcdf[col].astype(float).idxmax()]
                        return str(top["Model"]), float(top[col])
        except Exception:
            pass
    return "", None


def _markdown_cell(value: Any, *, max_len: int | None = None) -> str:
    """Render a stable one-line Markdown table cell.

    Reviewer-facing audit tables should not contain embedded newlines or large raw
    JSON blobs because they corrupt the table structure and make the artifact hard
    to trust. Collapse whitespace, escape pipes, and optionally truncate.
    """

    text = str(value if value is not None else "")
    text = text.replace("|", "\\|")
    text = re.sub(r"\s+", " ", text).strip()
    if max_len is not None and len(text) > max_len:
        return text[: max(0, max_len - 1)].rstrip() + "…"
    return text


def _paper_compliance_metric_summary(payload: dict[str, Any]) -> str:
    """Compact compliance report for Markdown tables."""

    overall = str(payload.get("overall_status", "") or "").strip() or "unknown"
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return f"overall_status={overall}"
    total = len(checks)
    pass_count = 0
    fail_ids: list[str] = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        status = str(check.get("status", "") or "").strip().lower()
        if status == "pass":
            pass_count += 1
        elif status:
            fail_ids.append(str(check.get("check_id", "unknown")))
    if fail_ids:
        preview = ", ".join(fail_ids[:4])
        if len(fail_ids) > 4:
            preview += ", …"
        return f"overall_status={overall}; checks_pass={pass_count}/{total}; failing={preview}"
    return f"overall_status={overall}; checks_pass={pass_count}/{total}"


def _cohort_snapshot(manifest: dict[str, Any], mctx: dict[str, Any]) -> str:
    gov = (
        mctx.get("cohort_prepared_row_count")
        or mctx.get("governed_cohort_rows")
        or manifest.get("cohort_size")
        or ""
    )
    train = (
        (mctx.get("split") or {}).get("train_sample_count")
        if isinstance(mctx.get("split"), dict)
        else None
    ) or manifest.get("train_sample_count") or ""
    test = (
        (mctx.get("split") or {}).get("test_sample_count")
        if isinstance(mctx.get("split"), dict)
        else None
    ) or manifest.get("test_sample_count") or ""
    aligned = mctx.get("aligned_supervised_rows") or ""
    post_ls = mctx.get("post_low_support_training_rows") or ""
    return (
        f"prepared_cohort_rows≈{gov}; aligned_supervised≈{aligned}; "
        f"post_low_support_training≈{post_ls}; train≈{train}; test≈{test}"
    )


def write_paper_claim_audit_md(
    *,
    diagnostics_dir: Path,
    manifest: dict[str, Any] | None,
    manifest_context: dict[str, Any] | None,
    run_id: str,
) -> Path:
    """Write one surface-specific claim audit with evidence and wording guidance."""
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    mctx = manifest_context if isinstance(manifest_context, dict) else {}
    man = manifest if isinstance(manifest, dict) else {}
    model_summary = mctx.get("model_summary") or man.get("model_summary") or {}
    top_model = str(model_summary.get("top_model", "") or "")

    ablation_status, ablation_reason = _ablation_status(diagnostics_dir, run_id)
    ablation_rows = _ablation_rows(diagnostics_dir, run_id)
    max_by_exp = _max_f1_by_experiment(ablation_rows)
    fused = max_by_exp.get("full_fused")
    vend = max_by_exp.get("vendor_no_parsed_family")
    if vend is None:
        vend = max_by_exp.get("vendor_only")
    if vend is None:
        vend = max_by_exp.get("vendor_full")
    perm_raw = max_by_exp.get("permissions_raw")

    top_mod_name, top_mod_f1 = _model_top_macro_f1(diagnostics_dir, run_id)

    cohort_summary = man.get("cohort_summary") or {}
    nf = cohort_summary.get("n_families")
    active_train = mctx.get("trained_model_count") or man.get("trained_model_count")

    publication_ready_mode = bool(mctx.get("publication_ready_mode")) or coalesce_manifest_publication_mode(
        mctx
    ) or coalesce_manifest_publication_mode(man)
    profile_id = str(
        mctx.get("profile_id")
        or (man.get("profile_params") or {}).get("profile_id")
        or man.get("profile_id")
        or ""
    ).strip()
    benchmark_support_floor = mctx.get("benchmark_support_floor")
    support_floor_mode = str(mctx.get("support_floor_mode", "") or "").strip().lower()
    primary_surface = _primary_claim_surface(
        profile_id=profile_id,
        publication_ready_mode=publication_ready_mode,
        support_floor_mode=support_floor_mode,
        benchmark_support_floor=benchmark_support_floor,
    )
    path = diagnostics_dir / _claim_audit_filename(primary_surface)
    compliance_path = man.get("paper_mode_compliance_report") or diagnostics_dir / f"paper_mode_compliance_report_{run_id}.json"

    population_line = _cohort_snapshot(man, mctx)
    ablation_evidence = (
        f"status=unavailable; reason={ablation_reason}; run_id={run_id}"
        if ablation_status != "available"
        else f"ablation_summary_{run_id}.csv"
    )
    model_evidence = f"model_comparison_summary_{run_id}.csv or model_comparison_summary.latest.csv"

    # A cross-sectional heatmap is not temporal evidence. Only an artifact with
    # a year dimension and annual prevalence is eligible to support a temporal
    # permission claim.
    annual_paths = list(diagnostics_dir.glob(f"**/permission_prevalence_by_year*{run_id}*.csv"))
    annual_paths += list(diagnostics_dir.glob(f"**/annual_permission_prevalence*{run_id}*.csv"))
    trend_evidence = (
        annual_paths[0].name
        if annual_paths
        else "annual_permission_trend_status=NOT_AVAILABLE"
    )

    claim_rows: list[dict[str, str]] = []

    def add(
        *,
        claim: str,
        status: str,
        evidence_artifact: str,
        metric_value: str,
        population: str,
        rationale: str,
        safer_wording: str,
    ) -> None:
        claim_rows.append(
            {
                "claim": claim,
                "status": status,
                "evidence_artifact": evidence_artifact,
                "metric_value": metric_value,
                "population": population,
                "rationale": rationale,
                "safer_wording": safer_wording,
            }
        )

    if fused is not None and vend is not None:
        if fused + 1e-6 >= vend:
            fused_status = "NEEDS_REVISION"
            fused_rationale = (
                f"full_fused max macro_f1={fused:.4f} ≥ safer vendor baseline={vend:.4f}; "
                "fusion may not add independent lift — "
                "check feature independence and label leakage."
            )
        else:
            fused_status = "UNSUPPORTED"
            fused_rationale = (
                f"full_fused ({fused:.4f}) did not beat the safer vendor baseline ({vend:.4f}) "
                "on ablation summary."
            )
        fused_metric = f"max macro_f1 full_fused={fused}; safer_vendor_baseline={vend}"
    else:
        fused_status = "UNSUPPORTED"
        fused_metric = "n/a"
        fused_rationale = (
            "Ablation evidence unavailable for this run (ablation_disabled)."
            if ablation_status != "available"
            else "Missing fused or safer vendor-baseline rows for preferred family target in ablation summary."
        )

    add(
        claim="Fused multimodal features are strictly best overall",
        status=fused_status,
        evidence_artifact=ablation_evidence,
        metric_value=fused_metric,
        population=population_line,
        rationale=fused_rationale,
        safer_wording="Report per-target ablations with baselines; state whether fused beats vendor_only on same frozen split IDs.",
    )

    if perm_raw is None:
        perm_status, perm_metric, perm_reason = (
            "UNSUPPORTED", "n/a",
            "Ablation evidence unavailable for this run (ablation_disabled)."
            if ablation_status != "available" else "No permissions_raw ablation rows.",
        )
    else:
        if perm_raw >= 0.35:
            perm_status = "NEEDS_REVISION"
            perm_metric = f"permissions_raw max macro_f1={perm_raw:.4f}"
            perm_reason = "Define 'strong' vs majority / stratified / type-conditional baselines in baseline_comparison.csv."
        else:
            perm_status = "UNSUPPORTED"
            perm_metric = f"permissions_raw max macro_f1={perm_raw:.4f}"
            perm_reason = "Macro-F1 magnitude alone does not justify 'strong'; compare lift vs baselines."

    add(
        claim="Permissions-only model provides strong standalone family benchmark signal",
        status=perm_status,
        evidence_artifact=ablation_evidence,
        metric_value=perm_metric,
        population=population_line + "; label_target=family_id_or_fallback",
        rationale=perm_reason,
        safer_wording="Permissions are static declared-capability signal; quantify lift vs stratified_random and vendor baselines before making family-strength claims.",
    )

    rf_status = "UNSUPPORTED"
    rf_metric = top_mod_f1 if top_mod_f1 is not None else "n/a"
    rf_reason = f"Ranking artifact lists top_model={top_model or 'unknown'}."
    if top_model and "random_forest" in top_model.lower():
        rf_status = "NEEDS_REVISION"
        rf_reason += " Confirm on frozen split_audit hash and cite model_comparison row."
    if top_mod_name and top_mod_name != top_model:
        rf_metric = f"{top_mod_name} Macro-F1={top_mod_f1}"

    add(
        claim="Random Forest is the top-performing classifier family",
        status=rf_status,
        evidence_artifact=model_evidence + " ; manifest.model_summary.top_model",
        metric_value=str(rf_metric),
        population=population_line,
        rationale=rf_reason,
        safer_wording="State 'best-ranked on this Macro-F1 table for split hash H' rather than categorical RF superiority.",
    )

    fam39_status = "UNSUPPORTED"
    fam39_metric = str(nf) if nf is not None else "n/a"
    fam39_reason = "`n_families` in cohort_summary differs from trained active-class list unless verified against post-low-support mask."
    if nf == 39:
        fam39_status = "NEEDS_REVISION"
        fam39_reason += " Manifest reports 39 distinct families — confirm parity with classifier `classes_` after support filter."

    add(
        claim="Models evaluate all 39 malware families uniformly",
        status=fam39_status,
        evidence_artifact="manifest.cohort_summary.n_families ; training reports / classifier class list",
        metric_value=fam39_metric + f"; trained_model_count={active_train}",
        population=population_line,
        rationale=fam39_reason,
        safer_wording="Enumerate active classes post `min_family_support`; Macro-F1 is over supported classes only.",
    )

    vend_no_pf = max_by_exp.get("vendor_no_parsed_family")
    delta_note = (
        f"vendor_full={vend}; vendor_no_parsed_family={vend_no_pf}"
        if vend is not None and vend_no_pf is not None
        else "see ablation CSV vendor_full vs stripped experiments"
    )
    add(
        claim="Apache consensus metadata and declared permissions are complementary signals",
        status="UNSUPPORTED",
        evidence_artifact=ablation_evidence + " ; vendor_label_leakage_audit.csv ; baseline_comparison.csv",
        metric_value=delta_note,
        population=population_line,
        rationale="Complementarity needs orthogonality / conditional improvement tests — not pairwise bar ordering alone.",
        safer_wording="Permissions add incremental Macro-F1 of ΔX over vendor_only **on frozen split**, if row exists.",
    )

    temporal_status = "UNSUPPORTED"
    temporal_metric = trend_evidence
    temporal_reason = "Random split evaluations do not imply 2026 outlook; require temporal holdouts (train≤year vs test≥year)."
    if not annual_paths:
        temporal_metric += "; annual permission prevalence artifact absent"

    add(
        claim="Permission prevalence trends demonstrate temporal evolution 2020–2025 predictive of future years",
        status=temporal_status,
        evidence_artifact=str(trend_evidence),
        metric_value="Descriptive prevalence != validated forecast",
        population=population_line + "; see temporal_validity_audit.md",
        rationale=temporal_reason,
        safer_wording="Report descriptive year-stratified burdens with cohort gates; separate from supervised generalization.",
    )

    funnel_exists = (diagnostics_dir / "cohort_funnel.csv").exists()
    add(
        claim="Dataset construction details do not materially change conclusions",
        status="UNSUPPORTED",
        evidence_artifact="cohort_funnel.csv ; cohort_population_audit.csv (when hostile bundle runs)",
        metric_value=f"funnel_present={funnel_exists}",
        population=population_line,
        rationale="Even small N shifts remap low-support families; must cite stage-wise populations.",
        safer_wording="Each gate changes effective study population — disclose aligned vs governed deltas explicitly.",
    )

    comp_status = "UNSUPPORTED"
    comp_metric = ""
    compliance_note = "`NOT_APPLICABLE` — publication/evidence mode off"
    if publication_ready_mode:
        comp_status = "NEEDS_REVISION"
        compliance_note = f"publication/evidence mode ON — mandatory human review `{compliance_path}`"
        try:
            cpath = Path(str(compliance_path))
            if cpath.exists():
                payload = json.loads(cpath.read_text(encoding="utf-8"))
                comp_metric = _paper_compliance_metric_summary(payload)
        except Exception:
            comp_metric = "unreadable compliance json"

    add(
        claim="Evidence pack / publication-ready status is materially valid without further operator review",
        status=comp_status,
        evidence_artifact=str(compliance_path),
        metric_value=comp_metric or ("publication_ready_mode=" + str(publication_ready_mode)),
        population=population_line,
        rationale=compliance_note,
        safer_wording="Publication readiness is procedural — tie each figure to audited populations and forbid absent artifacts.",
    )

    title = {
        "locked_publication_surface": "Publication claim audit",
        "major_family_benchmark": "Benchmark claim audit",
        "broad_current_corpus": "Corpus diagnostic claim audit",
        "expanded_family_exploratory": "Expanded-family exploratory claim audit",
        "type_taxonomy_surface": "Type-taxonomy claim audit",
    }.get(primary_surface, "Claim audit")
    surface_label = {
        "locked_publication_surface": "locked publication cohort",
        "major_family_benchmark": "major-family benchmark surface",
        "broad_current_corpus": "broad current-corpus diagnostic surface",
        "expanded_family_exploratory": "expanded-family exploratory surface",
        "type_taxonomy_surface": "type-taxonomy benchmark surface",
    }.get(primary_surface, "current run surface")

    lines = [
        f"# {title} (machine-assisted, strict)",
        "",
        f"**Primary surface:** {surface_label}",
        f"**Ablation evidence:** status={ablation_status}; reason={ablation_reason or 'n/a'}; run_id={run_id}",
        "",
        "Each row binds a conversational claim to an **evidence artifact**, **metric/value**, ",
        "**population string**, adjudication status, and **replacement wording**. ",
        "`NEEDS_REVISION` means the sentence could mislead reviewers without edits; ",
        "`UNSUPPORTED` cannot be asserted as written from current artifacts.",
        "",
        "| claim | status | evidence artifact | metric / value | data population used | rationale | safer replacement wording |",
        "|-------|--------|-------------------|----------------|----------------------|-----------|----------------------------|",
    ]
    for row in claim_rows:
        cells = [
            _markdown_cell(row["claim"], max_len=160),
            _markdown_cell(row["status"], max_len=32),
            _markdown_cell(row["evidence_artifact"], max_len=220),
            _markdown_cell(row["metric_value"], max_len=220),
            _markdown_cell(row["population"], max_len=220),
            _markdown_cell(row["rationale"], max_len=220),
            _markdown_cell(row["safer_wording"], max_len=220),
        ]
        lines.append("| " + " | ".join(cells) + " |")

    lines.extend(
        [
            "",
            "## Reading guide",
            "",
            "- Prefer numbers from `cohort_population_audit.csv` once emitted (post hostile bundle). ",
            "- Cross-check lifts with `baseline_comparison.csv`; avoid citing raw Macro-F1 alone.",
            "",
        ]
    )

    body = "\n".join(lines)
    path.write_text(body, encoding="utf-8")
    return path
