"""Operator-facing terminal run health summary."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from obsidiandroid.cli.ui import display as du
from obsidiandroid.common.publication_readiness import (
    coalesce_publication_ready_reasons,
    coalesce_publication_ready_status,
)
from obsidiandroid.governance.evidence_mode_resolver import (
    coalesce_manifest_evidence_mode,
    coalesce_manifest_publication_mode,
)
from obsidiandroid.labeling.malware_family_constants import canonicalize_family_label

_BANKER_WARNING_RE = re.compile(r"banker share\s+([0-9.]+%)\s+exceeds\s+([0-9.]+%)", re.IGNORECASE)
_RAW_CANONICAL_RE = re.compile(
    r"raw family label differs from canonical family:\s*([0-9]+)",
    re.IGNORECASE,
)


def print_unified_run_health(
    *,
    inventory_summary: dict[str, Any],
    observability_json_path: Path,
    evidence_index_path: Path | None,
    run_root: Path,
) -> None:
    """Print a compact operator-facing run-health verdict block."""
    del inventory_summary

    base = Path(observability_json_path).parent
    payload: dict[str, Any] = {}
    obs_resolved = Path(observability_json_path)
    for cand in (base / "run_observability_summary.json", obs_resolved):
        if not cand.exists():
            continue
        try:
            payload = json.loads(cand.read_text(encoding="utf-8"))
            obs_resolved = cand
            break
        except Exception:
            payload = {}

    du.print_section("Run Health")

    _print_group(
        "Run status",
        [
            ("Pipeline", payload.get("pipeline_status", "UNKNOWN")),
            ("Research validity bundle", _format_status_with_reason(payload, "research_validity_status", "research_validity_skip_reason")),
            ("Skeptic audit", _format_status_with_reason(payload, "hostile_audit_status", "hostile_audit_skip_reason")),
            ("Scientific adequacy", _scientific_posture(payload)),
            ("Profile", payload.get("profile_id", "unknown")),
            ("Run mode", _run_mode_line(payload)),
            ("Claim surface", payload.get("claim_surface_label") or payload.get("claim_surface") or "n/a"),
            ("Publication status", coalesce_publication_ready_status(payload)),
            *(_run_identity_rows(payload, run_root)),
        ],
    )

    _print_group(
        "Benchmark surface",
        [
            ("Row authority", payload.get("main_training_row_authority") or payload.get("row_authority") or "n/a"),
            ("Family target", _label_strategy_value(payload, "preferred_family_target")),
            ("Type target", _label_strategy_value(payload, "preferred_type_target")),
            ("Avoid primary claims on", _label_strategy_avoid(payload)),
            ("Label resolution", "ENABLED" if payload.get("label_resolution_enabled", True) else "DISABLED"),
            (
                "Type-guard suppressions",
                (
                    "unavailable (label resolution disabled)"
                    if payload.get("label_resolution_enabled") is False
                    else str(payload.get("type_guard_family_suppressed_count", 0))
                ),
            ),
        ],
    )

    support_gate = _support_gate_line(payload)
    _print_group(
        "Benchmark eligibility",
        [
            ("Prepared cohort", _safe_value(payload.get("cohort_rows") or payload.get("cohort_prepared_row_count"))),
            ("Visible governed families", _safe_value(payload.get("visible_family_count"))),
            ("Benchmark trainable", _safe_value(payload.get("post_low_support_training_rows") or payload.get("counts", {}).get("post_low_support_training_rows"))),
            ("Active benchmark family classes", _safe_value(payload.get("benchmark_trainable_family_count"))),
            ("Actual modeled family classes", _safe_value(payload.get("modeled_family_class_count"))),
            ("Support gate", support_gate[0]),
            ("Support exclusions", support_gate[1]),
            ("Excluded families", support_gate[2]),
        ],
    )

    _print_model_summary(payload)

    warning_rows = _warning_rows(payload)
    if warning_rows:
        du.print_subheader("Warnings")
        for severity, label, message in warning_rows:
            print(f"[{severity}] {label}: {message}")

    _print_group(
        "Next artifacts",
        [
            ("Start here", _start_here_path(run_root, evidence_index_path)),
            ("Cohort/taxonomy", _best_existing_rel(run_root, _artifact_candidates(run_root, obs_resolved.parent, "taxonomy", payload=payload))),
            ("Family/type coverage", _best_existing_rel(run_root, _artifact_candidates(run_root, obs_resolved.parent, "coverage", payload=payload))),
            ("Claim audit", _best_existing_rel(run_root, _artifact_candidates(run_root, obs_resolved.parent, "claim_audit", payload=payload))),
            ("Ablation summary", _ablation_summary_path(run_root, obs_resolved.parent, payload)),
        ],
        compact=True,
    )

    _print_group(
        "Timing",
        [
            ("Manifest finalization", _format_seconds(payload.get("manifest_finalize_duration_sec"))),
        ],
    )

    publication_ready_reasons = coalesce_publication_ready_reasons(payload)
    if publication_ready_reasons:
        du.print_note(f"Publication detail: {', '.join(str(x) for x in publication_ready_reasons)}")


def _print_group(title: str, rows: list[tuple[str, Any]], *, compact: bool = False) -> None:
    du.print_subheader(title)
    for label, value in rows:
        if value in (None, "", "n/a"):
            continue
        du.print_stat(label, value, width=0 if compact else 32)


def _print_model_summary(payload: dict[str, Any]) -> None:
    """Print the end-of-run model handoff without table-style padding."""
    du.print_subheader("Model summary")
    rows = [
        ("Main model", _main_model_name(payload)),
        ("Macro-F1", _main_macro_f1(payload)),
        ("Primary metric", _main_primary_metric_name(payload)),
        ("Primary tier", _main_primary_tier(payload)),
        ("Weighted-F1 tier", _main_weighted_tier(payload)),
        ("Accuracy tier", _main_accuracy_tier(payload)),
        ("Test set", _safe_value(payload.get("test_sample_count") or payload.get("counts", {}).get("test_rows"))),
        ("Feature columns", _feature_column_line(payload)),
    ]
    for label, value in rows:
        if value not in (None, "", "n/a"):
            du.print_stat(label, value, width=0)

    status, details = _ablation_summary_parts(payload)
    if status == "n/a":
        return
    du.print_stat("Ablation", status, width=0)
    for detail in details:
        print(f"  - {detail}")


def _format_status_with_reason(payload: dict[str, Any], status_key: str, reason_key: str) -> str:
    status = str(payload.get(status_key, "UNKNOWN") or "UNKNOWN").strip()
    reason = str(payload.get(reason_key, "") or "").strip()
    return f"{status} ({reason})" if reason else status


def _scientific_posture(payload: dict[str, Any]) -> str:
    scientific = payload.get("scientific_adequacy") if isinstance(payload.get("scientific_adequacy"), dict) else {}
    return str(scientific.get("posture", "") or "n/a")


def _run_mode_line(payload: dict[str, Any]) -> str:
    run_mode = str(payload.get("run_mode", "") or "n/a")
    evidence_mode = "ON" if coalesce_manifest_evidence_mode(payload.get("evidence_mode")) else "OFF"
    publication_mode = "ON" if coalesce_manifest_publication_mode(payload) else "OFF"
    return f"{run_mode}; evidence {evidence_mode}; publication {publication_mode}"


def _run_identity_rows(payload: dict[str, Any], run_root: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    run_slot = str(payload.get("run_slot", "") or "").strip()
    run_instance_id = str(payload.get("run_instance_id", "") or payload.get("run_id", "") or "").strip()
    started = str(payload.get("run_started_at_utc", "") or "").strip()
    if run_slot:
        rows.append(("Run slot", run_slot))
    if run_instance_id:
        rows.append(("Run instance", run_instance_id))
    if run_root:
        rows.append(("Output path", du.format_console_path(run_root)))
    if started:
        rows.append(("Started UTC", started))
    return rows


def _label_strategy_value(payload: dict[str, Any], key: str) -> str:
    label_strategy = payload.get("label_strategy") if isinstance(payload.get("label_strategy"), dict) else {}
    return str(label_strategy.get(key, "") or "n/a")


def _label_strategy_avoid(payload: dict[str, Any]) -> str:
    label_strategy = payload.get("label_strategy") if isinstance(payload.get("label_strategy"), dict) else {}
    avoid = label_strategy.get("avoid_for_primary_claims")
    if isinstance(avoid, list) and avoid:
        return ", ".join(str(x) for x in avoid)
    return "n/a"


def _safe_value(value: Any) -> str:
    if value in (None, "", "n/a"):
        return "n/a"
    return f"{int(value):,}" if isinstance(value, (int, float)) and not isinstance(value, bool) else str(value)


def _support_gate_line(payload: dict[str, Any]) -> tuple[str, str, str]:
    floor = payload.get("benchmark_support_floor")
    floor_text = f"n>={int(floor)}" if floor not in (None, "") else "n/a"

    benchmark_rows = int(payload.get("benchmark_support_excluded_sample_count", 0) or 0)
    benchmark_fams = int(payload.get("benchmark_support_excluded_family_count", 0) or 0)
    benchmark_top = _normalize_family_count_preview(str(payload.get("benchmark_support_excluded_families_top", "") or ""))
    if benchmark_rows > 0 or benchmark_fams > 0 or benchmark_top:
        return (
            floor_text,
            f"{benchmark_rows:,} rows / {benchmark_fams:,} families",
            benchmark_top or "n/a",
        )

    low_rows = int(payload.get("low_support_row_drop_count", 0) or 0)
    low_fams = int(payload.get("low_support_family_drop_count", 0) or 0)
    low_top = _normalize_family_count_preview(str(payload.get("low_support_family_drops_top", "") or ""))
    return (
        floor_text,
        f"{low_rows:,} rows / {low_fams:,} families",
        low_top or "n/a",
    )


def _normalize_family_count_preview(value: str) -> str:
    parts = []
    for raw_part in str(value or "").split(","):
        token = raw_part.strip()
        if not token or "=" not in token:
            continue
        family, count = token.split("=", 1)
        family_display = canonicalize_family_label(family.strip())
        parts.append(f"{family_display}={count.strip()}")
    return ", ".join(parts)


def _main_model_name(payload: dict[str, Any]) -> str:
    model_summary = payload.get("model_summary") if isinstance(payload.get("model_summary"), dict) else {}
    if model_summary:
        return str(model_summary.get("top_model", "") or "n/a")
    model_block = payload.get("model") if isinstance(payload.get("model"), dict) else {}
    return str(model_block.get("top_model", "") or "n/a")


def _main_macro_f1(payload: dict[str, Any]) -> str:
    model_summary = payload.get("model_summary") if isinstance(payload.get("model_summary"), dict) else {}
    value = model_summary.get("top_macro_f1") if model_summary else None
    if value in (None, ""):
        model_block = payload.get("model") if isinstance(payload.get("model"), dict) else {}
        value = model_block.get("top_macro_f1")
    if value in (None, ""):
        return "n/a"
    return f"{float(value):.4f}"


def _main_primary_metric_name(payload: dict[str, Any]) -> str:
    model_summary = payload.get("model_summary") if isinstance(payload.get("model_summary"), dict) else {}
    value = model_summary.get("top_model_primary_metric_name") if model_summary else None
    if value in (None, ""):
        model_block = payload.get("model") if isinstance(payload.get("model"), dict) else {}
        value = model_block.get("top_model_primary_metric_name")
    return str(value or "n/a")


def _main_primary_tier(payload: dict[str, Any]) -> str:
    model_summary = payload.get("model_summary") if isinstance(payload.get("model_summary"), dict) else {}
    value = model_summary.get("top_model_primary_metric_tier") if model_summary else None
    if value in (None, ""):
        model_block = payload.get("model") if isinstance(payload.get("model"), dict) else {}
        value = model_block.get("top_model_primary_metric_tier")
    return str(value or "n/a")


def _main_weighted_tier(payload: dict[str, Any]) -> str:
    model_summary = payload.get("model_summary") if isinstance(payload.get("model_summary"), dict) else {}
    value = model_summary.get("top_model_weighted_f1_tier") if model_summary else None
    if value in (None, ""):
        model_block = payload.get("model") if isinstance(payload.get("model"), dict) else {}
        value = model_block.get("top_model_weighted_f1_tier")
    return str(value or "n/a")


def _main_accuracy_tier(payload: dict[str, Any]) -> str:
    model_summary = payload.get("model_summary") if isinstance(payload.get("model_summary"), dict) else {}
    value = model_summary.get("top_model_accuracy_tier") if model_summary else None
    if value in (None, ""):
        model_block = payload.get("model") if isinstance(payload.get("model"), dict) else {}
        value = model_block.get("top_model_accuracy_tier")
    return str(value or "n/a")


def _feature_column_line(payload: dict[str, Any]) -> str:
    features = payload.get("features") if isinstance(payload.get("features"), dict) else {}
    pre = features.get("feature_matrix_cols_pre_prune") or features.get("pre_prune")
    post = features.get("feature_matrix_cols_post_prune") or features.get("post_prune")
    if pre in (None, "") and post in (None, ""):
        return "n/a"
    return f"{_safe_value(pre)} → {_safe_value(post)}"


def _ablation_line(payload: dict[str, Any]) -> str:
    ablation = payload.get("ablation") if isinstance(payload.get("ablation"), dict) else {}
    status_line = str(ablation.get("status_line", "") or payload.get("ablation_status", "") or "n/a").strip()
    if not status_line:
        return "n/a"
    # Keep each quantity labelled: artifact count is not experiment count.
    # Older run records used ``artifact_paths=`` / ``ablation_grid_status=``;
    # normalize them without dropping the field name.
    text = status_line.replace("artifact_paths=", "artifacts=").replace(
        "ablation_grid_status=", "status="
    )
    text = text.replace("skipped_experiments=", "skipped=")
    text = text.replace(" | ", "; ")
    return text


def _ablation_summary_parts(payload: dict[str, Any]) -> tuple[str, list[str]]:
    """Return a short ablation status followed by readable detail lines."""
    line = _ablation_line(payload)
    if line == "n/a":
        return line, []

    fields: dict[str, str] = {}
    for token in line.split():
        key, separator, value = token.partition("=")
        if separator and key and value:
            fields[key] = value
    status = fields.pop("status", line)

    first_line_keys = ("trainable_experiments", "skipped")
    second_line_keys = ("summary_rows", "artifacts", "summary")
    detail_lines = [
        " ".join(f"{key}={fields[key]}" for key in keys if key in fields)
        for keys in (first_line_keys, second_line_keys)
    ]
    return status, [line for line in detail_lines if line]


def _warning_rows(payload: dict[str, Any]) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    profile_id = str(payload.get("profile_id", "") or "").strip()
    warnings = payload.get("research_warnings_top") or payload.get("research_warnings") or []
    if not isinstance(warnings, list):
        warnings = []
    seen: set[tuple[str, str]] = set()
    for message in [str(item or "").strip() for item in warnings if str(item or "").strip()]:
        banker_match = _BANKER_WARNING_RE.search(message)
        if banker_match:
            item = ("HIGH", "Banker share", f"{banker_match.group(1)} exceeds {banker_match.group(2)}")
            if item[:2] not in seen:
                seen.add(item[:2])
                rows.append(item)
            continue
        family_match = _RAW_CANONICAL_RE.search(message)
        if family_match:
            # This count is a source-label disagreement review signal, not the
            # taxonomy mismatch count exposed in the observability payload.
            # Keeping the two concepts separate avoids suggesting that a
            # governed taxonomy conflict exists when only an alias/raw-label
            # reconciliation needs review.
            item = ("MEDIUM", "Family-label review", f"raw-label disagreements={family_match.group(1)}")
            if item[:2] not in seen:
                seen.add(item[:2])
                rows.append(item)
            continue
    if not rows:
        family_conflicts = int(payload.get("family_conflict_count", 0) or 0)
        if family_conflicts > 0:
            rows.append(("MEDIUM", "Taxonomy conflicts", f"canonical taxonomy mismatches={family_conflicts}"))
    if not rows and warnings:
        preview = " | ".join(str(item) for item in warnings[:3])
        if len(warnings) > 3:
            preview += f" (+{len(warnings) - 3} more in diagnostics)"
        rows.append(("MEDIUM", "Research warnings", preview))
    if profile_id == "android_malware_all_current":
        rows.append(
            (
                "MEDIUM",
                "Current corpus",
                "diagnostic/research surface only; avoid benchmark-quality overclaims on long-tail family results",
            )
        )
    return rows[:4]


def _artifact_candidates(
    run_root: Path,
    diagnostics_dir: Path,
    lane: str,
    *,
    payload: dict[str, Any] | None = None,
) -> list[Path]:
    if lane == "taxonomy":
        return [
            diagnostics_dir / "taxonomy_authority_split.latest.md",
            *sorted(diagnostics_dir.glob("taxonomy_authority_split_*.md")),
        ]
    if lane == "coverage":
        return [
            *sorted(diagnostics_dir.glob("family_type_authority_coverage_*.md")),
        ]
    if lane == "claim_audit":
        resolved_claim_audit = None
        if isinstance(payload, dict):
            resolved_claim_audit = str(payload.get("claim_audit_summary", "") or "").strip()
        candidates: list[Path] = []
        if resolved_claim_audit:
            candidates.append(Path(resolved_claim_audit))
        candidates.extend(
            [
                diagnostics_dir / "benchmark_claim_audit.md",
                diagnostics_dir / "research_claim_audit.md",
                diagnostics_dir / "publication_claim_audit.md",
                diagnostics_dir / "paper_claim_audit.md",
            ]
        )
        return [
            *candidates,
        ]
    return []


def _start_here_path(run_root: Path, evidence_index_path: Path | None) -> str:
    diagnostics_dir = run_root / "diagnostics"
    candidates = [
        diagnostics_dir / "run_science_index.md",
        diagnostics_dir / "index.md",
        diagnostics_dir / "run_artifact_index.md",
        evidence_index_path if evidence_index_path else None,
    ]
    return _best_existing_rel(run_root, candidates)


def _ablation_summary_path(run_root: Path, diagnostics_dir: Path, payload: dict[str, Any]) -> str:
    status_line = str((payload.get("ablation") or {}).get("status_line", "") or "").strip()
    match = re.search(r"summary=([A-Za-z0-9_.-]+)", status_line)
    candidates: list[Path] = []
    if match:
        candidates.append(diagnostics_dir / match.group(1))
    candidates.extend(sorted(diagnostics_dir.glob("ablation_summary*.csv")))
    return _best_existing_rel(run_root, candidates)


def _best_existing_rel(run_root: Path, candidates: list[Path | None]) -> str:
    for candidate in candidates:
        if candidate and candidate.exists():
            return _short_display_path(str(candidate), base=run_root)
    return "n/a"


def _open_first_hints(
    evidence_index_path: Path | None,
    logging_audit: Path,
    *,
    verbose_run_artifacts: bool,
    research_validity_enabled: bool,
    claim_audit_summary: str | None = None,
) -> list[str]:
    """Compatibility helper for existence-aware open-first artifact hints."""
    hints: list[str] = []
    if evidence_index_path and evidence_index_path.exists():
        hints.append(str(evidence_index_path))
    parent = evidence_index_path.parent if evidence_index_path else Path(".")
    names = ["pipeline_stage_summary.md"]
    if research_validity_enabled:
        claim_audit_name = Path(str(claim_audit_summary or "")).name if str(claim_audit_summary or "").strip() else ""
        ordered_claim_names = [
            name
            for name in (
                claim_audit_name,
                "benchmark_claim_audit.md",
                "research_claim_audit.md",
                "publication_claim_audit.md",
                "paper_claim_audit.md",
            )
            if name
        ]
        names = [
            "cohort_funnel.md",
            *ordered_claim_names,
            "recommended_findings.md",
            "figure_validity_audit.md",
            *names,
        ]
    for name in names:
        candidate = parent / name
        if candidate.exists():
            hints.append(str(candidate))
    ros = (parent / "diagnostics" / "run_observability_summary.json") if evidence_index_path else Path(".")
    if ros.exists():
        hints.append(str(ros))
    if verbose_run_artifacts and logging_audit.exists():
        hints.append(str(logging_audit))
    deduped: list[str] = []
    seen: set[str] = set()
    for item in hints:
        if item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped[:5]


def _short_display_path(value: str, *, base: Path | None = None) -> str:
    text = str(value).strip()
    if not text:
        return text
    try:
        path = Path(text)
        if base is not None:
            try:
                return path.resolve().relative_to(base.resolve()).as_posix()
            except Exception:
                pass
        return path.name or text
    except Exception:
        return text


def _format_seconds(value: Any) -> str:
    if value in (None, ""):
        return "n/a"
    try:
        return f"{float(value):.2f}s"
    except (TypeError, ValueError):
        return str(value)


__all__ = ["print_unified_run_health"]
