"""Paper export registry helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from obsidiandroid.pipeline.manifest.hashing import sha256_hex


def build_paper_registry_payload(
    *,
    run_root: Path,
    run_id: str,
    contract_version: str,
    figure_registry_rows: list[dict[str, Any]],
    table_registry_rows: list[dict[str, Any]],
    latex_paths: dict[str, str],
    blocked_non_paper_ids: set[str],
) -> dict[str, Any]:
    """Build the unified paper artifact registry payload."""
    artifacts_out: list[dict[str, Any]] = []
    for row in figure_registry_rows:
        artifact_id = str(row.get("figure_id", "")).strip()
        temp_destination_path = str(row.get("destination_path", "")).strip()
        destination_filename = str(row.get("destination_filename", "")).strip()
        destination_path = (
            str((run_root / "paper_exports" / "figures" / destination_filename).resolve())
            if destination_filename
            else ""
        )
        source_path = str(row.get("source_path", "")).strip()
        sha = (
            sha256_hex(Path(temp_destination_path).read_bytes())
            if temp_destination_path and Path(temp_destination_path).exists()
            else ""
        )
        artifacts_out.append(
            {
                "artifact_id": artifact_id,
                "artifact_type": "figure",
                "run_id": str(run_id),
                "source_path": source_path,
                "destination_path": destination_path,
                "sha256": sha,
                "paper_allowed": True,
                "contract_version": str(contract_version),
            }
        )
    for row in table_registry_rows:
        artifact_id = str(row.get("table_id", "")).strip()
        temp_destination_path = str(row.get("destination_path", "")).strip()
        destination_filename = str(row.get("destination_filename", "")).strip()
        destination_path = (
            str((run_root / "paper_exports" / "tables" / destination_filename).resolve())
            if destination_filename
            else ""
        )
        source_path = str(row.get("source_path", "")).strip()
        sha = (
            sha256_hex(Path(temp_destination_path).read_bytes())
            if temp_destination_path and Path(temp_destination_path).exists()
            else ""
        )
        latex_name = str(latex_paths.get(artifact_id, "")).strip()
        artifacts_out.append(
            {
                "artifact_id": artifact_id,
                "artifact_type": "table",
                "run_id": str(run_id),
                "source_path": source_path,
                "destination_path": destination_path,
                "sha256": sha,
                "paper_allowed": True,
                "contract_version": str(contract_version),
                "latex_path": (
                    str((run_root / "paper_exports" / "tables_latex" / latex_name).resolve())
                    if latex_name
                    else ""
                ),
            }
        )
    for blocked_id in sorted(blocked_non_paper_ids):
        artifacts_out.append(
            {
                "artifact_id": blocked_id,
                "artifact_type": "blocked_non_paper",
                "run_id": str(run_id),
                "source_path": "",
                "destination_path": "",
                "sha256": "",
                "paper_allowed": False,
                "contract_version": str(contract_version),
            }
        )
    return {
        "run_id": str(run_id),
        "contract_version": str(contract_version),
        "artifacts": sorted(artifacts_out, key=lambda item: str(item.get("artifact_id", ""))),
    }


__all__ = ["build_paper_registry_payload"]
