"""Artifact registry for deterministic manifest assembly."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class ArtifactRecord:
    """One artifact registry entry.

    Attributes:
        logical_name: Stable logical artifact name.
        stage_origin: Stage that produced the artifact.
        artifact_path: Absolute path on disk.
        sha256: Content hash.
        size_bytes: File size.
        timestamp_created: UTC timestamp.
    """

    logical_name: str
    stage_origin: str
    artifact_path: str
    sha256: str
    size_bytes: int
    timestamp_created: str


class ArtifactRegistry:
    """Registry for run artifacts with write-and-register helpers."""

    def __init__(self) -> None:
        self._records: dict[str, ArtifactRecord] = {}

    def records(self) -> list[ArtifactRecord]:
        """Return registry records sorted by logical name."""
        return [self._records[name] for name in sorted(self._records.keys())]

    def as_dicts(self) -> list[dict[str, Any]]:
        """Return serializable registry entries."""
        return [asdict(record) for record in self.records()]

    def write_text(
        self,
        *,
        logical_name: str,
        stage_origin: str,
        path: Path,
        text: str,
        encoding: str = "utf-8",
    ) -> ArtifactRecord:
        """Write text file and register metadata."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding=encoding)
        return self.register(
            logical_name=logical_name,
            stage_origin=stage_origin,
            path=path,
        )

    def write_bytes(
        self,
        *,
        logical_name: str,
        stage_origin: str,
        path: Path,
        payload: bytes,
    ) -> ArtifactRecord:
        """Write bytes file and register metadata."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return self.register(
            logical_name=logical_name,
            stage_origin=stage_origin,
            path=path,
        )

    def write_dataframe_csv(
        self,
        *,
        logical_name: str,
        stage_origin: str,
        path: Path,
        dataframe: pd.DataFrame,
        float_format: str | None = None,
        lineterminator: str = "\n",
    ) -> ArtifactRecord:
        """Write CSV file and register metadata."""
        path.parent.mkdir(parents=True, exist_ok=True)
        dataframe.to_csv(path, index=False, float_format=float_format, lineterminator=lineterminator)
        return self.register(
            logical_name=logical_name,
            stage_origin=stage_origin,
            path=path,
        )

    def register(
        self,
        *,
        logical_name: str,
        stage_origin: str,
        path: Path,
    ) -> ArtifactRecord:
        """Register an existing file and compute metadata."""
        resolved = path.resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Artifact path does not exist: {resolved}")
        size_bytes = int(resolved.stat().st_size)
        if size_bytes <= 0:
            raise ValueError(f"Artifact path is empty: {resolved}")
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        record = ArtifactRecord(
            logical_name=str(logical_name),
            stage_origin=str(stage_origin),
            artifact_path=str(resolved),
            sha256=digest,
            size_bytes=size_bytes,
            timestamp_created=datetime.now(timezone.utc).isoformat(),
        )
        self._records[str(logical_name)] = record
        return record

