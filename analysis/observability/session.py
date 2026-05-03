"""Buffered and append-only observability events for pipeline runs."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analysis.observability.taxonomy import LogCategory, LogSeverity

_PIPELINE_ORDER = [
    "preflight",
    "samples",
    "av_pipeline",
    "vendor_metadata",
    "engine_weights",
    "feature_matrix",
    "alignment",
    "training",
    "ablation",
    "permission_trends",
    "label_resolution",
    "research_validity",
    "hostile_audit",
    "manifest_finalization",
]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_severity(sev: LogSeverity | str) -> LogSeverity:
    if isinstance(sev, LogSeverity):
        return sev
    try:
        return LogSeverity(str(sev))
    except ValueError:
        return LogSeverity.WARNING


class PipelineObservabilitySession:
    """Per-run diagnostics writer under ``RUNTIME_DIAGNOSTICS_DIR``.

    Writes:
    - ``pipeline_events.jsonl`` (append)
    - ``pipeline_stage_summary.csv`` (append)

    Markdown + status JSON regeneration: ``finalize_pipeline_observability``.
    """

    CSV_FIELDS = [
        "run_id",
        "stage_name",
        "start_time",
        "end_time",
        "duration_sec",
        "status",
        "input_rows",
        "output_rows",
        "input_features",
        "output_features",
        "rows_added",
        "rows_removed",
        "features_added",
        "features_removed",
        "major_warnings",
        "paper_blocker",
        "artifacts_written",
        "artifacts_skipped",
        "next_stage_allowed",
        "extras_json",
    ]

    def __init__(self, *, diagnostics_dir: Path, run_id: str) -> None:
        self.diagnostics_dir = Path(diagnostics_dir)
        self.run_id = str(run_id)
        self._jsonl_path = self.diagnostics_dir / "pipeline_events.jsonl"
        self._csv_path = self.diagnostics_dir / "pipeline_stage_summary.csv"
        self._completed_stage_names: set[str] = set()
        self._warnings: list[dict[str, Any]] = []
        self._paper_blockers: list[str] = []
        self._partial_failures: list[dict[str, Any]] = []

    @staticmethod
    def pipeline_order_full() -> list[str]:
        return list(_PIPELINE_ORDER)

    def emit_jsonl(
        self,
        category: LogCategory | str,
        *,
        severity: LogSeverity | str = LogSeverity.INFO,
        message: str = "",
        **fields: Any,
    ) -> None:
        cat = category.value if isinstance(category, LogCategory) else str(category)
        sev_obj = _coerce_severity(severity)
        obj: dict[str, Any] = {
            "timestamp_utc": _utc_iso(),
            "run_id": self.run_id,
            "category": cat,
            "severity": sev_obj.value,
            "message": message,
        }
        for k in sorted(fields):
            v = fields[k]
            obj[k] = (
                v
                if isinstance(v, (str, int, float, bool)) or isinstance(v, (list, dict)) or v is None
                else str(v)
            )
        self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(obj, separators=(",", ":"), sort_keys=False, default=str) + "\n"
        try:
            with self._jsonl_path.open("a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass

    def emit_stage_start(self, stage_name: str, **fields: Any) -> None:
        """Mark the beginning of a named pipeline stage for JSONL readers."""
        self.emit_jsonl(
            LogCategory.STAGE_START,
            severity=LogSeverity.INFO,
            message=str(stage_name),
            stage=str(stage_name),
            **fields,
        )

    def emit_artifact_written(self, path: Path | str, *, detail: str = "") -> None:
        """Log a concrete artifact emitted to disk."""
        p = str(path).strip()
        self.emit_jsonl(
            LogCategory.ARTIFACT_WRITE,
            severity=LogSeverity.INFO,
            message=p,
            path=p,
            detail=str(detail) if detail else "",
        )

    def emit_artifact_skipped(self, *, reason: str, path_hint: str = "", detail: str = "") -> None:
        """Log an expected-but-missing artifact or skipped exporter."""
        self.emit_jsonl(
            LogCategory.ARTIFACT_SKIP,
            severity=LogSeverity.WARNING,
            message=str(reason),
            path_hint=str(path_hint) if path_hint else "",
            detail=str(detail) if detail else "",
        )

    def emit_stage_completion(
        self,
        stage_name: str,
        *,
        status: str,
        duration_sec: float,
        input_rows: int | str | None = None,
        output_rows: int | str | None = None,
        input_features: int | str | None = None,
        output_features: int | str | None = None,
        rows_removed: str | None = None,
        rows_added: str | None = None,
        features_removed: str | None = None,
        features_added: str | None = None,
        major_warnings: str = "",
        paper_blocker_stage: bool = False,
        artifacts_written_count: str = "",
        artifacts_skipped: str = "",
        next_stage_allowed: bool | str = True,
        extras: dict[str, Any] | None = None,
    ) -> None:
        """Append one CSV row + STAGE_END JSONL marker."""
        extras = extras or {}
        self._completed_stage_names.add(stage_name)
        ts_end = _utc_iso()
        start_time_iso = str(extras.pop("start_time_iso", "") or "").strip()

        extras_json = ""
        try:
            extras_json = json.dumps(extras, sort_keys=True, default=str)[:4000] if extras else ""
        except Exception:
            extras_json = ""

        if isinstance(next_stage_allowed, bool):
            nsa = "true" if next_stage_allowed else "false"
        else:
            nsa = str(next_stage_allowed)

        row = {
            "run_id": self.run_id,
            "stage_name": stage_name,
            "start_time": start_time_iso,
            "end_time": ts_end,
            "duration_sec": round(float(duration_sec), 4),
            "status": str(status),
            "input_rows": "" if input_rows is None else str(input_rows),
            "output_rows": "" if output_rows is None else str(output_rows),
            "input_features": "" if input_features is None else str(input_features),
            "output_features": "" if output_features is None else str(output_features),
            "rows_added": rows_added if rows_added is not None else "",
            "rows_removed": rows_removed if rows_removed is not None else "",
            "features_added": features_added if features_added is not None else "",
            "features_removed": features_removed if features_removed is not None else "",
            "major_warnings": major_warnings,
            "paper_blocker": "true" if paper_blocker_stage else "false",
            "artifacts_written": str(artifacts_written_count) if artifacts_written_count != "" else "",
            "artifacts_skipped": artifacts_skipped or "",
            "next_stage_allowed": nsa,
            "extras_json": extras_json,
        }

        self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
        csv_flag = self._csv_path.exists() and self._csv_path.stat().st_size > 0
        try:
            with self._csv_path.open("a", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=self.CSV_FIELDS)
                if not csv_flag:
                    w.writeheader()
                w.writerow(row)
        except OSError:
            pass

        self.emit_jsonl(
            LogCategory.STAGE_END,
            severity=LogSeverity.INFO,
            message=stage_name,
            status=status,
            duration_sec=round(duration_sec, 4),
        )

    def add_warning(
        self,
        message: str,
        *,
        severity: LogSeverity | str = LogSeverity.WARNING,
        category: LogCategory | str = LogCategory.WARNING_OPERATIONAL,
        paper_blocker: bool = False,
        stage_hint: str = "",
    ) -> None:
        """Record warnings with optional paper-blocker escalation."""
        sev_obj = _coerce_severity(severity if not paper_blocker else LogSeverity.PAPER_BLOCKER)
        sev_str = LogSeverity.PAPER_BLOCKER.value if paper_blocker else sev_obj.value
        rec = {
            "severity": sev_str,
            "message": message,
            "paper_blocker": bool(paper_blocker),
            "stage_hint": stage_hint or "",
            "timestamp_utc": _utc_iso(),
        }
        self._warnings.append(rec)
        cat_enum = category if isinstance(category, LogCategory) else LogCategory.WARNING_OPERATIONAL
        emit_cat = (
            LogCategory.WARNING_RESEARCH
            if sev_str == LogSeverity.RESEARCH_WARNING.value or cat_enum == LogCategory.WARNING_RESEARCH
            else cat_enum
        )
        try:
            self.emit_jsonl(
                emit_cat,
                severity=LogSeverity.PAPER_BLOCKER if paper_blocker else sev_obj,
                message=message,
                stage_hint=stage_hint,
                paper_blocker=paper_blocker,
            )
        except Exception:
            pass
        if paper_blocker or sev_str == LogSeverity.PAPER_BLOCKER.value:
            self._paper_blockers.append(message)
            try:
                self.emit_jsonl(LogCategory.PAPER_STATUS, severity=LogSeverity.PAPER_BLOCKER, message=message)
            except Exception:
                pass

    def record_partial_failure(self, *, stage: str, error: str, recoverable: bool = True) -> None:
        """Degraded stage (partial CSV/MD exported)."""
        self._partial_failures.append(
            {
                "stage": stage,
                "error": str(error),
                "recoverable": bool(recoverable),
                "timestamp_utc": _utc_iso(),
            }
        )
        self.emit_jsonl(
            LogCategory.ERROR_RECOVERABLE if recoverable else LogCategory.ERROR_FATAL,
            severity=LogSeverity.ERROR,
            stage=stage,
            message=str(error),
        )

    def log_population_transition(
        self,
        *,
        transition: str,
        previous_count: int | None,
        new_count: int | None,
        reason: str,
        artifact_path: str = "",
    ) -> None:
        prev_val = previous_count if previous_count is not None else ""
        new_val = new_count if new_count is not None else ""
        delta = ""
        pct = ""
        try:
            if isinstance(prev_val, int) or (isinstance(prev_val, str) and str(prev_val).isdigit()):
                p = float(prev_val)
                n = float(new_val if new_val != "" else p)
                d = int(n - p)
                delta = str(d)
                if p:
                    pct = str(round(100.0 * (d / p), 6))
        except Exception:
            pass
        self.emit_jsonl(
            LogCategory.DATA_POPULATION_CHANGE,
            severity=LogSeverity.INFO,
            message=transition,
            previous=str(prev_val),
            new=str(new_val),
            delta=delta,
            percent_removed_or_change=pct,
            reason=reason,
            artifact=str(artifact_path),
        )

    def log_schema_change(
        self,
        *,
        stage_hint: str,
        previous_cols: int | None,
        new_cols: int | None,
        reason: str,
        artifact_path: str = "",
    ) -> None:
        pf = "" if previous_cols is None else str(int(previous_cols))
        nf = "" if new_cols is None else str(int(new_cols))
        self.emit_jsonl(
            LogCategory.FEATURE_SCHEMA_CHANGE,
            severity=LogSeverity.INFO,
            stage_hint=stage_hint,
            previous_features=pf,
            new_features=nf,
            reason=reason,
            artifact=str(artifact_path),
        )

    def log_train_test_split_allocation(
        self,
        *,
        pool_rows: int | None,
        train_rows: int | None,
        test_rows: int | None,
        reason: str = "",
        artifact_path: str = "",
    ) -> None:
        """Train/test counts after the supervised training pool is fixed."""
        self.emit_jsonl(
            LogCategory.LABEL_FILTERING,
            severity=LogSeverity.INFO,
            message="training_pool_to_train_and_test_holdout",
            pool_rows="" if pool_rows is None else int(pool_rows),
            train_rows="" if train_rows is None else int(train_rows),
            test_rows="" if test_rows is None else int(test_rows),
            reason=str(reason or ""),
            artifact=str(artifact_path or ""),
        )

    # --- aggregation accessors for finalize / terminal ---
    def completed_stages(self) -> set[str]:
        return set(self._completed_stage_names)

    def warnings_snapshot(self) -> list[dict[str, Any]]:
        return list(self._warnings)

    def paper_blockers_snapshot(self) -> list[str]:
        return list(dict.fromkeys(self._paper_blockers))

    def partial_failures_snapshot(self) -> list[dict[str, Any]]:
        return list(self._partial_failures)


__all__ = ["PipelineObservabilitySession"]
