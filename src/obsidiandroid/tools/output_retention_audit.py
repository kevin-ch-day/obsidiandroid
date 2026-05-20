"""Read-only retention audit for run-scoped output folders.

This module classifies historical ``output/runs/<run_id>/`` folders into
conservative retention buckets without deleting anything. The goal is to make
retention policy explicit before any destructive cleanup command is introduced.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from obsidiandroid.common import output_paths
from obsidiandroid.common.json_io import read_json_dict

KEEP_MARKER = ".keep"
PROTECTED_MARKER = ".protected"
CLEANUP_CANDIDATE_MARKER = ".cleanup_candidate"


def _utc_now() -> datetime:
    """Return current UTC time (wrapped for tests)."""
    return datetime.now(UTC)


def _parse_iso_utc(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_run_id_timestamp(run_id: str) -> datetime | None:
    token = str(run_id or "").strip()
    if len(token) < 16 or "T" not in token or not token[:8].isdigit():
        return None
    stamp = token.split("__", maxsplit=1)[0]
    try:
        parsed = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC)


def _safe_json(path: Path) -> dict[str, Any]:
    payload = read_json_dict(path)
    return payload if isinstance(payload, dict) else {}


def _first_str(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _human_size(num_bytes: int) -> str:
    value = float(max(0, num_bytes))
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024.0 or unit == "TiB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{num_bytes} B"


def _directory_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += int(child.stat().st_size)
            except OSError:
                continue
    return total


def _latest_pointer_run_id(output_dir: Path) -> str | None:
    diagnostics_dir = output_dir / "diagnostics"
    promoted_dir = output_dir / "promoted"
    candidates = [
        diagnostics_dir / "latest_run_pointer.json",
        promoted_dir / "latest_run_manifest.json",
        promoted_dir / "latest_run.txt",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            if path.suffix == ".json":
                payload = json.loads(path.read_text(encoding="utf-8"))
                run_id = str(payload.get("run_id", "")).strip()
            else:
                run_id = path.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if run_id:
            return run_id
    return None


@dataclass(frozen=True)
class RetentionPolicy:
    """Conservative retention defaults for the audit tool."""

    recent_days: int = 7
    keep_last_full_per_profile: int = 3
    keep_last_dev_runs_total: int = 5


@dataclass
class RunRetentionRecord:
    """Derived run metadata for retention classification."""

    run_id: str
    run_dir: Path
    size_bytes: int
    manifest_path: Path | None = None
    metadata_source: str = "none"
    profile_id: str = "unknown"
    profile_description: str = ""
    run_status: str = "unknown"
    completed_stage: str = ""
    publication_ready_status: str = ""
    paper_safe_status: str = ""
    evidence_mode: bool | None = None
    paper_mode: bool | None = None
    timestamp_utc: datetime | None = None
    mode: str = "unknown"
    status_bucket: str = "unknown"
    retention_class: str = "unknown"
    reasons: list[str] = field(default_factory=list)
    marker_keep: bool = False
    marker_protected: bool = False
    marker_cleanup_candidate: bool = False
    is_latest_pointer: bool = False
    is_promoted_pointer: bool = False


@dataclass
class RetentionAudit:
    """Complete read-only retention audit."""

    output_dir: Path
    policy: RetentionPolicy
    generated_at_utc: datetime
    latest_run_id: str | None
    promoted_run_id: str | None
    run_records: list[RunRetentionRecord]
    total_runs_size_bytes: int
    diagnostics_size_bytes: int
    bundles_size_bytes: int
    latest_size_bytes: int
    promoted_size_bytes: int
    reports_size_bytes: int

    @property
    def reclaimable_bytes(self) -> int:
        return sum(r.size_bytes for r in self.run_records if r.retention_class == "disposable")


def parse_run_record(run_dir: Path) -> RunRetentionRecord:
    """Read one run directory into a retention record."""
    run_id = run_dir.name
    manifest_path = run_dir / "run_manifest.json"
    summary_path = run_dir / "run_summary.json"
    payload: dict[str, Any] = {}
    source = "none"
    if manifest_path.exists():
        payload = _safe_json(manifest_path)
        source = "manifest"
    elif summary_path.exists():
        payload = _safe_json(summary_path)
        source = "summary"

    profile_params = payload.get("profile_params")
    profile_params = profile_params if isinstance(profile_params, dict) else {}
    profile_id = (
        _first_str(payload, "profile_id")
        or _first_str(profile_params, "profile_id")
        or "unknown"
    )
    description = _first_str(profile_params, "description")
    timestamp = (
        _parse_iso_utc(payload.get("timestamp_utc"))
        or _parse_iso_utc(payload.get("lifecycle_started_at_utc"))
        or _parse_iso_utc(payload.get("created_at_utc"))
        or _parse_run_id_timestamp(run_id)
    )
    evidence_mode = payload.get("evidence_mode")
    if evidence_mode is None and "evidence_mode" in profile_params:
        evidence_mode = profile_params.get("evidence_mode")
    paper_mode_payload = payload.get("paper_mode")
    if isinstance(paper_mode_payload, dict):
        paper_mode = bool(paper_mode_payload.get("resolved_value"))
    elif isinstance(paper_mode_payload, bool):
        paper_mode = paper_mode_payload
    else:
        paper_mode = None

    record = RunRetentionRecord(
        run_id=run_id,
        run_dir=run_dir,
        size_bytes=_directory_size(run_dir),
        manifest_path=manifest_path if manifest_path.exists() else (summary_path if summary_path.exists() else None),
        metadata_source=source,
        profile_id=profile_id,
        profile_description=description,
        run_status=_first_str(payload, "run_status") or "unknown",
        completed_stage=_first_str(payload, "completed_stage"),
        publication_ready_status=_first_str(payload, "publication_ready_status"),
        paper_safe_status=_first_str(payload, "paper_safe_status"),
        evidence_mode=bool(evidence_mode) if evidence_mode is not None else None,
        paper_mode=paper_mode,
        timestamp_utc=timestamp,
        marker_keep=(run_dir / KEEP_MARKER).exists(),
        marker_protected=(run_dir / PROTECTED_MARKER).exists(),
        marker_cleanup_candidate=(run_dir / CLEANUP_CANDIDATE_MARKER).exists(),
    )
    record.mode = infer_run_mode(record)
    record.status_bucket = infer_status_bucket(record)
    return record


def infer_run_mode(record: RunRetentionRecord) -> str:
    """Infer coarse operator mode from manifest/profile hints."""
    profile = record.profile_id.lower()
    desc = record.profile_description.lower()
    if (
        record.evidence_mode is True
        or record.paper_mode is True
        or record.publication_ready_status.upper() == "PASS"
        or "publication-ready" in desc
        or "locked" in profile
    ):
        return "evidence/publication"
    if any(token in profile for token in ("smoke", "dev")) or any(
        token in desc for token in ("smoke", "fast local iteration", "development", "ultra-fast")
    ):
        return "dev/smoke"
    if "exploratory" in desc or "research cohort" in desc or "standard cohort" in desc:
        return "exploratory"
    return "unknown"


def infer_status_bucket(record: RunRetentionRecord) -> str:
    """Normalize run status to retention-friendly buckets."""
    status = record.run_status.strip().lower()
    if status == "complete":
        return "complete/pass"
    if status == "failed":
        return "failed"
    if status == "partial":
        if record.completed_stage and record.completed_stage != "manifest":
            return "interrupted"
        return "partial/unknown"
    return "partial/unknown" if record.metadata_source != "none" else "unknown"


def _sort_key(record: RunRetentionRecord) -> tuple[int, datetime, str]:
    timestamp = record.timestamp_utc or datetime.fromtimestamp(0, UTC)
    valid = 1 if record.timestamp_utc is not None else 0
    return (valid, timestamp, record.run_id)


def classify_runs(
    records: list[RunRetentionRecord],
    *,
    output_dir: Path,
    policy: RetentionPolicy,
    now_utc: datetime,
) -> None:
    """Assign retention classes conservatively in place."""
    latest_run_id = _latest_pointer_run_id(output_dir)
    promoted_run_id = latest_run_id
    diagnostics_pointer = output_dir / "diagnostics" / "latest_run_pointer.json"
    promoted_manifest = output_dir / "promoted" / "latest_run_manifest.json"
    if promoted_manifest.exists():
        promoted_run_id = str(_safe_json(promoted_manifest).get("run_id", "")).strip() or promoted_run_id
    if diagnostics_pointer.exists():
        latest_run_id = str(_safe_json(diagnostics_pointer).get("run_id", "")).strip() or latest_run_id

    recent_cutoff = now_utc - timedelta(days=max(0, policy.recent_days))

    complete_by_profile: dict[str, list[RunRetentionRecord]] = defaultdict(list)
    dev_candidates: list[RunRetentionRecord] = []
    for record in records:
        if record.profile_id != "unknown" and record.status_bucket == "complete/pass":
            complete_by_profile[record.profile_id].append(record)
        if record.mode == "dev/smoke":
            dev_candidates.append(record)

    recent_profile_ids: set[str] = set()
    for runs in complete_by_profile.values():
        for record in sorted(runs, key=_sort_key, reverse=True)[: max(0, policy.keep_last_full_per_profile)]:
            recent_profile_ids.add(record.run_id)

    recent_dev_ids = {
        record.run_id
        for record in sorted(dev_candidates, key=_sort_key, reverse=True)[: max(0, policy.keep_last_dev_runs_total)]
    }

    for record in records:
        record.is_latest_pointer = record.run_id == latest_run_id
        record.is_promoted_pointer = record.run_id == promoted_run_id
        reasons: list[str] = []

        if record.marker_protected:
            record.retention_class = "protected"
            reasons.append("marker:.protected")
        elif record.is_latest_pointer:
            record.retention_class = "protected"
            reasons.append("current latest-run pointer")
        elif record.is_promoted_pointer:
            record.retention_class = "protected"
            reasons.append("promoted latest-run pointer")
        elif (
            record.mode == "evidence/publication"
            and record.status_bucket == "complete/pass"
            and record.publication_ready_status.upper() == "PASS"
        ):
            record.retention_class = "protected"
            reasons.append("publication/evidence PASS")
        elif record.marker_keep:
            record.retention_class = "pinned"
            reasons.append("marker:.keep")
        elif record.timestamp_utc is None and record.metadata_source == "none":
            record.retention_class = "unknown"
            reasons.append("missing metadata")
        elif record.timestamp_utc is not None and record.timestamp_utc >= recent_cutoff:
            record.retention_class = "recent"
            reasons.append(f"within {policy.recent_days}-day window")
        elif record.run_id in recent_profile_ids:
            record.retention_class = "recent"
            reasons.append(f"kept among last {policy.keep_last_full_per_profile} complete runs for profile")
        elif record.run_id in recent_dev_ids:
            record.retention_class = "recent"
            reasons.append(f"kept among last {policy.keep_last_dev_runs_total} dev/smoke runs")
        elif record.mode == "dev/smoke":
            record.retention_class = "disposable"
            reasons.append("older dev/smoke run outside default keep window")
        elif record.status_bucket in {"failed", "interrupted", "partial/unknown"} and record.mode != "evidence/publication":
            record.retention_class = "disposable"
            reasons.append("older non-evidence failed/partial run outside keep window")
        else:
            record.retention_class = "unknown"
            reasons.append("conservative fallback")

        if record.marker_cleanup_candidate:
            reasons.append("marker:.cleanup_candidate")
        record.reasons = reasons


def audit_output_retention(
    output_dir: Path,
    *,
    policy: RetentionPolicy | None = None,
    now_utc: datetime | None = None,
) -> RetentionAudit:
    """Build a full dry-run retention audit for the output tree."""
    policy = policy or RetentionPolicy()
    now_utc = now_utc or _utc_now()
    output_dir = output_dir.expanduser().resolve()
    runs_root = output_dir / "runs"
    run_records: list[RunRetentionRecord] = []
    if runs_root.exists():
        for child in sorted(runs_root.iterdir()):
            if child.is_dir():
                run_records.append(parse_run_record(child))

    classify_runs(run_records, output_dir=output_dir, policy=policy, now_utc=now_utc)

    latest_run_id = _latest_pointer_run_id(output_dir)
    promoted_payload = _safe_json(output_dir / "promoted" / "latest_run_manifest.json")
    promoted_run_id = str(promoted_payload.get("run_id", "")).strip() or latest_run_id

    return RetentionAudit(
        output_dir=output_dir,
        policy=policy,
        generated_at_utc=now_utc,
        latest_run_id=latest_run_id,
        promoted_run_id=promoted_run_id,
        run_records=sorted(run_records, key=_sort_key, reverse=True),
        total_runs_size_bytes=_directory_size(output_dir / "runs"),
        diagnostics_size_bytes=_directory_size(output_dir / "diagnostics"),
        bundles_size_bytes=_directory_size(output_dir / "bundles"),
        latest_size_bytes=_directory_size(output_dir / "latest"),
        promoted_size_bytes=_directory_size(output_dir / "promoted"),
        reports_size_bytes=_directory_size(output_dir / "reports"),
    )


def _by_date(records: list[RunRetentionRecord]) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for record in records:
        stamp = record.timestamp_utc or _parse_run_id_timestamp(record.run_id)
        key = stamp.strftime("%Y-%m-%d") if stamp else "unknown"
        counts[key] += 1
    return sorted(counts.items())


def _by_field(records: list[RunRetentionRecord], field_name: str) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter(getattr(record, field_name) or "unknown" for record in records)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def audit_to_dict(audit: RetentionAudit) -> dict[str, Any]:
    """Serialize audit to a JSON-friendly mapping."""
    return {
        "generated_at_utc": audit.generated_at_utc.isoformat(),
        "output_dir": str(audit.output_dir),
        "policy": {
            "recent_days": audit.policy.recent_days,
            "keep_last_full_per_profile": audit.policy.keep_last_full_per_profile,
            "keep_last_dev_runs_total": audit.policy.keep_last_dev_runs_total,
        },
        "summary": {
            "run_count": len(audit.run_records),
            "latest_run_id": audit.latest_run_id,
            "promoted_run_id": audit.promoted_run_id,
            "total_runs_size_bytes": audit.total_runs_size_bytes,
            "diagnostics_size_bytes": audit.diagnostics_size_bytes,
            "bundles_size_bytes": audit.bundles_size_bytes,
            "latest_size_bytes": audit.latest_size_bytes,
            "promoted_size_bytes": audit.promoted_size_bytes,
            "reports_size_bytes": audit.reports_size_bytes,
            "reclaimable_bytes": audit.reclaimable_bytes,
        },
        "counts": {
            "retention": dict(_by_field(audit.run_records, "retention_class")),
            "status": dict(_by_field(audit.run_records, "status_bucket")),
            "mode": dict(_by_field(audit.run_records, "mode")),
            "profile": dict(_by_field(audit.run_records, "profile_id")),
            "date": dict(_by_date(audit.run_records)),
        },
        "runs": [
            {
                "run_id": record.run_id,
                "size_bytes": record.size_bytes,
                "profile_id": record.profile_id,
                "mode": record.mode,
                "status_bucket": record.status_bucket,
                "retention_class": record.retention_class,
                "publication_ready_status": record.publication_ready_status,
                "evidence_mode": record.evidence_mode,
                "timestamp_utc": record.timestamp_utc.isoformat() if record.timestamp_utc else None,
                "reasons": record.reasons,
                "markers": {
                    "keep": record.marker_keep,
                    "protected": record.marker_protected,
                    "cleanup_candidate": record.marker_cleanup_candidate,
                },
            }
            for record in audit.run_records
        ],
    }


def render_retention_audit(audit: RetentionAudit) -> str:
    """Render a human-readable dry-run retention report."""
    lines: list[str] = []
    lines.append("Output Retention Audit (dry-run)")
    lines.append(f"Generated UTC: {audit.generated_at_utc.isoformat()}")
    lines.append(f"Output root: {audit.output_dir}")
    lines.append("")
    lines.append("Structure")
    lines.append(f"- Run folders: {len(audit.run_records)}")
    lines.append(f"- output/runs: {_human_size(audit.total_runs_size_bytes)}")
    lines.append(f"- output/diagnostics: {_human_size(audit.diagnostics_size_bytes)}")
    lines.append(f"- output/bundles: {_human_size(audit.bundles_size_bytes)}")
    lines.append(f"- output/latest: {_human_size(audit.latest_size_bytes)}")
    lines.append(f"- output/promoted: {_human_size(audit.promoted_size_bytes)}")
    lines.append(f"- output/reports: {_human_size(audit.reports_size_bytes)}")
    lines.append("")
    lines.append("Pointers and policy")
    lines.append(f"- latest run: {audit.latest_run_id or 'unknown'}")
    lines.append(f"- promoted run: {audit.promoted_run_id or 'unknown'}")
    lines.append(
        "- policy:"
        f" recent_days={audit.policy.recent_days},"
        f" keep_last_full_per_profile={audit.policy.keep_last_full_per_profile},"
        f" keep_last_dev_runs_total={audit.policy.keep_last_dev_runs_total}"
    )
    lines.append("")
    lines.append("Counts")
    for label, field_name in (
        ("retention", "retention_class"),
        ("status", "status_bucket"),
        ("mode", "mode"),
        ("profile", "profile_id"),
    ):
        lines.append(f"- by {label}:")
        for key, count in _by_field(audit.run_records, field_name):
            lines.append(f"  - {key}: {count}")
    lines.append("- by date:")
    for key, count in _by_date(audit.run_records):
        lines.append(f"  - {key}: {count}")
    lines.append("")
    lines.append("Largest run folders")
    for record in sorted(audit.run_records, key=lambda item: item.size_bytes, reverse=True)[:10]:
        lines.append(
            f"- {record.run_id}: {_human_size(record.size_bytes)}"
            f" | {record.retention_class}"
            f" | {record.profile_id}"
            f" | {record.status_bucket}"
        )
    lines.append("")
    lines.append(f"Reclaimable estimate (disposable only): {_human_size(audit.reclaimable_bytes)}")
    disposable = [record for record in audit.run_records if record.retention_class == "disposable"]
    if disposable:
        lines.append("Disposable candidates")
        for record in disposable:
            lines.append(
                f"- {record.run_id}: {_human_size(record.size_bytes)}"
                f" | profile={record.profile_id}"
                f" | mode={record.mode}"
                f" | status={record.status_bucket}"
                f" | reasons={'; '.join(record.reasons)}"
            )
    else:
        lines.append("Disposable candidates")
        lines.append("- none under the current conservative policy")
    lines.append("")
    lines.append("Protected runs")
    for record in [r for r in audit.run_records if r.retention_class == "protected"][:20]:
        lines.append(f"- {record.run_id}: {', '.join(record.reasons)}")
    lines.append("")
    lines.append("Marker files supported")
    lines.append(f"- {KEEP_MARKER}: pinned; never auto-delete")
    lines.append(f"- {PROTECTED_MARKER}: protected; never auto-delete")
    lines.append(f"- {CLEANUP_CANDIDATE_MARKER}: advisory marker only")
    lines.append("")
    lines.append("No files were deleted. To add destructive cleanup later, consume this audit output first.")
    return "\n".join(lines) + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    """Create CLI parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="",
        help="Output root override (default: configured output root).",
    )
    parser.add_argument(
        "--recent-days",
        type=int,
        default=7,
        help="Keep runs newer than this many days as 'recent'.",
    )
    parser.add_argument(
        "--keep-last-full-per-profile",
        type=int,
        default=3,
        help="Keep this many complete runs per profile as 'recent'.",
    )
    parser.add_argument(
        "--keep-last-dev-runs-total",
        type=int,
        default=5,
        help="Keep this many dev/smoke runs total as 'recent'.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of text.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else output_paths.output_root()
    )
    policy = RetentionPolicy(
        recent_days=max(0, int(args.recent_days)),
        keep_last_full_per_profile=max(0, int(args.keep_last_full_per_profile)),
        keep_last_dev_runs_total=max(0, int(args.keep_last_dev_runs_total)),
    )
    audit = audit_output_retention(output_dir, policy=policy)
    if args.json:
        print(json.dumps(audit_to_dict(audit), indent=2, sort_keys=True))
    else:
        print(render_retention_audit(audit), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
