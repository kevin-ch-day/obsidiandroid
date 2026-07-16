"""Write the consolidated live backlog/debt operator summary export."""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.runtime_bootstrap  # noqa: F401

from obsidiandroid.common.backlog_semantics import build_backlog_markdown_lines
from obsidiandroid.diagnostics.backlog_triage_context import load_backlog_triage_context


OUTPUT_DIR = Path("output") / "diagnostics"
JSON_OUT = OUTPUT_DIR / "backlog_debt_operator_summary_latest.json"
MD_OUT = OUTPUT_DIR / "backlog_debt_operator_summary_latest.md"


def build_report(*, output_root: Path) -> dict[str, object]:
    """Build the consolidated operator backlog/debt summary payload."""
    context = load_backlog_triage_context(output_root=output_root)
    debt_summary = context.get("debt_summary", {})
    priority_backlog = context.get("priority_backlog", {})
    health = context.get("backlog_triage_health", {})
    readiness = context.get("readiness", {})
    return {
        "context": context,
        "payload": {
            "debt_summary": debt_summary,
            "priority_backlog": priority_backlog,
            "backlog_triage_health": health,
            "readiness_status": str((readiness or {}).get("status", "") or ""),
            "artifact_paths": {
                "android_missing_resolution": str(
                    output_root / "diagnostics" / "android_missing_resolution_triage_latest.csv"
                ),
                "missing_primary_label": str(
                    output_root / "diagnostics" / "missing_primary_label_triage_latest.csv"
                ),
                "missing_primary_authority_backfill_proposals": str(
                    output_root / "diagnostics" / "missing_primary_label_authority_backfill_proposals_latest.csv"
                ),
                "missing_primary_backfill_review_template": str(
                    output_root / "diagnostics" / "missing_primary_label_authority_backfill_review_template_latest.csv"
                ),
                "missing_primary_backfill_review_validation": str(
                    output_root / "diagnostics" / "missing_primary_label_authority_backfill_review_validation_latest.json"
                ),
                "blank_resolved_family": str(
                    output_root / "diagnostics" / "blank_resolved_family_triage_latest.csv"
                ),
                "policy_held_token_risk": str(
                    output_root / "diagnostics" / "android_policy_held_token_risk_latest.csv"
                ),
                "profile_family_mapping_debt_json": str(
                    output_root / "diagnostics" / "profile_family_mapping_debt_latest.json"
                ),
                "profile_family_mapping_debt_csv": str(
                    output_root / "diagnostics" / "profile_family_mapping_debt_latest.csv"
                ),
                "vt_false_positive_review": str(
                    output_root / "diagnostics" / "vt_false_positive_review_triage_latest.csv"
                ),
                "android_vt_tail_review": str(
                    output_root / "diagnostics" / "android_missing_resolution_vt_tail_latest.csv"
                ),
                "blank_resolved_singleton_provenance": str(
                    output_root / "diagnostics" / "blank_resolved_singleton_provenance_latest.csv"
                ),
                "blank_resolved_singleton_package_clusters": str(
                    output_root / "diagnostics" / "blank_resolved_singleton_package_clusters_latest.csv"
                ),
                "profile_policy_held_slug_worklist": str(
                    output_root / "diagnostics" / "profile_policy_held_slug_worklist_latest.csv"
                ),
                "operator_summary_json": str(
                    output_root / "diagnostics" / "backlog_debt_operator_summary_latest.json"
                ),
                "operator_summary_md": str(
                    output_root / "diagnostics" / "backlog_debt_operator_summary_latest.md"
                ),
            },
        },
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report(output_root=Path("output"))
    payload = report["payload"] if isinstance(report.get("payload"), dict) else {}
    debt_summary = payload.get("debt_summary", {}) if isinstance(payload, dict) else {}
    priority_backlog = payload.get("priority_backlog", {}) if isinstance(payload, dict) else {}
    health = payload.get("backlog_triage_health", {}) if isinstance(payload, dict) else {}

    JSON_OUT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    md_lines = ["# Live backlog / debt operator summary", ""]
    if isinstance(health, dict) and health.get("needs_refresh"):
        md_lines.append("- **Export health:** stale or mismatched triage export(s) detected.")
        md_lines.append(
            "- **Refresh exports:** "
            + ", ".join(str(key) for key in (health.get("refresh_exports", []) or []))
        )
        md_lines.append("")
    focus_structured = (
        debt_summary.get("focus_structured", {})
        if isinstance(debt_summary, dict) and isinstance(debt_summary.get("focus_structured"), dict)
        else {}
    )
    lane_counts = (
        focus_structured.get("lane_counts", {})
        if isinstance(focus_structured.get("lane_counts"), dict)
        else {}
    )
    if lane_counts:
        md_lines.append("## Lane focus")
        md_lines.append("")
        for lane, count in sorted(
            ((str(lane), int(count or 0)) for lane, count in lane_counts.items() if str(lane).strip()),
            key=lambda item: (-item[1], item[0]),
        ):
            md_lines.append(f"- {lane}: {count}")
        vt_tail_count = int(focus_structured.get("vt_tail_review_count", 0) or 0)
        vt_tail_export = str(focus_structured.get("vt_tail_export", "") or "").strip()
        if vt_tail_count > 0 and vt_tail_export:
            md_lines.append(f"- VT-tail drill-down export: `{vt_tail_export}` ({vt_tail_count} row(s))")
        lane_worklist_pattern = str(focus_structured.get("lane_worklist_export_pattern", "") or "").strip()
        if lane_worklist_pattern:
            md_lines.append(f"- Per-lane worklists: `{lane_worklist_pattern}`")
        singleton_count = int(focus_structured.get("singleton_provenance_count", 0) or 0)
        singleton_export = str(focus_structured.get("singleton_export", "") or "").strip()
        singleton_cluster_export = str(focus_structured.get("singleton_cluster_export", "") or "").strip()
        if singleton_count > 0 and singleton_export:
            md_lines.append(f"- Singleton provenance drill-down: `{singleton_export}` ({singleton_count} row(s))")
        if singleton_count > 0 and singleton_cluster_export:
            md_lines.append(f"- Singleton package clusters: `{singleton_cluster_export}`")
        md_lines.append("")
    md_lines.extend(
        build_backlog_markdown_lines(
            debt_summary=debt_summary if isinstance(debt_summary, dict) else {},
            priority_backlog=priority_backlog if isinstance(priority_backlog, dict) else {},
            heading="## Backlog and operator queues",
            ranked_style="table",
            max_rows=8,
            android_path=(payload.get("artifact_paths", {}) or {}).get("android_missing_resolution")
            if isinstance(payload.get("artifact_paths"), dict)
            else None,
            missing_primary_path=(payload.get("artifact_paths", {}) or {}).get("missing_primary_label")
            if isinstance(payload.get("artifact_paths"), dict)
            else None,
            policy_held_path=(payload.get("artifact_paths", {}) or {}).get("policy_held_token_risk")
            if isinstance(payload.get("artifact_paths"), dict)
            else None,
        )
    )
    MD_OUT.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    focus_label = str((debt_summary or {}).get("focus_label", "") or "—")
    focus_count = int((debt_summary or {}).get("focus_count", 0) or 0)
    print(f"[EXPORT] Backlog debt operator summary JSON: {JSON_OUT.as_posix()}")
    print(f"[EXPORT] Backlog debt operator summary MD: {MD_OUT.as_posix()}")
    print(f"Focus: {focus_label} ({focus_count} row(s))")
    print(f"Needs refresh: {bool((health or {}).get('needs_refresh'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
