"""Artifact key and run-scoped manifest utilities."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from obsidiandroid.common.path_safety import safe_join


class ArtifactKey(str):
    """Enum-like artifact keys for governance outputs."""

    SPLIT_AUDIT_CSV = "split_audit_csv"
    DUPLICATE_SHA_REPORT_CSV = "duplicate_sha_report_csv"
    VENDOR_GATE_DEBUG_CSV = "vendor_gate_debug_csv"
    ABLATION_UNIVERSE_REPORT_CSV = "ablation_universe_report_csv"
    EXPERIMENT_REGISTRY_JSON = "experiment_registry_json"
    SAFE_CLAIMS_MD = "safe_claims_md"
    LOW_SUPPORT_POLICY_JSON = "low_support_policy_json"
    FAMILIES_MAPPED_CSV = "families_mapped_csv"
    PAPER_AUDIT_COHORT_CSV = "paper_audit_cohort_csv"
    RUN_PATHS_MANIFEST_JSON = "run_paths_manifest_json"
    RUN_SUMMARY_ONEPAGER_MD = "run_summary_onepager_md"
    MODEL_CONFIG_SNAPSHOT_JSON = "model_config_snapshot_json"
    COHORT_FILTER_CONTRACT_JSON = "cohort_filter_contract_json"
    EXPERIMENT_CONTRACT_SNAPSHOT_JSON = "experiment_contract_snapshot_json"


_ALLOWED_KEYS = {
    value
    for name, value in ArtifactKey.__dict__.items()
    if name.isupper() and isinstance(value, str)
}


@dataclass
class ArtifactEntry:
    """One manifest artifact entry."""

    relpath: str
    sha256: str
    content_type: str
    description: str
    status: str = "created"


def hash_file(path: Path) -> str:
    """Compute SHA256 hash of file bytes."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


class ManifestWriter:
    """Run-scoped manifest builder with key/duplicate protection."""

    def __init__(self, run_root: Path, *, paper_mode: bool = False) -> None:
        self.run_root = run_root.resolve()
        self.paper_mode = bool(paper_mode)
        self._artifacts: dict[str, ArtifactEntry] = {}
        self._excluded_non_run_scoped_count = 0

    @property
    def excluded_non_run_scoped_count(self) -> int:
        """Return number of artifacts excluded for being outside run root."""
        return int(self._excluded_non_run_scoped_count)

    def add_file(
        self,
        *,
        artifact_key: str,
        path: Path,
        content_type: str,
        description: str,
        status: str = "created",
    ) -> None:
        if artifact_key not in _ALLOWED_KEYS:
            raise KeyError(f"Unknown artifact key: {artifact_key}")
        if self.paper_mode and artifact_key in self._artifacts:
            raise ValueError(f"Duplicate artifact key in paper mode: {artifact_key}")
        resolved_path = path.resolve()
        try:
            rel_to_run = resolved_path.relative_to(self.run_root)
        except ValueError as exc:
            if self.paper_mode:
                raise ValueError(
                    f"Artifact path is outside run root: {resolved_path} (run_root={self.run_root})"
                ) from exc
            self._excluded_non_run_scoped_count += 1
            self._artifacts[artifact_key] = ArtifactEntry(
                relpath=str(resolved_path).replace("\\", "/"),
                sha256="",
                content_type=content_type,
                description=description,
                status="excluded_non_run_scoped",
            )
            return
        safe_path = safe_join(self.run_root, rel_to_run)
        relpath = str(safe_path.relative_to(self.run_root)).replace("\\", "/")
        file_hash = hash_file(safe_path) if safe_path.exists() else ""
        self._artifacts[artifact_key] = ArtifactEntry(
            relpath=relpath,
            sha256=file_hash,
            content_type=content_type,
            description=description,
            status=status,
        )

    def to_dict(self, *, run_id: str, profile_name: str) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "run_id": run_id,
            "profile": {"name": profile_name},
            "roots": {"run_root": str(self.run_root).replace("\\", "/")},
            "artifacts": {
                key: {
                    "relpath": entry.relpath,
                    "sha256": entry.sha256,
                    "content_type": entry.content_type,
                    "description": entry.description,
                    "status": entry.status,
                }
                for key, entry in sorted(self._artifacts.items())
            },
        }

    def write_json(self, output_path: Path, *, run_id: str, profile_name: str) -> Path:
        payload = self.to_dict(run_id=run_id, profile_name=profile_name)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return output_path
