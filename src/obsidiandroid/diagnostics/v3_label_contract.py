"""Compact V3 label contract artifact for governed classification runs.

Consolidates profile role, claim boundary, supervised target namespace, and
family/type label inventories into one machine-readable contract per run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.common.run_slots import resolve_run_slot_plan
from obsidiandroid.diagnostics import taxonomy_target_surface_report
from obsidiandroid.governance.family_tier_authority import CANONICAL_TYPE_TOKENS
from obsidiandroid.governance.support_floor_policy import resolve_support_floor_mode


CANONICAL_PROFILE_ROLES: dict[str, dict[str, str]] = {
    "android_malware_major_families": {
        "profile_role": "support-gated major-family benchmark surface",
        "claim_boundary": (
            "Benchmark claims on curated major families meeting the support floor. "
            "Not a full-catalog census and not publication-grade without a locked profile."
        ),
        "pass_semantics": (
            "PASS means the governed major-family benchmark cohort prepared successfully; "
            "it does not mean the same thing as a PASS on all-current or expanded-families."
        ),
    },
    "android_malware_type_taxonomy": {
        "profile_role": "malware type/category taxonomy surface",
        "claim_boundary": (
            "Type-slug supervision and type-level permission-pattern claims. "
            "Family labels are contextual audit surfaces, not the primary supervised target."
        ),
        "pass_semantics": (
            "PASS means the authoritative type taxonomy surface prepared successfully for "
            "type-level modeling and reporting."
        ),
    },
    "android_malware_expanded_families": {
        "profile_role": "broader family expansion / stress surface",
        "claim_boundary": (
            "Exploratory expanded-family research surface spanning major and valid minor families. "
            "Not a support-gated benchmark and not publication-safe without separate locking."
        ),
        "pass_semantics": (
            "PASS means the expanded-family exploratory cohort prepared successfully; "
            "headline metrics are stress/exploratory, not benchmark publication claims."
        ),
    },
    "android_malware_all_current": {
        "profile_role": "current-state census / exploratory surface",
        "claim_boundary": (
            "Diagnostic census across the current Android malware corpus. "
            "Exploratory unless separately support-gated; not a benchmark publication surface."
        ),
        "pass_semantics": (
            "PASS means the current-corpus diagnostic surface prepared successfully; "
            "it does not authorize benchmark or publication claims."
        ),
    },
}


def _claim_surface_label(profile_id: str) -> str:
    token = str(profile_id or "").strip()
    if token == "android_malware_all_current":
        return "Current-corpus diagnostic surface"
    if token == "android_malware_major_families":
        return "Support-gated benchmark cohort"
    if token == "android_malware_expanded_families":
        return "Expanded-family exploratory cohort"
    if token == "android_malware_type_taxonomy":
        return "Type taxonomy benchmark"
    return "Benchmark research surface"


def _claim_readiness_wording(*, profile_id: str, run_mode: str, support_floor_mode: str) -> str:
    role = CANONICAL_PROFILE_ROLES.get(str(profile_id or "").strip(), {})
    if role:
        return str(role.get("pass_semantics", "") or "").strip()
    if run_mode == "benchmark":
        return "PASS means the benchmark cohort prepared successfully for governed evaluation."
    if run_mode == "diagnostic":
        return "PASS means the diagnostic cohort prepared successfully; claims remain exploratory."
    if run_mode == "exploratory":
        return "PASS means the exploratory cohort prepared successfully; not a benchmark publication surface."
    if support_floor_mode == "benchmark_eligibility":
        return "PASS means benchmark-eligible labels met the configured support floor."
    return "PASS means the prepared cohort completed sample-stage label contract checks."


def _target_namespace(training_label_field: str) -> str:
    field = str(training_label_field or "family_id").strip() or "family_id"
    if field == "type_slug":
        return "malware_type_slug"
    if field == "family_within_type":
        return "malware_family_within_type"
    return "malware_family"


def _surface_lookup(targets: list[dict[str, Any]], surface_name: str) -> dict[str, Any]:
    for row in targets:
        if str(row.get("surface_name", "")).strip() == surface_name:
            return row if isinstance(row, dict) else {}
    return {}


def _build_family_label_summary(
    samples_df: pd.DataFrame,
    *,
    taxonomy_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    per_family = taxonomy_summary.get("per_family_support", [])
    if not isinstance(per_family, list) or not per_family:
        return []
    rows: list[dict[str, Any]] = []
    for entry in per_family:
        if not isinstance(entry, dict):
            continue
        sample_count = int(entry.get("sample_count", 0) or 0)
        benchmark_eligible = bool(entry.get("benchmark_eligible"))
        exclusion = str(entry.get("benchmark_exclusion_reason", "") or "").strip()
        tier = str(entry.get("family_tier", "") or "").strip()
        rows.append(
            {
                "family_slug": str(entry.get("family_canonical", "") or "").strip().lower(),
                "family_display_name": str(entry.get("family_canonical", "") or "").strip(),
                "type_slug": str(entry.get("type_slug", "") or "").strip(),
                "sample_count": sample_count,
                "family_support_tier": tier or "unknown",
                "benchmark_eligible": benchmark_eligible,
                "family_claim_readiness": (
                    "benchmark_eligible"
                    if benchmark_eligible
                    else ("excluded_below_support" if exclusion else "authority_present_not_benchmark")
                ),
                "exclusion_reason": exclusion or None,
            }
        )
    rows.sort(key=lambda item: (-int(item.get("sample_count", 0)), str(item.get("family_slug", ""))))
    return rows


def _build_type_label_summary(samples_df: pd.DataFrame, *, min_support: int) -> list[dict[str, Any]]:
    if not isinstance(samples_df, pd.DataFrame) or samples_df.empty or "type_slug" not in samples_df.columns:
        return []
    series = (
        samples_df["type_slug"]
        .fillna("")
        .astype(str)
        .str.strip()
    )
    series = series[series != ""]
    if series.empty:
        return []
    counts = series.value_counts()
    rows: list[dict[str, Any]] = []
    for type_slug, sample_count in counts.items():
        count = int(sample_count)
        token = str(type_slug).strip().lower()
        eligible = token in CANONICAL_TYPE_TOKENS
        rows.append(
            {
                "type_slug": token,
                "type_display_name": str(type_slug).strip(),
                "sample_count": count,
                "type_support_tier": (
                    "benchmark_trainable"
                    if eligible and count >= max(1, int(min_support))
                    else ("retired_or_noncanonical" if not eligible else "below_min_support")
                ),
                "type_claim_readiness": (
                    "type_target_eligible"
                    if eligible and count >= max(1, int(min_support))
                    else ("not_type_target" if not eligible else "below_min_support")
                ),
                "exclusion_reason": (
                    None
                    if eligible and count >= max(1, int(min_support))
                    else ("retired_or_noncanonical_type" if not eligible else f"support_below_{int(min_support)}")
                ),
            }
        )
    rows.sort(key=lambda item: (-int(item.get("sample_count", 0)), str(item.get("type_slug", ""))))
    return rows


def build_v3_label_contract(
    *,
    profile: dict[str, Any],
    samples_df: pd.DataFrame,
    taxonomy_summary: dict[str, Any] | None = None,
    run_id: str = "",
) -> dict[str, Any]:
    """Build the compact V3 label contract payload for one prepared cohort."""
    profile_id = str(profile.get("profile_id", "") or "").strip()
    training_label_field = str(profile.get("training_label_field", "") or "").strip() or "family_id"
    gates = profile.get("cohort_gates") if isinstance(profile.get("cohort_gates"), dict) else {}
    profile_status = profile.get("profile_status") if isinstance(profile.get("profile_status"), dict) else {}
    support_floor_mode = resolve_support_floor_mode(gates)
    slot_plan = resolve_run_slot_plan(
        profile_id=profile_id,
        paper_locked=bool(profile.get("paper_locked", False)),
        evidence_mode=bool(profile.get("evidence_mode", False)),
        keep_run_output=False,
    )
    role_meta = dict(CANONICAL_PROFILE_ROLES.get(profile_id, {}))
    if taxonomy_summary is None:
        min_support = gates.get("min_samples_per_family")
        taxonomy_summary = taxonomy_target_surface_report.build_taxonomy_target_surface_summary(
            samples_df,
            min_support=int(min_support) if min_support not in (None, "") else 1,
        )

    targets = taxonomy_summary.get("targets", []) if isinstance(taxonomy_summary.get("targets"), list) else []
    family_surface = _surface_lookup(targets, "family_id")
    type_surface = _surface_lookup(targets, "type_slug")
    tier_counts = taxonomy_summary.get("tier_counts", {}) if isinstance(taxonomy_summary.get("tier_counts"), dict) else {}
    benchmark_policy = (
        taxonomy_summary.get("benchmark_support_policy")
        if isinstance(taxonomy_summary.get("benchmark_support_policy"), dict)
        else {}
    )
    min_support = int(benchmark_policy.get("benchmark_min_support") or gates.get("min_samples_per_family") or 1)

    supervised_surface = (
        type_surface
        if training_label_field == "type_slug"
        else family_surface
    )
    family_summary = _build_family_label_summary(samples_df, taxonomy_summary=taxonomy_summary)
    type_summary = _build_type_label_summary(samples_df, min_support=min_support)

    included_family_labels = [
        row for row in family_summary if row.get("family_claim_readiness") == "benchmark_eligible"
    ] if support_floor_mode == "benchmark_eligibility" else [
        row for row in family_summary if row.get("sample_count", 0) > 0
    ]
    excluded_family_labels = [
        {
            "label": row.get("family_display_name"),
            "namespace": "malware_family",
            "sample_count": row.get("sample_count"),
            "exclusion_reason": row.get("exclusion_reason") or row.get("family_claim_readiness"),
        }
        for row in family_summary
        if row not in included_family_labels
    ]

    included_type_labels = [row for row in type_summary if not row.get("exclusion_reason")]
    excluded_type_labels = [
        {
            "label": row.get("type_display_name"),
            "namespace": "malware_type_slug",
            "sample_count": row.get("sample_count"),
            "exclusion_reason": row.get("exclusion_reason"),
        }
        for row in type_summary
        if row.get("exclusion_reason")
    ]

    return {
        "contract_version": "v3_label_contract_v1",
        "run_id": str(run_id or "").strip(),
        "profile_id": profile_id,
        "profile_role": role_meta.get("profile_role", "non_canonical_profile"),
        "claim_boundary": role_meta.get("claim_boundary", "Use profile-specific claim audits before publication."),
        "claim_surface_label": _claim_surface_label(profile_id),
        "claim_surface_code": slot_plan.claim_surface,
        "run_mode": slot_plan.run_mode,
        "support_readiness_tier": str(profile_status.get("support_tier", "") or "unknown"),
        "cohort_readiness_bucket": str(profile.get("cohort_readiness_bucket", "") or ""),
        "support_floor_mode": support_floor_mode,
        "training_label_field": training_label_field,
        "target_label_namespace": _target_namespace(training_label_field),
        "included_label_count": int(supervised_surface.get("trainable_classes_at_min_support", 0) or 0),
        "included_sample_count": int(supervised_surface.get("trainable_rows_at_min_support", 0) or 0),
        "present_label_count": int(supervised_surface.get("unique_classes", 0) or 0),
        "present_sample_count": int(supervised_surface.get("present_rows", 0) or 0),
        "claim_readiness_wording": _claim_readiness_wording(
            profile_id=profile_id,
            run_mode=slot_plan.run_mode,
            support_floor_mode=support_floor_mode,
        ),
        "label_strategy": taxonomy_summary.get("label_strategy", {}),
        "family_label_summary": family_summary,
        "type_label_summary": type_summary,
        "label_exclusion_reasons": {
            "families": excluded_family_labels,
            "types": excluded_type_labels,
            "benchmark_excluded_below_support_families": benchmark_policy.get("excluded_below_support_families", []),
            "non_family_target_samples": int(tier_counts.get("excluded_non_family_target_samples", 0) or 0),
            "below_benchmark_support_samples": int(tier_counts.get("excluded_below_benchmark_support_samples", 0) or 0),
        },
        "permission_pattern_disclaimer": (
            "Permission patterns describe structural declared-capability associations. "
            "They do not prove malware by themselves and do not substitute for dynamic analysis."
        ),
        "not_supported_claims": [
            "dynamic_analysis_execution",
            "deep_learning_model_training_or_inference",
            "mitre_attack_mapping_as_primary_claim",
            "full_catalog_publication_without_support_gating",
        ],
    }


def export_v3_label_contract(
    *,
    diagnostics_dir: Path,
    run_id: str,
    profile: dict[str, Any],
    samples_df: pd.DataFrame,
    taxonomy_summary: dict[str, Any] | None = None,
    min_support: int | None = None,
) -> list[str]:
    """Write run-scoped V3 label contract artifacts and return their paths."""
    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    if taxonomy_summary is None:
        taxonomy_summary = taxonomy_target_surface_report.build_taxonomy_target_surface_summary(
            samples_df,
            min_support=int(min_support or 1),
        )
    payload = build_v3_label_contract(
        profile=profile,
        samples_df=samples_df,
        taxonomy_summary=taxonomy_summary,
        run_id=run_id,
    )

    json_path = diagnostics_dir / f"v3_label_contract_{run_id}.json"
    md_path = diagnostics_dir / f"v3_label_contract_{run_id}.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    oh.mirror_json_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=json_path.name,
        payload=payload,
        global_latest_name="v3_label_contract.latest.json",
    )

    lines = [
        "# V3 Label Contract",
        "",
        f"Run ID: `{run_id}`",
        f"Profile: `{payload.get('profile_id', '')}`",
        "",
        "## Profile role and claim boundary",
        "",
        f"- **Profile role:** {payload.get('profile_role', '')}",
        f"- **Claim boundary:** {payload.get('claim_boundary', '')}",
        f"- **Claim surface:** {payload.get('claim_surface_label', '')}",
        f"- **Run mode:** `{payload.get('run_mode', '')}`",
        f"- **Support readiness tier:** `{payload.get('support_readiness_tier', '')}`",
        f"- **Claim readiness:** {payload.get('claim_readiness_wording', '')}",
        "",
        "## Supervised target",
        "",
        f"- **Training label field:** `{payload.get('training_label_field', '')}`",
        f"- **Target namespace:** `{payload.get('target_label_namespace', '')}`",
        f"- **Included labels:** {int(payload.get('included_label_count', 0) or 0)}",
        f"- **Included samples:** {int(payload.get('included_sample_count', 0) or 0)}",
        f"- **Present labels:** {int(payload.get('present_label_count', 0) or 0)}",
        f"- **Present samples:** {int(payload.get('present_sample_count', 0) or 0)}",
        "",
        "## Family labels (audit surface)",
        "",
        "| family | type | samples | support tier | claim readiness | exclusion |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    for row in payload.get("family_label_summary", [])[:40]:
        lines.append(
            f"| `{row.get('family_display_name', '')}` | `{row.get('type_slug', '')}` | "
            f"{int(row.get('sample_count', 0))} | `{row.get('family_support_tier', '')}` | "
            f"`{row.get('family_claim_readiness', '')}` | `{row.get('exclusion_reason') or ''}` |"
        )
    lines.extend(
        [
            "",
            "## Type labels (audit surface)",
            "",
            "| type | samples | support tier | claim readiness | exclusion |",
            "| --- | ---: | --- | --- | --- |",
        ]
    )
    for row in payload.get("type_label_summary", [])[:40]:
        lines.append(
            f"| `{row.get('type_display_name', '')}` | {int(row.get('sample_count', 0))} | "
            f"`{row.get('type_support_tier', '')}` | `{row.get('type_claim_readiness', '')}` | "
            f"`{row.get('exclusion_reason') or ''}` |"
        )
    exclusions = payload.get("label_exclusion_reasons", {}) if isinstance(payload.get("label_exclusion_reasons"), dict) else {}
    lines.extend(
        [
            "",
            "## Claim safety",
            "",
            f"- {payload.get('permission_pattern_disclaimer', '')}",
            "- Not supported by V3:",
        ]
    )
    for item in payload.get("not_supported_claims", []):
        lines.append(f"  - `{item}`")
    lines.append("")
    md_text = "\n".join(lines).strip() + "\n"
    md_path.write_text(md_text, encoding="utf-8")
    oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=md_path.name,
        text=md_text,
        global_latest_name="v3_label_contract.latest.md",
    )
    return [str(json_path), str(md_path)]
