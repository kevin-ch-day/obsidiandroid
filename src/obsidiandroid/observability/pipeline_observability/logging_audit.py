"""Emit ``logging_audit.md`` + ``logging_audit.csv`` (Pass 1 inventory)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from obsidiandroid.observability.pipeline_observability.taxonomy import LogCategory, LogSeverity


def write_logging_audit_artifacts(diagnostics_dir: Path, *, run_id: str | None = None) -> tuple[Path, Path]:
    """Summarize today's logging posture and remediation backlog."""

    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    md_path = diagnostics_dir / "logging_audit.md"
    csv_path = diagnostics_dir / "logging_audit.csv"

    rid_note = run_id or "n/a"

    md_lines = [
        "# Logging & observability audit (generated)",
        "",
        f"_Run anchor: `{rid_note}` (informational)._",
        "",
        "## Severity model (canonical)",
        "",
        "| Level | Meaning |",
        "|-------|---------|",
        "| `INFO` | Normal progress milestones |",
        "| `WARNING` | Operational caveat; run may still be scientifically usable |",
        "| `RESEARCH_WARNING` | May bias interpretation — flag in reviewer notes |",
        "| `PAPER_BLOCKER` | Publication/evidence contract violated when publication-ready mode expects pass |",
        "| `ERROR` | Stage degraded or aborted sub-step |",
        "| `FATAL` | Runner cannot safely continue core objectives |",
        "",
        "## Event taxonomy (canonical categories)",
        "",
        "Emitted to `pipeline_events.jsonl` plus terminal hints where wired:",
        "",
        ", ".join(f"`{c.value}`" for c in LogCategory),
        "",
        "## Current sinks (today)",
        "",
        "- **Terminal:** `obsidiandroid.cli.ui.display` (`print_*`, `[PIPELINE]` / `[EVIDENCE]` prefixes) mixed with contextual lines.",
        "- **Structured file:** `obsidiandroid.observability.logging.logger.log_event` + `PIPELINE_MAIN_LOGGER` (category `pipeline_orchestration.log`).",
        "- **Diagnostics:** run-scoped + `.latest` mirror policies via `obsidiandroid.common.output_hygiene`.",
        "- **Compliance:** `paper_mode_compliance_report_{run_id}.json` (compatibility filename; gates when publication/evidence expectations apply).",
        "",
        "## Known gaps (prioritized backlog)",
        "",
        "1. Duplicate context lines: `[PIPELINE] Paths` repeats path roots already in `[CTX]` per stage.",
        "2. Vague skips: `[AUDIT] Research validity bundle skipped` loses stack cause in operator view — now duplicated into observability partial-failure ledger.",
        "3. Silent continues: legacy AV subprocess paths sometimes log WARN and empty frames—require `DATA_POPULATION_CHANGE` emission when row counts drop sharply.",
        "4. Severity drift: `[DUPLICATE]` warnings are informational outside publication-ready mode but `[PAPER]` raises—classification should map to taxonomy severities explicitly.",
        "5. Latest vs run-scoped: operators must read both `*_latest.*` mirrors and `{run_id}` suffixed originals—`run_evidence_index.md` indexes canonical paths.",
        "",
        "## Artifacts introduced by observability sprint",
        "",
        "- `pipeline_stage_summary.csv` — one row per completed/skipped/degraded stage.",
        "- `pipeline_stage_summary.md` — human-readable rollup.",
        "- `pipeline_events.jsonl` — append-only timeline (`STAGE_*`, `DATA_POPULATION_CHANGE`, etc.).",
        "- `run_observability_summary.json` — **authoritative** run-level rollup for automation, terminal **Run Health**, and `run_evidence_index.md` mirror.",
        "- `logging_audit.md` / `logging_audit.csv` — this taxonomy + backlog inventory.",
        "- `partial_failures.md` — non-fatal stage errors (audits/ablations/evidence readiness).",
        "",
    ]

    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    backlog_rows: list[dict[str, Any]] = [
        {
            "area": "taxonomy",
            "issue": "Unify prefixes under structured categories instead of free-form [PIPELINE] tags.",
            "severity": LogSeverity.INFO.value,
            "status": "IN_PROGRESS",
        },
        {
            "area": "stage_boundary",
            "issue": "Emit STAGE_START / STAGE_END pairs for timeline reconstruction from JSONL.",
            "severity": LogSeverity.INFO.value,
            "status": "IMPLEMENTED_JSONL_STAGE_START_AND_COMPLETION_ROWS",
        },
        {
            "area": "stage_summary",
            "issue": "Emit explicit PASS_WITH_WARNINGS when warnings exist without failure.",
            "severity": LogSeverity.WARNING.value,
            "status": "IMPLEMENTED",
        },
        {
            "area": "data_changes",
            "issue": "Log governed→feature-matrix→aligned→train/test transitions with artifact pointers.",
            "severity": LogSeverity.RESEARCH_WARNING.value,
            "status": "IMPLEMENTED",
        },
        {
            "area": "paper_status",
            "issue": "Never print PASS for publication-ready status when evidence mode is off.",
            "severity": LogSeverity.PAPER_BLOCKER.value,
            "status": "RULE_ENFORCED",
        },
        {
            "area": "failures",
            "issue": "Surface audit/ablation skips in aggregate pipeline verdict instead of masking as complete.",
            "severity": LogSeverity.ERROR.value,
            "status": "IMPLEMENTED",
        },
    ]
    keys = ["area", "issue", "severity", "status"]
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for row in backlog_rows:
            w.writerow({k: row.get(k, "") for k in keys})

    return md_path, csv_path


__all__ = ["write_logging_audit_artifacts"]
