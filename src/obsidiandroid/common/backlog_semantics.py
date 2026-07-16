"""Shared backlog/debt semantics across operator surfaces."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

import pandas as pd

from obsidiandroid.common.authority_taxonomy_terms import (
    ANDROID_MISSING_RESOLUTION_BACKLOG_LABEL,
    FAMILY_TYPE_CONFLICT_BACKLOG_LABEL,
    POLICY_HELD_FAMILY_NOISE_LABEL,
    PROFILE_FAMILY_MAPPING_DEBT_LABEL,
    TRUE_UNRESOLVED_FAMILY_DEBT_LABEL,
    VT_FALSE_POSITIVE_REVIEW_RESIDUE_LABEL,
    taxonomy_curation_discipline_note,
)
from obsidiandroid.common.json_io import read_json_dict
from obsidiandroid.common.cohort_methodology import safe_int


BACKLOG_ROW_ANDROID_MISSING_RESOLUTION = "android_missing_resolution"
BACKLOG_ROW_VT_FALSE_POSITIVE = "vt_false_positive_review"
BACKLOG_ROW_MISSING_PRIMARY_LABELS = "missing_primary_labels"
BACKLOG_ROW_TRUE_UNRESOLVED_FAMILY = "true_unresolved_family"
BACKLOG_ROW_POLICY_HELD_FAMILY = "policy_held_family"
BACKLOG_ROW_FAMILY_TYPE_CONFLICT = "family_type_conflict"
BACKLOG_ROW_BLANK_RESOLVED_FAMILY = "blank_resolved_family"

# These lanes have an authority-derived primary-label target and can be worked
# as a bounded review/backfill queue.  All other residual lanes remain
# provenance, policy, or manual-candidate work; their volume must not drown
# out closure-ready work in the operator priority surface.
MISSING_PRIMARY_CLOSURE_READY_LANES: frozenset[str] = frozenset(
    {
        "authority_backed_primary_backfill_review",
        # Kept only to classify older exports until the schema guard requests a
        # refresh.  The current query emits the authority_backed name above.
        "high_strong_primary_backfill_review",
    }
)
MISSING_PRIMARY_REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {
        "sample_id",
        "authority_bucket",
        "resolved_family_lc",
        "authority_family_slug",
        "authority_type_slug",
        "authority_parent_type_slug",
        "proposed_classification_primary",
        "confidence_bucket",
        "residual_lane",
        "recommended_triage_action",
    }
)

_RUN_BACKLOG_LABELS = (
    "Missing primary labels",
    TRUE_UNRESOLVED_FAMILY_DEBT_LABEL,
    POLICY_HELD_FAMILY_NOISE_LABEL,
    ANDROID_MISSING_RESOLUTION_BACKLOG_LABEL,
    VT_FALSE_POSITIVE_REVIEW_RESIDUE_LABEL,
    FAMILY_TYPE_CONFLICT_BACKLOG_LABEL,
)


def file_freshness_label(path: Path) -> str:
    """Classify an export file by mtime recency."""
    if not path.is_file():
        return "missing"
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return "unknown"
    age_hours = max(0.0, (datetime.now(timezone.utc) - modified).total_seconds() / 3600.0)
    if age_hours <= 24.0:
        return "current"
    if age_hours <= 72.0:
        return "aging"
    return "stale"


def _count_map(df: pd.DataFrame, column: str) -> dict[str, int]:
    if column not in df.columns:
        return {}
    counts: dict[str, int] = {}
    for raw in df[column].fillna("").astype(str):
        value = str(raw).strip()
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


def _count_map_masked(df: pd.DataFrame, column: str, mask: pd.Series) -> dict[str, int]:
    """Count non-empty values in ``column`` for the masked subset."""
    if column not in df.columns or not isinstance(mask, pd.Series):
        return {}
    try:
        work = df.loc[mask.fillna(False)]
    except Exception:
        return {}
    return _count_map(work, column)


def _top_bucket(counts: dict[str, int] | object) -> tuple[str, int] | None:
    if not isinstance(counts, dict) or not counts:
        return None
    items = sorted(
        ((str(k), safe_int(v, 0)) for k, v in counts.items() if str(k).strip()),
        key=lambda item: -item[1],
    )
    return items[0] if items else None


def _missing_primary_lane_rows(taxonomy: dict[str, object]) -> list[dict[str, object]]:
    rows = taxonomy.get("top_missing_primary_label_lanes", [])
    if isinstance(rows, list) and rows:
        out: list[dict[str, object]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            lane = str(row.get("lane", "") or "").strip()
            count = safe_int(row.get("sample_count", 0), 0)
            if lane and count > 0:
                out.append({"lane": lane, "sample_count": count})
        if out:
            return out
    counts = taxonomy.get("missing_primary_label_lane_counts", {})
    if not isinstance(counts, dict):
        return []
    return [
        {"lane": lane, "sample_count": count}
        for lane, count in sorted(
            (
                (str(lane), safe_int(count, 0))
                for lane, count in counts.items()
                if str(lane).strip() and safe_int(count, 0) > 0
            ),
            key=lambda item: (-item[1], item[0]),
        )
    ]


def _format_missing_primary_lane_split(rows: list[dict[str, object]], *, limit: int = 4) -> str:
    parts = [
        f"{str(row.get('lane', '') or '')}={safe_int(row.get('sample_count', 0), 0)}"
        for row in rows[:limit]
        if str(row.get("lane", "") or "").strip()
    ]
    return ", ".join(parts)


def _missing_primary_action(
    taxonomy: dict[str, object],
    *,
    missing_primary_triage: dict[str, object] | None = None,
) -> str:
    triage = missing_primary_triage if isinstance(missing_primary_triage, dict) else {}
    freshness = str(triage.get("freshness", "") or "").strip()
    if str(triage.get("schema_status", "") or "").strip() == "incompatible":
        return "Refresh the missing-primary label triage export; its schema is older than the authority-backed backfill contract."
    if freshness == "stale":
        return "Refresh the missing-primary label triage export first."
    closure_ready = safe_int(triage.get("closure_ready_row_count", 0), 0)
    if closure_ready > 0:
        return (
            "Open the authority-backed missing-primary backfill proposals first; "
            "review and close that bounded queue before provenance/policy lanes."
        )
    if safe_int(triage.get("row_count", 0), 0) > 0:
        return "Open the missing-primary label triage export; the remaining rows are provenance/policy/manual review, not automatic backfill candidates."
    if safe_int(taxonomy.get("missing_primary_label_actionable_samples", 0), 0) > 0:
        return "Work high/strong missing-primary label-review rows first."
    if taxonomy.get("missing_primary_label_active_residual_samples") is not None:
        return "Open active residual worklist; suppressed/provenance rows are already closed from label-backfill work."
    if taxonomy.get("missing_primary_label_residual_samples") is not None:
        return "Open residual triage; remaining missing-primary rows are provenance/suppression/manual-review debt."
    return "Open profile readiness mapping inventory and inspect missing-primary-label debt."


def _missing_primary_detail(taxonomy: dict[str, object]) -> str:
    if taxonomy.get("missing_primary_label_active_residual_samples") is not None:
        return (
            "Active/actionable Android + PI missing-primary debt"
            f"; raw_missing={safe_int(taxonomy.get('missing_primary_label_raw_samples', 0), 0)}"
            f"; actionable={safe_int(taxonomy.get('missing_primary_label_actionable_samples', 0), 0)}"
            f"; suppressed={safe_int(taxonomy.get('missing_primary_label_suppressed_samples', 0), 0)}"
            f"; active_residual={safe_int(taxonomy.get('missing_primary_label_active_residual_samples', 0), 0)}."
        )
    if (
        taxonomy.get("missing_primary_label_actionable_samples") is not None
        or taxonomy.get("missing_primary_label_residual_samples") is not None
    ):
        return (
            "Active/actionable Android + PI missing-primary debt"
            f"; raw_missing={safe_int(taxonomy.get('missing_primary_label_raw_samples', 0), 0)}"
            f"; actionable={safe_int(taxonomy.get('missing_primary_label_actionable_samples', 0), 0)}"
            f"; residual={safe_int(taxonomy.get('missing_primary_label_residual_samples', 0), 0)}."
        )
    return "Android + PI-observed rows missing classification_primary."


def _policy_held_family_detail(taxonomy: dict[str, object]) -> str:
    """Summarize policy-held token residue without implying family authority debt."""
    unresolved_count = safe_int(taxonomy.get("unresolved_family_count", 0), 0)
    counts = taxonomy.get("policy_held_family_token_kind_counts", {})
    if not isinstance(counts, dict) or not counts:
        prefix = (
            "No true unresolved family debt in this slice; remaining resolved-family rows are intentionally held "
            "by generic/coarse token policy."
            if unresolved_count == 0
            else "Resolved-family rows intentionally held by generic/coarse token policy."
        )
        return prefix
    parts = [
        f"{str(token_kind)}={safe_int(count, 0)}"
        for token_kind, count in sorted(
            counts.items(),
            key=lambda item: (-safe_int(item[1], 0), str(item[0])),
        )
        if str(token_kind).strip() and safe_int(count, 0) > 0
    ]
    if not parts:
        return "Resolved-family rows intentionally held by generic/coarse token policy."
    prefix = (
        "No true unresolved family debt in this slice; remaining resolved-family rows are intentionally held by generic/coarse token policy"
        if unresolved_count == 0
        else "Resolved-family rows intentionally held by generic/coarse token policy"
    )
    return f"{prefix}; token_classes={', '.join(parts[:6])}."


def _policy_held_family_action(policy_held_triage: dict[str, object] | None) -> str:
    """Choose the next action for policy-held family noise."""
    triage = policy_held_triage if isinstance(policy_held_triage, dict) else {}
    freshness = str(triage.get("freshness", "") or "").strip()
    if freshness == "stale":
        return "Refresh the policy-held token risk export before auditing generic/coarse token policy."
    if safe_int(triage.get("high_or_strong_row_count", 0), 0) > 0:
        return "Open the policy-held token risk export and review the dominant high/strong hold lane plus token/package cluster before creating more family authority rows."
    if safe_int(triage.get("row_count", 0), 0) > 0:
        return "Open the policy-held token risk export and audit the dominant hold lane plus token/package cluster before creating more family authority rows."
    return "Audit generic/coarse token policy before creating more family authority rows."


def _family_type_conflict_detail(taxonomy: dict[str, object]) -> str:
    """Summarize actionable family/type conflict candidates."""
    posture = build_taxonomy_curation_posture(readiness={"taxonomy_signals": taxonomy})
    detail = str(posture.get("note", "") or "").strip()
    top_conflicts = taxonomy.get("top_family_type_conflicts", [])
    bits: list[str] = []
    if isinstance(top_conflicts, list):
        for entry in top_conflicts[:5]:
            if not isinstance(entry, dict):
                continue
            family = str(entry.get("family", "") or "").strip()
            db_type = str(entry.get("db_type_slug", "") or "").strip()
            semantic = str(entry.get("dominant_label_semantic", "") or "").strip()
            samples = safe_int(entry.get("sample_count", 0), 0)
            action = str(entry.get("suggested_action", "") or "").strip()
            if not family:
                continue
            rhs = semantic or "<none>"
            lhs = db_type or "<unmapped>"
            suffix = f", action={action}" if action else ""
            bits.append(f"{family}({lhs}->{rhs}, n={samples}{suffix})")
    if bits:
        extra = f" top_candidates={'; '.join(bits)}."
        return f"{detail} {extra}".strip() if detail else f"top_candidates={'; '.join(bits)}."
    return detail or "Rows where DB type, label semantics, or authority mapping still disagree."


def read_profile_family_mapping_debt_snapshot(*, output_root: Path) -> dict[str, object]:
    """Load the latest profile family-mapping debt summary export."""
    path = output_root / "diagnostics" / "profile_family_mapping_debt_latest.json"
    if not path.is_file():
        return {}
    payload = read_json_dict(path)
    profiles = payload.get("profiles", [])
    if not isinstance(profiles, list):
        return {}
    allcurrent = next(
        (
            row
            for row in profiles
            if isinstance(row, dict) and str(row.get("profile_id", "") or "") == "android_malware_all_current"
        ),
        None,
    )
    focus = allcurrent if isinstance(allcurrent, dict) else (profiles[0] if profiles else {})
    if not isinstance(focus, dict):
        return {}
    return {
        "path": path,
        "freshness": file_freshness_label(path),
        "profile_id": str(focus.get("profile_id", "") or ""),
        "governed_sql_rows": safe_int(focus.get("governed_sql_rows", 0), 0),
        "excluded_unmapped_family_rows": safe_int(focus.get("excluded_unmapped_family_rows", 0), 0),
        "blank_resolved_slug_rows": safe_int(focus.get("blank_resolved_slug_rows", 0), 0),
        "policy_held_resolved_slug_rows": safe_int(focus.get("policy_held_resolved_slug_rows", 0), 0),
        "true_unmapped_resolved_slug_rows": safe_int(focus.get("true_unmapped_resolved_slug_rows", 0), 0),
        "profiles": profiles,
    }


def _android_missing_resolution_action(
    *,
    android_missing_triage: dict[str, object],
    taxonomy: dict[str, object],
) -> str:
    triage = android_missing_triage if isinstance(android_missing_triage, dict) else {}
    freshness = str(triage.get("freshness", "") or "").strip()
    row_count = safe_int(triage.get("row_count", 0), 0)
    blank_resolved = safe_int(taxonomy.get("blank_resolved_family_samples", 0), 0)
    if freshness == "stale":
        return "Refresh the Android missing-resolution triage export first."
    if row_count <= 0 and blank_resolved > 0:
        return (
            "Refresh the Android missing-resolution triage export first; "
            "live blank-resolved family debt exists."
        )
    return "Open Android missing-resolution triage and work the dominant package/lane cluster."


def _android_missing_resolution_detail(
    *,
    android_missing_triage: dict[str, object],
    taxonomy: dict[str, object],
) -> str:
    triage = android_missing_triage if isinstance(android_missing_triage, dict) else {}
    blank_resolved = safe_int(taxonomy.get("blank_resolved_family_samples", 0), 0)
    parts = [
        f"freshness={str(triage.get('freshness', '') or '').strip() or 'unknown'}",
        f"top_lane={str(triage.get('top_lane', '') or '').strip() or 'none'}",
    ]
    if blank_resolved > 0:
        parts.append(f"live_blank_resolved={blank_resolved}")
    return "; ".join(parts) + "."


def _profile_family_mapping_detail(snapshot: dict[str, object] | None) -> str:
    triage = snapshot if isinstance(snapshot, dict) else {}
    if not triage:
        return ""
    return (
        f"allcurrent governed_sql={safe_int(triage.get('governed_sql_rows', 0), 0)}; "
        f"excluded_unmapped={safe_int(triage.get('excluded_unmapped_family_rows', 0), 0)} "
        f"(blank_resolved={safe_int(triage.get('blank_resolved_slug_rows', 0), 0)}, "
        f"policy_held={safe_int(triage.get('policy_held_resolved_slug_rows', 0), 0)}, "
        f"true_unmapped={safe_int(triage.get('true_unmapped_resolved_slug_rows', 0), 0)}); "
        f"freshness={str(triage.get('freshness', '') or '').strip() or 'unknown'}."
    )


def _augment_missing_primary_detail(
    detail: str,
    missing_primary_triage: dict[str, object] | None,
) -> str:
    """Append live missing-primary triage context to the generic summary detail."""
    triage = missing_primary_triage if isinstance(missing_primary_triage, dict) else {}
    suffix: list[str] = []
    schema_status = str(triage.get("schema_status", "") or "").strip()
    if schema_status and schema_status != "compatible":
        missing_columns = triage.get("missing_required_columns", [])
        missing_text = ",".join(str(value) for value in missing_columns[:3]) if isinstance(missing_columns, list) else ""
        suffix.append(f"schema={schema_status}" + (f" ({missing_text})" if missing_text else ""))
    closure_ready = safe_int(triage.get("closure_ready_row_count", 0), 0)
    if closure_ready > 0:
        suffix.append(f"closure_ready={closure_ready}")
    proposal_status = str(triage.get("proposal_status", "") or "").strip()
    if proposal_status:
        proposal_groups = safe_int(triage.get("proposal_group_count", 0), 0)
        proposal_samples = safe_int(triage.get("proposal_sample_count", 0), 0)
        suffix.append(
            f"proposals={proposal_status}"
            + (f" ({proposal_groups} groups/{proposal_samples} samples)" if proposal_status == "available" else "")
        )
    top_lane = str(triage.get("top_lane", "") or "").strip()
    top_lane_count = safe_int(triage.get("top_lane_count", 0), 0)
    if top_lane and top_lane_count > 0:
        suffix.append(f"top_lane={top_lane} ({top_lane_count})")
    freshness = str(triage.get("freshness", "") or "").strip()
    if freshness:
        suffix.append(f"freshness={freshness}")
    if not suffix:
        return detail
    return f"{detail} {'; '.join(suffix)}."


def _augment_policy_held_family_detail(
    detail: str,
    policy_held_triage: dict[str, object] | None,
) -> str:
    """Append live policy-held triage context to the generic summary detail."""
    triage = policy_held_triage if isinstance(policy_held_triage, dict) else {}
    suffix: list[str] = []
    top_lane = str(triage.get("top_lane", "") or "").strip()
    top_lane_count = safe_int(triage.get("top_lane_count", 0), 0)
    if top_lane and top_lane_count > 0:
        suffix.append(f"top_lane={top_lane} ({top_lane_count})")
    top_token_kind = str(triage.get("top_token_kind", "") or "").strip()
    top_token_kind_count = safe_int(triage.get("top_token_kind_count", 0), 0)
    if top_token_kind and top_token_kind_count > 0:
        suffix.append(f"top_token_kind={top_token_kind} ({top_token_kind_count})")
    top_policy_held_token = str(triage.get("top_policy_held_token", "") or "").strip()
    top_policy_held_token_count = safe_int(triage.get("top_policy_held_token_count", 0), 0)
    if top_policy_held_token and top_policy_held_token_count > 0:
        suffix.append(f"top_token={top_policy_held_token} ({top_policy_held_token_count})")
    top_android_package_name = str(triage.get("top_android_package_name", "") or "").strip()
    top_android_package_name_count = safe_int(triage.get("top_android_package_name_count", 0), 0)
    if top_android_package_name and top_android_package_name != "<blank>" and top_android_package_name_count > 0:
        suffix.append(f"top_package={top_android_package_name} ({top_android_package_name_count})")
    high_or_strong_row_count = safe_int(triage.get("high_or_strong_row_count", 0), 0)
    if high_or_strong_row_count > 0:
        suffix.append(f"high_or_strong={high_or_strong_row_count}")
    top_high_token = str(triage.get("top_high_or_strong_policy_held_token", "") or "").strip()
    top_high_token_count = safe_int(triage.get("top_high_or_strong_policy_held_token_count", 0), 0)
    if top_high_token and top_high_token_count > 0:
        suffix.append(f"top_high_token={top_high_token} ({top_high_token_count})")
    top_high_package = str(triage.get("top_high_or_strong_android_package_name", "") or "").strip()
    top_high_package_count = safe_int(triage.get("top_high_or_strong_android_package_name_count", 0), 0)
    if top_high_package and top_high_package != "<blank>" and top_high_package_count > 0:
        suffix.append(f"top_high_package={top_high_package} ({top_high_package_count})")
    freshness = str(triage.get("freshness", "") or "").strip()
    if freshness:
        suffix.append(f"freshness={freshness}")
    if not suffix:
        return detail
    return f"{detail} {'; '.join(suffix)}."


def _top_bucket_with_priority(
    counts: dict[str, int] | object,
    *,
    priority_order: tuple[str, ...],
) -> tuple[str, int] | None:
    if not isinstance(counts, dict) or not counts:
        return None
    priority_rank = {name: idx for idx, name in enumerate(priority_order)}
    items = sorted(
        ((str(k), safe_int(v, 0)) for k, v in counts.items() if str(k).strip()),
        key=lambda item: (-item[1], priority_rank.get(item[0], len(priority_rank)), item[0]),
    )
    return items[0] if items else None


def read_triage_snapshot(
    *,
    path: Path,
    lane_column: str,
    action_column: str,
    extra_count_columns: dict[str, str] | None = None,
    required_columns: frozenset[str] | None = None,
) -> dict[str, object]:
    """Read a triage CSV export into a shared operator snapshot shape."""
    if not path.is_file():
        return {}
    try:
        df = pd.read_csv(path)
    except Exception:
        return {}
    available_columns = {str(column).strip() for column in df.columns}
    missing_columns = sorted(set(required_columns or frozenset()) - available_columns)
    schema_status = "compatible" if not missing_columns else "incompatible"
    if df.empty:
        snapshot: dict[str, object] = {
            "path": path,
            "row_count": 0,
            "lane_counts": {},
            "action_counts": {},
            "freshness": file_freshness_label(path),
        }
    else:
        snapshot = {
            "path": path,
            "row_count": int(len(df)),
            "lane_counts": _count_map(df, lane_column),
            "action_counts": _count_map(df, action_column),
            "freshness": file_freshness_label(path),
        }
    snapshot["schema_status"] = schema_status
    snapshot["missing_required_columns"] = missing_columns
    for key, column in (extra_count_columns or {}).items():
        snapshot[key] = _count_map(df, column) if not df.empty else {}
    top_lane = _top_bucket(snapshot.get("lane_counts"))
    if top_lane is not None:
        snapshot["top_lane"] = top_lane[0]
        snapshot["top_lane_count"] = top_lane[1]
    else:
        snapshot["top_lane"] = ""
        snapshot["top_lane_count"] = 0
    return snapshot


def read_false_positive_triage_snapshot(*, output_root: Path) -> dict[str, object]:
    """Load the latest suppression-aware false-positive triage export."""
    return read_triage_snapshot(
        path=output_root / "diagnostics" / "vt_false_positive_review_triage_latest.csv",
        lane_column="review_lane",
        action_column="recommended_triage_action",
        extra_count_columns={"global_policy_counts": "global_policy_bucket"},
    )


def read_android_missing_resolution_snapshot(*, output_root: Path) -> dict[str, object]:
    """Load the latest Android missing-resolution triage export."""
    snapshot = read_triage_snapshot(
        path=output_root / "diagnostics" / "android_missing_resolution_triage_latest.csv",
        lane_column="review_lane",
        action_column="recommended_action",
        extra_count_columns={"cluster_counts": "package_cluster_key"},
    )
    top_lane = _top_bucket_with_priority(
        snapshot.get("lane_counts"),
        priority_order=(
            "blank_package_review",
            "package_cluster_review",
            "singleton_package_review",
            "vt_tail_review",
        ),
    )
    if top_lane is not None:
        snapshot["top_lane"] = top_lane[0]
        snapshot["top_lane_count"] = top_lane[1]
    return snapshot


def read_blank_resolved_triage_snapshot(*, output_root: Path) -> dict[str, object]:
    """Load the latest blank-resolved family triage export."""
    return read_triage_snapshot(
        path=output_root / "diagnostics" / "blank_resolved_family_triage_latest.csv",
        lane_column="review_lane",
        action_column="recommended_triage_action",
        extra_count_columns={"authority_bucket_counts": "authority_bucket"},
    )


def read_missing_primary_triage_snapshot(*, output_root: Path) -> dict[str, object]:
    """Load the latest missing-primary label triage export."""
    snapshot = read_triage_snapshot(
        path=output_root / "diagnostics" / "missing_primary_label_triage_latest.csv",
        lane_column="residual_lane",
        action_column="recommended_triage_action",
        extra_count_columns={
            "authority_bucket_counts": "authority_bucket",
            "confidence_bucket_counts": "confidence_bucket",
        },
        required_columns=MISSING_PRIMARY_REQUIRED_COLUMNS,
    )
    lane_counts = snapshot.get("lane_counts", {})
    if not isinstance(lane_counts, dict):
        lane_counts = {}
    closure_ready_count = sum(
        safe_int(lane_counts.get(lane, 0), 0)
        for lane in MISSING_PRIMARY_CLOSURE_READY_LANES
    )
    snapshot["closure_ready_row_count"] = closure_ready_count
    snapshot["closure_ready_lane_counts"] = {
        lane: safe_int(lane_counts.get(lane, 0), 0)
        for lane in sorted(MISSING_PRIMARY_CLOSURE_READY_LANES)
        if safe_int(lane_counts.get(lane, 0), 0) > 0
    }
    residual_count = safe_int(snapshot.get("row_count", 0), 0)
    snapshot["non_closure_ready_row_count"] = max(residual_count - closure_ready_count, 0)
    proposal_path = output_root / "diagnostics" / "missing_primary_label_authority_backfill_proposals_latest.csv"
    snapshot["proposal_path"] = proposal_path
    snapshot["proposal_status"] = "missing"
    snapshot["proposal_group_count"] = 0
    snapshot["proposal_sample_count"] = 0
    if proposal_path.is_file():
        try:
            proposals = pd.read_csv(proposal_path)
        except Exception:
            proposals = pd.DataFrame()
        snapshot["proposal_status"] = "available"
        snapshot["proposal_group_count"] = int(len(proposals))
        if "sample_count" in proposals.columns:
            snapshot["proposal_sample_count"] = safe_int(
                pd.to_numeric(proposals["sample_count"], errors="coerce").fillna(0).sum(),
                0,
            )
    summary_path = output_root / "diagnostics" / "missing_primary_label_triage_summary_latest.json"
    snapshot["summary_path"] = summary_path
    if summary_path.is_file():
        summary_payload = read_json_dict(summary_path)
        snapshot["summary_schema_version"] = safe_int(summary_payload.get("schema_version", 0), 0)
    else:
        snapshot["summary_schema_version"] = 0
    return snapshot


def read_policy_held_token_risk_snapshot(*, output_root: Path) -> dict[str, object]:
    """Load the latest policy-held family-token risk export."""
    snapshot = read_triage_snapshot(
        path=output_root / "diagnostics" / "android_policy_held_token_risk_latest.csv",
        lane_column="policy_hold_lane",
        action_column="recommended_next_action",
        extra_count_columns={
            "token_kind_counts": "token_kind",
            "policy_held_token_counts": "policy_held_token",
            "android_package_name_counts": "android_package_name",
        },
    )
    token_kind = _top_bucket(snapshot.get("token_kind_counts"))
    if token_kind is not None:
        snapshot["top_token_kind"] = token_kind[0]
        snapshot["top_token_kind_count"] = token_kind[1]
    else:
        snapshot["top_token_kind"] = ""
        snapshot["top_token_kind_count"] = 0
    held_token = _top_bucket(snapshot.get("policy_held_token_counts"))
    if held_token is not None:
        snapshot["top_policy_held_token"] = held_token[0]
        snapshot["top_policy_held_token_count"] = held_token[1]
    else:
        snapshot["top_policy_held_token"] = ""
        snapshot["top_policy_held_token_count"] = 0
    package_name = _top_bucket(snapshot.get("android_package_name_counts"))
    if package_name is not None:
        snapshot["top_android_package_name"] = package_name[0]
        snapshot["top_android_package_name_count"] = package_name[1]
    else:
        snapshot["top_android_package_name"] = ""
        snapshot["top_android_package_name_count"] = 0
    path = snapshot.get("path")
    if isinstance(path, Path) and path.is_file():
        try:
            df = pd.read_csv(path)
        except Exception:
            df = pd.DataFrame()
        if not df.empty and "confidence_bucket" in df.columns:
            high_mask = df["confidence_bucket"].fillna("").astype(str).str.strip().isin(["high", "strong"])
            snapshot["high_or_strong_row_count"] = safe_int(high_mask.sum(), 0)
            high_token = _top_bucket(_count_map_masked(df, "policy_held_token", high_mask))
            if high_token is not None:
                snapshot["top_high_or_strong_policy_held_token"] = high_token[0]
                snapshot["top_high_or_strong_policy_held_token_count"] = high_token[1]
            else:
                snapshot["top_high_or_strong_policy_held_token"] = ""
                snapshot["top_high_or_strong_policy_held_token_count"] = 0
            high_package = _top_bucket(_count_map_masked(df, "android_package_name", high_mask))
            if high_package is not None:
                snapshot["top_high_or_strong_android_package_name"] = high_package[0]
                snapshot["top_high_or_strong_android_package_name_count"] = high_package[1]
            else:
                snapshot["top_high_or_strong_android_package_name"] = ""
                snapshot["top_high_or_strong_android_package_name_count"] = 0
        else:
            snapshot["high_or_strong_row_count"] = 0
            snapshot["top_high_or_strong_policy_held_token"] = ""
            snapshot["top_high_or_strong_policy_held_token_count"] = 0
            snapshot["top_high_or_strong_android_package_name"] = ""
            snapshot["top_high_or_strong_android_package_name_count"] = 0
    return snapshot


def triage_status(*, row_count: int | None, freshness: str) -> str:
    """Return traffic-light status for a triage export."""
    if row_count is None:
        return "YELLOW"
    if freshness == "stale":
        return "RED"
    if freshness in {"aging", "unknown"}:
        return "YELLOW"
    return "YELLOW" if row_count > 0 else "GREEN"


def triage_detail(
    row_count: int | None,
    *,
    noun: str,
    top_bucket: tuple[str, int] | None = None,
    freshness: str | None = None,
) -> str:
    """Render a compact operator-facing triage detail."""
    if row_count is None:
        return "report missing"
    detail = f"{row_count} {noun}"
    if top_bucket is not None:
        name, count = top_bucket
        detail += f"; top={name} ({count})"
    if freshness:
        detail += f"; freshness={freshness}"
    return detail


def assess_backlog_triage_health(
    *,
    readiness: dict[str, object] | None = None,
    android_missing_triage: dict[str, object],
    fp_triage: dict[str, object],
    missing_primary_triage: dict[str, object] | None = None,
    policy_held_triage: dict[str, object] | None = None,
    profile_mapping_debt: dict[str, object] | None = None,
    blank_resolved_triage: dict[str, object] | None = None,
) -> dict[str, object]:
    """Classify stale or mismatched backlog triage exports for selective refresh."""
    taxonomy = readiness.get("taxonomy_signals", {}) if isinstance(readiness, dict) else {}
    if not isinstance(taxonomy, dict):
        taxonomy = {}
    blank_live = safe_int(taxonomy.get("blank_resolved_family_samples", 0), 0)
    missing_active = safe_int(taxonomy.get("missing_primary_label_active_residual_samples", 0), 0)
    policy_live = safe_int(taxonomy.get("policy_held_family_samples", 0), 0)

    def _append_issue(
        issues: list[dict[str, object]],
        *,
        code: str,
        export_key: str,
        detail: str,
    ) -> None:
        issues.append(
            {
                "code": code,
                "export_key": export_key,
                "detail": detail,
            }
        )

    issues: list[dict[str, object]] = []
    checks: list[tuple[str, dict[str, object] | None, int | None]] = [
        ("android_missing_resolution", android_missing_triage, blank_live),
        ("missing_primary_label", missing_primary_triage, missing_active),
        ("vt_false_positive_review", fp_triage, None),
        ("policy_held_token_risk", policy_held_triage, policy_live),
        ("profile_family_mapping_debt", profile_mapping_debt, None),
        ("blank_resolved_family", blank_resolved_triage, blank_live),
    ]
    for export_key, payload, live_count in checks:
        triage = payload if isinstance(payload, dict) else {}
        freshness = str(triage.get("freshness", "") or "").strip() or "missing"
        row_count = safe_int(triage.get("row_count", 0), 0)
        if freshness in {"stale", "missing"}:
            _append_issue(
                issues,
                code=f"{export_key}_stale",
                export_key=export_key,
                detail=f"{export_key} export freshness={freshness}.",
            )
        if str(triage.get("schema_status", "") or "").strip() == "incompatible":
            missing_columns = triage.get("missing_required_columns", [])
            detail = f"{export_key} export schema is incompatible"
            if isinstance(missing_columns, list) and missing_columns:
                detail += "; missing=" + ",".join(str(value) for value in missing_columns[:5])
            _append_issue(
                issues,
                code=f"{export_key}_schema_incompatible",
                export_key=export_key,
                detail=detail + ".",
            )
        if export_key == "missing_primary_label" and str(triage.get("proposal_status", "") or "") != "available":
            _append_issue(
                issues,
                code="missing_primary_label_proposal_missing",
                export_key=export_key,
                detail="missing-primary authority-backed proposal export is missing.",
            )
        if live_count is not None and live_count > 0 and row_count <= 0 and freshness != "missing":
            _append_issue(
                issues,
                code=f"{export_key}_empty_mismatch",
                export_key=export_key,
                detail=f"{export_key} export has 0 rows while live debt={live_count}.",
            )
    if blank_live > 0 and safe_int((android_missing_triage or {}).get("row_count", 0), 0) <= 0:
        if not any(issue.get("export_key") == "android_missing_resolution" for issue in issues):
            _append_issue(
                issues,
                code="android_missing_resolution_empty_mismatch",
                export_key="android_missing_resolution",
                detail=(
                    f"android_missing_resolution export has 0 rows while live blank_resolved={blank_live}."
                ),
            )
    refresh_exports = sorted({str(issue.get("export_key", "") or "") for issue in issues if issue.get("export_key")})
    return {
        "issues": issues,
        "needs_refresh": bool(issues),
        "refresh_exports": refresh_exports,
    }


def choose_priority_triage(
    *,
    android_missing_triage: dict[str, object],
    fp_triage: dict[str, object],
    missing_primary_triage: dict[str, object] | None = None,
) -> dict[str, str | int]:
    """Choose the first triage queue the operator should open."""
    candidates: list[dict[str, str | int]] = []
    for label, payload, action in (
        (
            "Android missing-resolution triage",
            android_missing_triage,
            "Open Android missing-resolution triage first.",
        ),
        (
            "Missing-primary label triage",
            missing_primary_triage or {},
            "Open missing-primary label triage first.",
        ),
        (
            "VT false-positive triage",
            fp_triage,
            "Open VT false-positive triage first.",
        ),
    ):
        if not isinstance(payload, dict) or not payload:
            continue
        freshness = str(payload.get("freshness", "") or "").strip()
        row_count = safe_int(payload.get("row_count", 0), 0)
        top_lane = str(payload.get("top_lane", "") or "").strip()
        top_lane_count = safe_int(payload.get("top_lane_count", 0), 0)
        if label == "Missing-primary label triage":
            if str(payload.get("schema_status", "") or "").strip() == "incompatible":
                action = "Refresh missing-primary triage: the current export predates the authority-backed backfill schema."
            elif str(payload.get("proposal_status", "") or "") != "available":
                action = "Refresh missing-primary triage: the authority-backed proposal export is missing."
            else:
                closure_ready = safe_int(payload.get("closure_ready_row_count", 0), 0)
                if closure_ready <= 0:
                    # Residual provenance/policy work remains visible in the
                    # debt ledger, but it should not eclipse a bounded queue
                    # that can actually close primary-label debt.
                    continue
                label = "Authority-backed primary backfill review"
                row_count = closure_ready
                closure_lanes = payload.get("closure_ready_lane_counts", {})
                if isinstance(closure_lanes, dict) and closure_lanes:
                    top_lane, top_lane_count = _top_bucket(closure_lanes) or ("", 0)
                action = "Open authority-backed primary backfill proposals first; review before applying any catalog update."
        if row_count <= 0 and freshness == "current":
            continue
        if freshness == "stale":
            action = f"Refresh {label.lower()} export first, then reopen it."
        candidates.append(
            {
                "label": label,
                "row_count": row_count,
                "freshness": freshness,
                "top_lane": top_lane,
                "top_lane_count": top_lane_count,
                "action": action,
            }
        )
    if not candidates:
        return {}
    freshness_rank = {"current": 0, "aging": 1, "unknown": 2, "stale": 3, "missing": 4}
    candidates.sort(
        key=lambda item: (
            -safe_int(item.get("row_count", 0), 0),
            freshness_rank.get(str(item.get("freshness", "")), 5),
            -safe_int(item.get("top_lane_count", 0), 0),
            str(item.get("label", "")),
        )
    )
    return candidates[0]


def build_taxonomy_curation_posture(*, readiness: dict[str, object]) -> dict[str, object]:
    """Build one normalized taxonomy-curation posture summary from readiness signals."""
    taxonomy = readiness.get("taxonomy_signals", {}) if isinstance(readiness, dict) else {}
    if not isinstance(taxonomy, dict):
        taxonomy = {}
    conflict_count = safe_int(taxonomy.get("family_type_conflict_count", 0), 0)
    high_priority_count = safe_int(taxonomy.get("high_priority_conflict_count", 0), 0)
    action_counts = taxonomy.get("family_type_conflict_action_counts", {})
    if not isinstance(action_counts, dict):
        action_counts = {}
    issue_counts = taxonomy.get("family_type_conflict_issue_counts", {})
    if not isinstance(issue_counts, dict):
        issue_counts = {}

    dominant_action = ""
    dominant_action_count = 0
    if action_counts:
        dominant_action, dominant_action_count = max(
            ((str(k), safe_int(v, 0)) for k, v in action_counts.items() if str(k).strip()),
            key=lambda item: (item[1], item[0]),
            default=("", 0),
        )
    dominant_issue = ""
    dominant_issue_count = 0
    if issue_counts:
        dominant_issue, dominant_issue_count = max(
            ((str(k), safe_int(v, 0)) for k, v in issue_counts.items() if str(k).strip()),
            key=lambda item: (item[1], item[0]),
            default=("", 0),
        )
    note = taxonomy_curation_discipline_note(
        conflict_count=conflict_count,
        high_priority_count=high_priority_count,
        action_counts=action_counts,
        issue_counts=issue_counts,
    )
    return {
        "conflict_count": conflict_count,
        "high_priority_count": high_priority_count,
        "action_counts": action_counts,
        "issue_counts": issue_counts,
        "dominant_action": dominant_action,
        "dominant_action_count": dominant_action_count,
        "dominant_issue": dominant_issue,
        "dominant_issue_count": dominant_issue_count,
        "note": note,
    }


def build_backlog_debt_summary(
    *,
    readiness: dict[str, object],
    fp_triage: dict[str, object],
    android_missing_triage: dict[str, object],
    policy_held_triage: dict[str, object] | None = None,
    missing_primary_triage: dict[str, object] | None = None,
    profile_mapping_debt: dict[str, object] | None = None,
    blank_resolved_triage: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build one ranked cross-surface debt ledger for operator cleanup."""
    taxonomy = readiness.get("taxonomy_signals", {}) if isinstance(readiness, dict) else {}
    posture = build_taxonomy_curation_posture(readiness=readiness)
    missing_primary_lanes = _missing_primary_lane_rows(taxonomy if isinstance(taxonomy, dict) else {})
    unresolved_count = safe_int(taxonomy.get("unresolved_family_count", 0), 0) if isinstance(taxonomy, dict) else 0
    policy_held_kind_counts = (
        taxonomy.get("policy_held_family_token_kind_counts", {})
        if isinstance(taxonomy, dict)
        else {}
    )
    policy_held_generic_samples = (
        safe_int(policy_held_kind_counts.get("generic_family_token", 0), 0)
        if isinstance(policy_held_kind_counts, dict)
        else 0
    )

    def _row(*, code: str, label: str, count: int, action: str, detail: str = "") -> dict[str, object] | None:
        if count <= 0:
            return None
        return {
            "code": str(code),
            "label": label,
            "count": int(count),
            "action": action,
            "detail": detail,
        }

    rows = [
        _row(
            code=BACKLOG_ROW_ANDROID_MISSING_RESOLUTION,
            label=ANDROID_MISSING_RESOLUTION_BACKLOG_LABEL,
            count=safe_int(android_missing_triage.get("row_count", 0), 0),
            action=_android_missing_resolution_action(
                android_missing_triage=android_missing_triage if isinstance(android_missing_triage, dict) else {},
                taxonomy=taxonomy if isinstance(taxonomy, dict) else {},
            ),
            detail=_android_missing_resolution_detail(
                android_missing_triage=android_missing_triage if isinstance(android_missing_triage, dict) else {},
                taxonomy=taxonomy if isinstance(taxonomy, dict) else {},
            ),
        ),
        _row(
            code=BACKLOG_ROW_VT_FALSE_POSITIVE,
            label=VT_FALSE_POSITIVE_REVIEW_RESIDUE_LABEL,
            count=safe_int(fp_triage.get("row_count", 0), 0),
            action=(
                "Refresh the VT false-positive triage export first."
                if str(fp_triage.get("freshness", "") or "").strip() == "stale"
                else "Open VT false-positive triage and drain the dominant review lane."
            ),
            detail=(
                f"freshness={str(fp_triage.get('freshness', '') or '').strip()}; "
                f"top_lane={str(fp_triage.get('top_lane', '') or '').strip() or 'none'}"
            ),
        ),
        _row(
            code=BACKLOG_ROW_BLANK_RESOLVED_FAMILY,
            label="Blank resolved-family residue",
            count=safe_int((blank_resolved_triage or {}).get("row_count", 0), 0),
            action=(
                "Refresh the blank-resolved family triage export first."
                if str((blank_resolved_triage or {}).get("freshness", "") or "").strip() == "stale"
                else "Open blank-resolved family triage for provenance/policy lanes outside missing-resolution view."
            ),
            detail=(
                f"freshness={str((blank_resolved_triage or {}).get('freshness', '') or '').strip() or 'unknown'}; "
                f"live_blank_resolved={safe_int(taxonomy.get('blank_resolved_family_samples', 0), 0)}; "
                f"top_lane={str((blank_resolved_triage or {}).get('top_lane', '') or '').strip() or 'none'}"
            ),
        ),
        _row(
            code=BACKLOG_ROW_MISSING_PRIMARY_LABELS,
            label="Missing primary labels",
            count=safe_int(taxonomy.get("missing_primary_label_samples", 0), 0),
            action=_missing_primary_action(
                taxonomy if isinstance(taxonomy, dict) else {},
                missing_primary_triage=missing_primary_triage,
            ),
            detail=_augment_missing_primary_detail(
                _missing_primary_detail(taxonomy if isinstance(taxonomy, dict) else {}),
                missing_primary_triage,
            ),
        ),
        _row(
            code=BACKLOG_ROW_TRUE_UNRESOLVED_FAMILY,
            label=TRUE_UNRESOLVED_FAMILY_DEBT_LABEL,
            count=safe_int(taxonomy.get("unresolved_family_samples", 0), 0),
            action="Open profile readiness mapping inventory and review live unresolved family slugs.",
            detail="Resolved families not mapped into authority and not already policy-held.",
        ),
        _row(
            code=BACKLOG_ROW_POLICY_HELD_FAMILY,
            label=POLICY_HELD_FAMILY_NOISE_LABEL,
            count=(
                safe_int(taxonomy.get("policy_held_family_samples", 0), 0)
                if policy_held_generic_samples > 0
                else 0
            ),
            action=_policy_held_family_action(policy_held_triage),
            detail=_augment_policy_held_family_detail(
                _policy_held_family_detail(taxonomy if isinstance(taxonomy, dict) else {}),
                policy_held_triage,
            ),
        ),
        _row(
            code=BACKLOG_ROW_FAMILY_TYPE_CONFLICT,
            label=FAMILY_TYPE_CONFLICT_BACKLOG_LABEL,
            count=safe_int(taxonomy.get("family_type_conflict_count", 0), 0),
            action="Open profile readiness mapping inventory and review family/type conflict candidates.",
            detail=_family_type_conflict_detail(taxonomy if isinstance(taxonomy, dict) else {}),
        ),
    ]
    ranked_rows = [row for row in rows if isinstance(row, dict)]
    row_priority = {
        BACKLOG_ROW_ANDROID_MISSING_RESOLUTION: 0,
        BACKLOG_ROW_TRUE_UNRESOLVED_FAMILY: 1,
        BACKLOG_ROW_MISSING_PRIMARY_LABELS: 2,
        BACKLOG_ROW_BLANK_RESOLVED_FAMILY: 3,
        BACKLOG_ROW_FAMILY_TYPE_CONFLICT: 4,
        BACKLOG_ROW_VT_FALSE_POSITIVE: 5,
        BACKLOG_ROW_POLICY_HELD_FAMILY: 6,
    }
    ranked_rows.sort(key=lambda row: (-safe_int(row.get("count", 0), 0), str(row.get("label", ""))))
    ranked_rows.sort(
        key=lambda row: (
            row_priority.get(str(row.get("code", "") or ""), 99),
            -safe_int(row.get("count", 0), 0),
            str(row.get("label", "")),
        )
    )
    top = ranked_rows[0] if ranked_rows else {}
    if str(top.get("code", "") or "") == BACKLOG_ROW_POLICY_HELD_FAMILY and unresolved_count == 0:
        top = top.copy()
        top["focus_note"] = "Policy-held rows are governance residue, not true unresolved family debt."
    profile_mapping_detail = _profile_family_mapping_detail(profile_mapping_debt)
    true_unmapped_rows = safe_int(
        (profile_mapping_debt or {}).get("true_unmapped_resolved_slug_rows", 0)
        if isinstance(profile_mapping_debt, dict)
        else 0,
        0,
    )
    if true_unmapped_rows > 0:
        ranked_rows.append(
            {
                "code": "profile_true_unmapped_slug",
                "label": PROFILE_FAMILY_MAPPING_DEBT_LABEL,
                "count": true_unmapped_rows,
                "action": "Open profile family-mapping debt export and repair true catalog-lag slugs first.",
                "detail": profile_mapping_detail,
            }
        )
    return_payload = {
        "rows": ranked_rows,
        "focus_code": str(top.get("code", "") or ""),
        "focus_label": str(top.get("label", "") or ""),
        "focus_count": safe_int(top.get("count", 0), 0),
        "focus_action": str(top.get("action", "") or ""),
        "focus_detail": str(top.get("detail", "") or ""),
        "focus_note": str(top.get("focus_note", "") or ""),
        "focus_structured": top.get("focus_structured", {}) if isinstance(top.get("focus_structured", {}), dict) else {},
        "missing_primary_label_lanes": missing_primary_lanes,
        "taxonomy_curation_posture": posture,
    }
    if profile_mapping_detail:
        return_payload["profile_mapping_note"] = profile_mapping_detail
    if str(top.get("code", "") or "") == BACKLOG_ROW_ANDROID_MISSING_RESOLUTION:
        triage = android_missing_triage if isinstance(android_missing_triage, dict) else {}
        lane_counts = (
            triage.get("lane_counts", {}) if isinstance(triage.get("lane_counts"), dict) else {}
        )
        return_payload["focus_structured"] = {
            "source": "live DB current-state view, not frozen run snapshot",
            "freshness": str(triage.get("freshness", "") or "").strip() or "unknown",
            "lane_counts": lane_counts,
            "top_lane": str(triage.get("top_lane", "") or "").strip(),
            "top_lane_count": safe_int(triage.get("top_lane_count", 0), 0),
            "vt_tail_review_count": safe_int(lane_counts.get("vt_tail_review", 0), 0),
            "vt_tail_export": "output/diagnostics/android_missing_resolution_vt_tail_latest.csv",
            "lane_worklist_export_pattern": "output/diagnostics/android_missing_resolution_lane_*_latest.csv",
        }
    if str(top.get("code", "") or "") == BACKLOG_ROW_POLICY_HELD_FAMILY:
        triage = policy_held_triage if isinstance(policy_held_triage, dict) else {}
        token_kind_counts = (
            taxonomy.get("policy_held_family_token_kind_counts", {})
            if isinstance(taxonomy, dict)
            else {}
        )
        return_payload["focus_structured"] = {
            "source": "live DB current-state view, not frozen run snapshot",
            "freshness": str(triage.get("freshness", "") or "").strip() or "unknown",
            "token_kind_counts": token_kind_counts if isinstance(token_kind_counts, dict) else {},
            "top_lane": str(triage.get("top_lane", "") or "").strip(),
            "top_lane_count": safe_int(triage.get("top_lane_count", 0), 0),
            "top_policy_held_token": str(triage.get("top_policy_held_token", "") or "").strip(),
            "top_policy_held_token_count": safe_int(triage.get("top_policy_held_token_count", 0), 0),
            "top_android_package_name": str(triage.get("top_android_package_name", "") or "").strip(),
            "top_android_package_name_count": safe_int(triage.get("top_android_package_name_count", 0), 0),
            "high_or_strong_row_count": safe_int(triage.get("high_or_strong_row_count", 0), 0),
            "missing_primary_lane_split": _format_missing_primary_lane_split(missing_primary_lanes),
        }
    if str(top.get("code", "") or "") == BACKLOG_ROW_BLANK_RESOLVED_FAMILY:
        triage = blank_resolved_triage if isinstance(blank_resolved_triage, dict) else {}
        lane_counts = (
            triage.get("lane_counts", {}) if isinstance(triage.get("lane_counts"), dict) else {}
        )
        return_payload["focus_structured"] = {
            "source": "live DB current-state view, not frozen run snapshot",
            "freshness": str(triage.get("freshness", "") or "").strip() or "unknown",
            "lane_counts": lane_counts,
            "top_lane": str(triage.get("top_lane", "") or "").strip(),
            "top_lane_count": safe_int(triage.get("top_lane_count", 0), 0),
            "singleton_provenance_count": safe_int(lane_counts.get("singleton_provenance_review", 0), 0),
            "singleton_export": "output/diagnostics/blank_resolved_singleton_provenance_latest.csv",
            "singleton_cluster_export": "output/diagnostics/blank_resolved_singleton_package_clusters_latest.csv",
        }
    return return_payload


def read_run_backlog_snapshot_counts(path: Path) -> dict[str, int]:
    """Parse a run-scoped backlog summary markdown file into label->count."""
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    counts: dict[str, int] = {}
    for label in _RUN_BACKLOG_LABELS:
        pattern = re.compile(rf"{re.escape(label)}(?: \(\*\*| \(|: )(\d+)")
        match = pattern.search(text)
        if match:
            counts[label] = safe_int(match.group(1), 0)
    return counts


def build_backlog_markdown_lines(
    *,
    debt_summary: dict[str, Any],
    priority_backlog: dict[str, Any],
    backlog_md: Path | None = None,
    android_path: Path | str | None = None,
    fp_path: Path | str | None = None,
    policy_held_path: Path | str | None = None,
    missing_primary_path: Path | str | None = None,
    heading: str = "## Backlog and operator queues",
    ranked_style: str = "bullets",
    max_rows: int = 5,
) -> list[str]:
    """Render a shared Markdown backlog/debt block for exported report surfaces."""
    lines: list[str] = [heading, ""]
    if isinstance(debt_summary, dict) and debt_summary.get("rows"):
        lines.append(
            f"- **Focus area:** {str(debt_summary.get('focus_label', '—') or '—')} "
            f"({int(debt_summary.get('focus_count', 0) or 0)} row(s))"
        )
        source_note = str(debt_summary.get("source_note", "") or "").strip()
        if source_note:
            lines.append(f"- **Source:** {source_note}")
        focus_detail = str(debt_summary.get("focus_detail", "") or "").strip()
        if focus_detail:
            lines.append(f"- **Focus detail:** {focus_detail}")
        focus_note = str(debt_summary.get("focus_note", "") or "").strip()
        if focus_note:
            lines.append(f"- **Focus note:** {focus_note}")
        profile_mapping_note = str(debt_summary.get("profile_mapping_note", "") or "").strip()
        if profile_mapping_note:
            lines.append(f"- **Profile mapping split:** {profile_mapping_note}")
        lane_split = _format_missing_primary_lane_split(
            debt_summary.get("missing_primary_label_lanes", [])
            if isinstance(debt_summary.get("missing_primary_label_lanes", []), list)
            else []
        )
        if lane_split:
            lines.append(f"- **Missing-primary lane split:** {lane_split}")
        snapshot_note = str(debt_summary.get("snapshot_compare_note", "") or "").strip()
        if snapshot_note:
            lines.append(f"- **Run snapshot:** {snapshot_note}")
        focus_action = str(debt_summary.get("focus_action", "") or "").strip()
        if focus_action:
            lines.append(f"- **Recommended next action:** {focus_action}")
        if isinstance(priority_backlog, dict) and priority_backlog:
            lines.append(
                f"- **Priority queue:** {str(priority_backlog.get('label', '—') or '—')} "
                f"[freshness={str(priority_backlog.get('freshness', '—') or '—')}]"
            )
        taxonomy_posture = debt_summary.get("taxonomy_curation_posture", {}) if isinstance(debt_summary, dict) else {}
        curation_note = str((taxonomy_posture or {}).get("note", "") or "").strip()
        if curation_note:
            lines.append(f"- **Family taxonomy posture:** {curation_note}")
        if ranked_style == "table":
            lines.extend(
                [
                    "- **Ranked debt:**",
                    "",
                    "| category | count | detail |",
                    "| --- | ---: | --- |",
                ]
            )
            for row in list(debt_summary.get("rows", []))[:max_rows]:
                if not isinstance(row, dict):
                    continue
                lines.append(
                    f"| {str(row.get('label', '') or '')} | {int(row.get('count', 0) or 0)} | {str(row.get('detail', '') or '—')} |"
                )
        else:
            lines.append("- **Ranked debt:**")
            for row in list(debt_summary.get("rows", []))[:max_rows]:
                if not isinstance(row, dict):
                    continue
                detail = str(row.get("detail", "") or "").strip()
                suffix = f" — {detail}" if detail else ""
                lines.append(
                    f"  - {str(row.get('label', '') or '')}: {int(row.get('count', 0) or 0)}{suffix}"
                )
    else:
        lines.append("- No ranked backlog debt rows surfaced.")

    if backlog_md is not None or android_path or fp_path or policy_held_path or missing_primary_path:
        lines.append("- **Related queue artifacts:**")
        if backlog_md is not None:
            lines.append(f"  - backlog debt summary: `{backlog_md}`")
        if missing_primary_path:
            lines.append(f"  - missing-primary label triage: `{missing_primary_path}`")
        if android_path:
            lines.append(f"  - android missing-resolution triage: `{android_path}`")
        if fp_path:
            lines.append(f"  - vt false-positive triage: `{fp_path}`")
        if policy_held_path:
            lines.append(f"  - policy-held token risk: `{policy_held_path}`")
    lines.append("")
    return lines


def build_backlog_terminal_lines(
    *,
    debt_summary: dict[str, Any],
    priority_backlog: dict[str, Any] | None = None,
    backlog_path: Path | str | None = None,
    policy_held_path: Path | str | None = None,
    missing_primary_path: Path | str | None = None,
    blank_resolved_path: Path | str | None = None,
    max_rows: int = 5,
) -> list[str]:
    """Render a shared terminal-friendly backlog/debt block."""
    lines: list[str] = []
    if not isinstance(debt_summary, dict) or not debt_summary:
        return lines
    focus_code = str(debt_summary.get("focus_code", "") or "")
    if focus_code == BACKLOG_ROW_POLICY_HELD_FAMILY:
        structured = (
            debt_summary.get("focus_structured", {})
            if isinstance(debt_summary.get("focus_structured"), dict)
            else {}
        )
        token_kind_counts = (
            structured.get("token_kind_counts", {})
            if isinstance(structured.get("token_kind_counts"), dict)
            else {}
        )
        lines.append("Debt status: No true unresolved family debt in this slice")
        lines.append(f"Primary residue: {str(debt_summary.get('focus_label', '—') or '—')}")
        lines.append(f"Rows: {int(debt_summary.get('focus_count', 0) or 0)}")
        source_note = str(structured.get("source", "") or "").strip()
        if source_note:
            lines.append(f"Source: {source_note}")
        freshness = str(structured.get("freshness", "") or "").strip()
        if freshness:
            lines.append(f"Freshness: {freshness}")
        if token_kind_counts:
            lines.append("")
            lines.append("Residue breakdown")
            lines.append("-----------------")
            for token_kind, count in sorted(
                (
                    (str(token_kind), safe_int(count, 0))
                    for token_kind, count in token_kind_counts.items()
                    if str(token_kind).strip() and safe_int(count, 0) > 0
                ),
                key=lambda item: (-item[1], item[0]),
            ):
                lines.append(f"{token_kind}: {count}")
        lines.append("")
        lines.append("Dominant cluster")
        lines.append("----------------")
        top_lane = str(structured.get("top_lane", "") or "").strip()
        top_lane_count = safe_int(structured.get("top_lane_count", 0), 0)
        if top_lane and top_lane_count > 0:
            lines.append(f"Top hold lane: {top_lane} ({top_lane_count})")
        top_token = str(structured.get("top_policy_held_token", "") or "").strip()
        top_token_count = safe_int(structured.get("top_policy_held_token_count", 0), 0)
        if top_token and top_token_count > 0:
            lines.append(f"Top token: {top_token} ({top_token_count})")
        top_package = str(structured.get("top_android_package_name", "") or "").strip()
        top_package_count = safe_int(structured.get("top_android_package_name_count", 0), 0)
        if top_package and top_package != "<blank>" and top_package_count > 0:
            lines.append(f"Top package: {top_package} ({top_package_count})")
        high_or_strong = safe_int(structured.get("high_or_strong_row_count", 0), 0)
        if high_or_strong > 0:
            lines.append(f"High/strong rows: {high_or_strong}")
        lane_split = str(structured.get("missing_primary_lane_split", "") or "").strip()
        if lane_split:
            lines.append(f"Missing-primary split: {lane_split}")
        lines.append("")
        lines.append("Interpretation")
        lines.append("--------------")
        lines.append(
            "Policy-held rows are governance residue, not unresolved family authority debt."
        )
        lines.append(
            "Do not create new family authority rows from generic/coarse/class-label tokens without reviewing the policy-held token risk export."
        )
        lines.append("")
        lines.append("Next action")
        lines.append("-----------")
        lines.append("Review policy-held token risk export, focusing on:")
        if top_lane:
            lines.append(f"1. {top_lane}")
        behavior_count = safe_int(token_kind_counts.get("behavior_class_token", 0), 0)
        if behavior_count > 0:
            lines.append("2. behavior_class_token")
        if top_token:
            lines.append(f"3. {top_token} token cluster")
        if top_package and top_package != "<blank>":
            lines.append(f"4. {top_package} package cluster")
        lines.append("")
        lines.append("Diagnostics")
        lines.append("-----------")
        if backlog_path:
            lines.append(Path(str(backlog_path)).name)
        if policy_held_path:
            lines.append(Path(str(policy_held_path)).name)
        return lines
    lines.append(
        f"Focus area: {str(debt_summary.get('focus_label', '—') or '—')} "
        f"({int(debt_summary.get('focus_count', 0) or 0)} row(s))"
    )
    source_note = str(debt_summary.get("source_note", "") or "").strip()
    if source_note:
        lines.append(f"Source: {source_note}")
    focus_detail = str(debt_summary.get("focus_detail", "") or "").strip()
    if focus_detail:
        lines.append(f"Focus detail: {focus_detail}")
    focus_note = str(debt_summary.get("focus_note", "") or "").strip()
    if focus_note:
        lines.append(f"Focus note: {focus_note}")
    lane_split = _format_missing_primary_lane_split(
        debt_summary.get("missing_primary_label_lanes", [])
        if isinstance(debt_summary.get("missing_primary_label_lanes", []), list)
        else []
    )
    if lane_split:
        lines.append(f"Missing-primary lane split: {lane_split}")
    snapshot_note = str(debt_summary.get("snapshot_compare_note", "") or "").strip()
    if snapshot_note:
        lines.append(f"Run snapshot: {snapshot_note}")
    profile_mapping_note = str(debt_summary.get("profile_mapping_note", "") or "").strip()
    if profile_mapping_note:
        lines.append(f"Profile mapping split: {profile_mapping_note}")
    focus_action = str(debt_summary.get("focus_action", "") or "").strip()
    if focus_action:
        lines.append(f"Recommended next action: {focus_action}")
    focus_structured = (
        debt_summary.get("focus_structured", {})
        if isinstance(debt_summary.get("focus_structured"), dict)
        else {}
    )
    vt_tail_count = safe_int(focus_structured.get("vt_tail_review_count", 0), 0)
    vt_tail_export = str(focus_structured.get("vt_tail_export", "") or "").strip()
    if vt_tail_count > 0 and vt_tail_export:
        lines.append(f"VT-tail drill-down: `{vt_tail_export}` ({vt_tail_count} row(s))")
    for row in list(debt_summary.get("rows", []))[:max_rows]:
        if not isinstance(row, dict):
            continue
        detail = str(row.get("detail", "") or "").strip()
        suffix = f" — {detail}" if detail else ""
        lines.append(
            f"{str(row.get('label', '') or '')}: {int(row.get('count', 0) or 0)}{suffix}"
        )
    if isinstance(priority_backlog, dict) and priority_backlog:
        lines.append(
            f"Priority queue: {str(priority_backlog.get('label', '—') or '—')} "
            f"[freshness={str(priority_backlog.get('freshness', '—') or '—')}]"
        )
    taxonomy_posture = debt_summary.get("taxonomy_curation_posture", {}) if isinstance(debt_summary, dict) else {}
    curation_note = str((taxonomy_posture or {}).get("note", "") or "").strip()
    if curation_note:
        lines.append(curation_note)
    if backlog_path:
        lines.append(f"File: `{backlog_path}`")
    if missing_primary_path:
        lines.append(f"Missing-primary triage: `{missing_primary_path}`")
    if blank_resolved_path:
        lines.append(f"Blank-resolved triage: `{blank_resolved_path}`")
    return lines
