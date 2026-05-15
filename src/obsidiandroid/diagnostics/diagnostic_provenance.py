"""Run-scoped provenance ledger for diagnostics and post-run enrichments."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from obsidiandroid.diagnostics import output_artifact_policy


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _coerce_path_strings(paths: list[str] | tuple[str, ...] | None) -> list[str]:
    out: list[str] = []
    for raw in list(paths or []):
        text = str(raw or "").strip()
        if text:
            out.append(text)
    return out


def _relative_or_absolute(path: Path, *, run_root: Path) -> tuple[str, bool]:
    try:
        return (path.resolve().relative_to(run_root.resolve()).as_posix(), True)
    except ValueError:
        return (str(path.resolve()).replace("\\", "/"), False)


def _output_root_from_run_root(run_root: Path) -> Path:
    resolved = Path(run_root).resolve()
    if "runs" in resolved.parts:
        idx = resolved.parts.index("runs")
        return Path(*resolved.parts[:idx]).resolve()
    return resolved.parent.resolve()


def _run_metadata_from_diagnostics_dir(path: Path) -> tuple[Path | None, Path | None, str | None]:
    resolved = Path(path).resolve()
    parts = resolved.parts
    if "runs" not in parts:
        return (None, None, None)
    idx = parts.index("runs")
    if idx + 1 >= len(parts):
        return (None, None, None)
    run_root = Path(*parts[: idx + 2]).resolve()
    run_id = parts[idx + 1]
    diagnostics_dir = run_root / "diagnostics"
    return (run_root, diagnostics_dir, run_id)


def resolve_post_run_enrichment_target(*, diagnostics_dir: Path, audit_id: str) -> dict[str, Any]:
    """Resolve where post-run enrichment artifacts should live.

    If ``diagnostics_dir`` points at a canonical run diagnostics root, post-run artifacts
    are routed under ``diagnostics/post_run_enrichments/<audit_id>/`` while provenance
    remains recorded at the canonical diagnostics root.
    """
    requested = Path(diagnostics_dir).resolve()
    run_root, canonical_diag, run_id = _run_metadata_from_diagnostics_dir(requested)

    if run_root is None or canonical_diag is None or run_id is None:
        return {
            "artifact_dir": requested,
            "provenance_dir": requested,
            "run_root": requested,
            "source_run_id": None,
            "is_run_scoped_enrichment": False,
        }

    rel_parts = requested.relative_to(run_root).parts
    if len(rel_parts) >= 3 and rel_parts[0] == "diagnostics" and rel_parts[1] == "post_run_enrichments":
        return {
            "artifact_dir": requested,
            "provenance_dir": canonical_diag,
            "run_root": run_root,
            "source_run_id": run_id,
            "is_run_scoped_enrichment": True,
        }
    if requested == canonical_diag:
        return {
            "artifact_dir": canonical_diag / "post_run_enrichments" / str(audit_id),
            "provenance_dir": canonical_diag,
            "run_root": run_root,
            "source_run_id": run_id,
            "is_run_scoped_enrichment": True,
        }
    return {
        "artifact_dir": requested,
        "provenance_dir": requested,
        "run_root": run_root,
        "source_run_id": run_id,
        "is_run_scoped_enrichment": False,
    }


def list_post_run_enrichment_dirs(diagnostics_dir: Path) -> list[Path]:
    """Return post-run enrichment audit directories under a run diagnostics root."""
    base = Path(diagnostics_dir).resolve() / "post_run_enrichments"
    if not base.is_dir():
        return []
    return sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.name)


def latest_post_run_enrichment_dir(diagnostics_dir: Path) -> Path | None:
    """Return the newest post-run enrichment directory, if one exists."""
    dirs = list_post_run_enrichment_dirs(diagnostics_dir)
    return dirs[-1] if dirs else None


def latest_post_run_entry(diagnostics_dir: Path) -> dict[str, Any] | None:
    """Return the newest recorded post-run provenance entry for a run diagnostics root."""
    diagnostics_dir = Path(diagnostics_dir).resolve()
    payload = _load_payload(diagnostics_dir / "diagnostic_provenance.json", run_id="")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return None
    post_entries = [row for row in entries if isinstance(row, dict) and not bool(row.get("generated_during_pipeline", False))]
    if not post_entries:
        return None
    return sorted(post_entries, key=lambda row: str(row.get("generated_at_utc", "")))[-1]


def _load_payload(path: Path, *, run_id: str) -> dict[str, Any]:
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("schema_version", "1.0")
                data.setdefault("run_id", run_id)
                entries = data.get("entries")
                if not isinstance(entries, list):
                    data["entries"] = []
                return data
        except Exception:
            pass
    return {"schema_version": "1.0", "run_id": run_id, "entries": []}


def record_diagnostic_provenance(
    *,
    diagnostics_dir: Path,
    run_root: Path,
    run_id: str,
    entry_id: str,
    generated_during_pipeline: bool,
    source_command: str,
    source_run_id: str,
    artifact_paths: list[str] | tuple[str, ...] | None,
    lifecycle_class: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Append or replace one provenance entry in ``diagnostic_provenance.json``."""
    diagnostics_dir = Path(diagnostics_dir)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    out_path = diagnostics_dir / "diagnostic_provenance.json"
    payload = _load_payload(out_path, run_id=str(run_id))

    artifact_rows: list[dict[str, Any]] = []
    for raw in _coerce_path_strings(artifact_paths):
        path = Path(raw)
        rel, within_run_root = _relative_or_absolute(path, run_root=Path(run_root))
        base = Path(run_root) if within_run_root else _output_root_from_run_root(Path(run_root))
        artifact_meta = output_artifact_policy.classify_file(
            path,
            base=base,
        )
        artifact_rows.append(
            {
                "path": rel,
                "within_run_root": bool(within_run_root),
                "artifact_bucket": artifact_meta.get("artifact_bucket"),
                "lifecycle_class": str(
                    lifecycle_class
                    or artifact_meta.get("lifecycle_class")
                    or "diagnostics_optional"
                ),
            }
        )

    entry = {
        "entry_id": str(entry_id),
        "generated_during_pipeline": bool(generated_during_pipeline),
        "source_command": str(source_command),
        "source_run_id": str(source_run_id),
        "generated_at_utc": _utc_now(),
        "lifecycle_class": str(
            lifecycle_class
            or ("canonical_run_evidence" if generated_during_pipeline else "post_run_enrichment")
        ),
        "artifact_count": len(artifact_rows),
        "artifacts": artifact_rows,
    }
    if isinstance(extra, dict) and extra:
        entry.update(extra)

    entries = [row for row in payload.get("entries", []) if str(row.get("entry_id", "")) != str(entry_id)]
    entries.append(entry)
    payload["entries"] = entries
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path


__all__ = [
    "latest_post_run_enrichment_dir",
    "latest_post_run_entry",
    "list_post_run_enrichment_dirs",
    "record_diagnostic_provenance",
    "resolve_post_run_enrichment_target",
]
