"""Summarize high-signal issues from the latest run's log surface."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.runtime_bootstrap  # noqa: F401

from obsidiandroid.common.output_paths import diagnostics_root, project_logs_root


DEFAULT_MD = Path("output") / "diagnostics" / "run_log_issue_summary_latest.md"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
WARNING_LINE_RE = re.compile(r"\[WARNING\]\s*(.+)")
INFO_LINE_RE = re.compile(r"\[INFO\]\s*(.+)")
STAGE_TIMING_RE = re.compile(r"event='stage_timing'.*?duration_sec=([0-9.]+).*?stage='([^']+)'")
EVENT_RE = re.compile(r"event='([^']+)'")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def read_latest_run_pointer(path: Path | None = None) -> dict[str, str]:
    pointer_path = path or diagnostics_root() / "latest_run_pointer.json"
    payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    return {
        "run_id": str(payload.get("run_id", "")).strip(),
        "run_root": str(payload.get("run_root", "")).strip(),
    }


def parse_console_warnings(console_log: Path) -> Counter[str]:
    warnings: Counter[str] = Counter()
    if not console_log.is_file():
        return warnings
    for raw_line in console_log.read_text(encoding="utf-8", errors="replace").splitlines():
        line = strip_ansi(raw_line)
        match = WARNING_LINE_RE.search(line)
        if match:
            warnings[match.group(1).strip()] += 1
    return warnings


def parse_console_info_flags(console_log: Path) -> Counter[str]:
    info_flags: Counter[str] = Counter()
    if not console_log.is_file():
        return info_flags
    for raw_line in console_log.read_text(encoding="utf-8", errors="replace").splitlines():
        line = strip_ansi(raw_line)
        match = INFO_LINE_RE.search(line)
        if not match:
            continue
        body = match.group(1).strip()
        if "[COHORT_LOCK]" in body or "[SMOTE]" in body or "[LINEAGE_GATE]" in body or "[COVERAGE]" in body:
            info_flags[body] += 1
    return info_flags


def parse_stage_timings(pipeline_log: Path) -> list[tuple[str, float]]:
    timings: list[tuple[str, float]] = []
    if not pipeline_log.is_file():
        return timings
    for line in pipeline_log.read_text(encoding="utf-8", errors="replace").splitlines():
        match = STAGE_TIMING_RE.search(line)
        if not match:
            continue
        timings.append((match.group(2), float(match.group(1))))
    timings.sort(key=lambda item: item[1], reverse=True)
    return timings


def parse_event_counts(log_path: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not log_path.is_file():
        return counts
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = EVENT_RE.search(line)
        if match:
            counts[match.group(1)] += 1
    return counts


def build_report(
    *,
    run_id: str,
    console_log: Path,
    pipeline_log: Path,
    machine_learning_log: Path,
    authority_log: Path,
    temporal_log: Path,
    error_log: Path,
) -> str:
    warning_counts = parse_console_warnings(console_log)
    info_flags = parse_console_info_flags(console_log)
    stage_timings = parse_stage_timings(pipeline_log)
    ml_events = parse_event_counts(machine_learning_log)
    pipeline_events = parse_event_counts(pipeline_log)
    authority_events = parse_event_counts(authority_log)
    temporal_events = parse_event_counts(temporal_log)
    error_exists = error_log.is_file()

    lines = [
        "# Run Log Issue Summary",
        "",
        f"- run_id: `{run_id}`",
        f"- console log: `{console_log}`",
        f"- pipeline log: `{pipeline_log}`",
        f"- machine learning log: `{machine_learning_log}`",
        f"- authority alerts log: `{authority_log}`",
        f"- temporal alerts log: `{temporal_log}`",
        f"- error log present: `{error_exists}`",
        "",
        "## Main issues",
        "",
    ]

    if warning_counts:
        for message, count in warning_counts.most_common(12):
            lines.append(f"- `{count}x` {message}")
    else:
        lines.append("- No console warnings captured.")

    if info_flags:
        lines.extend(["", "## Important info flags", ""])
        for message, count in info_flags.most_common(10):
            lines.append(f"- `{count}x` {message}")

    if stage_timings:
        lines.extend(["", "## Slowest stages", "", "| Stage | Duration (sec) |", "|---|---:|"])
        for stage, seconds in stage_timings[:10]:
            lines.append(f"| `{stage}` | {seconds:.2f} |")

    structured_risk_events = Counter()
    for key in (
        "smote_enabled_evidence_mode",
        "smote_skipped_evidence_mode",
        "split_stratification_disabled",
        "temporal_profile_non_temporal_split",
    ):
        if ml_events.get(key):
            structured_risk_events[key] = ml_events[key]
    for key in ("cohort_lock_drift",):
        if pipeline_events.get(key):
            structured_risk_events[key] = pipeline_events[key]
    for key in (
        "taxonomy_mismatch_summary",
        "family_prediction_error_summary",
        "taxonomy_noncanonical_dominance",
    ):
        if authority_events.get(key):
            structured_risk_events[key] = authority_events[key]
    if structured_risk_events:
        lines.extend(["", "## Structured risk events", "", "| Event | Count |", "|---|---:|"])
        for event_name, count in structured_risk_events.most_common():
            lines.append(f"| `{event_name}` | {count} |")

    if authority_events:
        lines.extend(["", "## Authority alert events", "", "| Event | Count |", "|---|---:|"])
        for event_name, count in authority_events.most_common():
            lines.append(f"| `{event_name}` | {count} |")

    if temporal_events:
        lines.extend(["", "## Temporal alert events", "", "| Event | Count |", "|---|---:|"])
        for event_name, count in temporal_events.most_common():
            lines.append(f"| `{event_name}` | {count} |")

    if not error_exists:
        lines.extend(
            [
                "",
                "## Gaps",
                "",
                "- `error.log` is not present for this run, which likely means the run had no structured `ERROR` events or some failure paths still log only through console warnings.",
            ]
        )

    lines.extend(
        [
            "",
            "## Recommendations",
            "",
            "- Treat repeated `SMOTE` warnings in evidence/paper mode as a policy issue, not just a model detail.",
            "- Treat `COHORT_LOCK` drift warnings as a reproducibility issue requiring explicit review.",
            "- Treat taxonomy/type mapping warnings as authority/rendering problems until the view-backed authority path is fully consumed everywhere.",
            "- Review the slowest stages first when optimizing operator experience and troubleshooting runtime cost.",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", default="", help="Explicit run_id to inspect. Defaults to latest pointer.")
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD, help="Markdown report output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_id = str(args.run_id or "").strip()
    if not run_id:
        pointer = read_latest_run_pointer()
        run_id = pointer["run_id"]
    if not run_id:
        print("[WARN] No latest run ID available.")
        return 1

    runtime_dir = project_logs_root() / "runtime" / run_id
    console_candidates = sorted(runtime_dir.glob("pipeline_runtime*.log"))
    console_log = console_candidates[-1] if console_candidates else runtime_dir / f"pipeline_runtime_console_{run_id}.log"
    pipeline_log = runtime_dir / "pipeline_orchestration.log"
    machine_learning_log = runtime_dir / "machine_learning.log"
    authority_log = project_logs_root() / "label_authority_alerts.log"
    temporal_log = project_logs_root() / "temporal_readiness_alerts.log"
    error_log = project_logs_root() / "error.log"

    report = build_report(
        run_id=run_id,
        console_log=console_log,
        pipeline_log=pipeline_log,
        machine_learning_log=machine_learning_log,
        authority_log=authority_log,
        temporal_log=temporal_log,
        error_log=error_log,
    )

    args.md_out.parent.mkdir(parents=True, exist_ok=True)
    args.md_out.write_text(report, encoding="utf-8")
    print(f"[OK] wrote {args.md_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
