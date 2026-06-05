"""Standalone V3 permission-pattern contract artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from obsidiandroid.common import output_hygiene as oh
from obsidiandroid.pipeline.permission_trends.pattern_framework import (
    COMPARISON_SCOPES,
    PATTERN_CLAIM_BOUNDARY,
    PATTERN_UNSUPPORTED_CLAIMS,
    build_pattern_scale_contract,
)


def _artifact_exists(diagnostics_dir: Path, stem: str, run_id: str) -> bool:
    for suffix in (".csv", ".json", ".md"):
        if (diagnostics_dir / f"{stem}_{run_id}{suffix}").exists():
            return True
        latest = diagnostics_dir / f"{stem}.latest{suffix}"
        if latest.exists():
            return True
    return False


def build_permission_pattern_contract_payload(
    *,
    run_id: str,
    profile_id: str,
    diagnostics_dir: Path | None = None,
) -> dict[str, Any]:
    """Build the standalone permission-pattern contract payload."""
    diag = Path(diagnostics_dir) if diagnostics_dir is not None else None
    available_scopes: dict[str, bool] = {}
    if diag is not None:
        available_scopes = {
            "type_vs_global": _artifact_exists(diag, "permission_type_enrichment", run_id)
            or _artifact_exists(diag, "permission_prevalence_by_type", run_id),
            "family_vs_global": _artifact_exists(diag, "permission_family_enrichment", run_id)
            or _artifact_exists(diag, "permission_prevalence_by_family", run_id),
            "family_vs_type": _artifact_exists(diag, "family_permission_similarity", run_id)
            or _artifact_exists(diag, "type_permission_similarity", run_id),
            "type_prevalence": _artifact_exists(diag, "permission_prevalence_by_type", run_id),
            "family_prevalence": _artifact_exists(diag, "permission_prevalence_by_family", run_id),
            "pairwise_similarity": _artifact_exists(diag, "family_permission_similarity", run_id),
        }
    return {
        "contract_version": "v3_permission_pattern_contract_v1",
        "run_id": str(run_id or "").strip(),
        "profile_id": str(profile_id or "").strip(),
        "pattern_scale": build_pattern_scale_contract(),
        "comparison_scopes": dict(COMPARISON_SCOPES),
        "available_comparison_scopes": available_scopes,
        "pattern_claim_boundary": PATTERN_CLAIM_BOUNDARY,
        "unsupported_claims": list(PATTERN_UNSUPPORTED_CLAIMS),
        "related_artifacts": {
            "permission_pattern_summary": f"permission_pattern_summary_{run_id}.md",
            "permission_prevalence_by_type": f"permission_prevalence_by_type_{run_id}.csv",
            "permission_prevalence_by_family": f"permission_prevalence_by_family_{run_id}.csv",
            "permission_type_enrichment": f"permission_type_enrichment_{run_id}.csv",
            "permission_family_enrichment": f"permission_family_enrichment_{run_id}.csv",
            "family_permission_similarity": f"family_permission_similarity_{run_id}.csv",
            "type_permission_similarity": f"type_permission_similarity_{run_id}.csv",
        },
    }


def export_permission_pattern_contract(
    *,
    diagnostics_dir: Path,
    run_id: str,
    profile_id: str,
) -> list[str]:
    """Write run-scoped permission-pattern contract artifacts."""
    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    payload = build_permission_pattern_contract_payload(
        run_id=run_id,
        profile_id=profile_id,
        diagnostics_dir=diagnostics_dir,
    )

    json_path = diagnostics_dir / f"permission_pattern_contract_{run_id}.json"
    md_path = diagnostics_dir / f"permission_pattern_contract_{run_id}.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    oh.mirror_json_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=json_path.name,
        payload=payload,
        global_latest_name="permission_pattern_contract.latest.json",
    )

    scale = payload.get("pattern_scale", {}) if isinstance(payload.get("pattern_scale"), dict) else {}
    lines = [
        "# V3 Permission Pattern Contract",
        "",
        f"Run ID: `{run_id}`",
        f"Profile: `{profile_id}`",
        "",
        "## Pattern scale",
        "",
        f"- **Scale name:** `{scale.get('scale_name', '')}`",
        f"- **Scale version:** `{scale.get('scale_version', '')}`",
        f"- **Framing:** structural association strength (not malware proof or causality)",
        "",
        "### Level definitions (0–9)",
        "",
        "| level | label | definition |",
        "| ---: | --- | --- |",
    ]
    for row in scale.get("levels", []):
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| {int(row.get('level', 0))} | `{row.get('label', '')}` | {row.get('definition', '')} |"
        )
    lines.extend(
        [
            "",
            "## Comparison scopes",
            "",
        ]
    )
    for key, description in COMPARISON_SCOPES.items():
        available = payload.get("available_comparison_scopes", {}).get(key)
        flag = "available" if available else "not exported this run"
        lines.append(f"- **{key}** ({flag}): {description}")
    lines.extend(
        [
            "",
            "## Pattern claim boundary",
            "",
            payload.get("pattern_claim_boundary", PATTERN_CLAIM_BOUNDARY),
            "",
            "## Unsupported claims",
            "",
        ]
    )
    for item in payload.get("unsupported_claims", []):
        lines.append(f"- `{item}`")
    lines.append("")
    md_text = "\n".join(lines).strip() + "\n"
    md_path.write_text(md_text, encoding="utf-8")
    oh.mirror_utf8_text_run_then_global(
        diagnostics_dir=diagnostics_dir,
        run_filename=md_path.name,
        text=md_text,
        global_latest_name="permission_pattern_contract.latest.md",
    )
    return [str(json_path), str(md_path)]
