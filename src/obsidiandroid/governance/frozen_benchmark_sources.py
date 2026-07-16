"""Explicit sources for the isolated frozen benchmark; no legacy DB fallback."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Protocol

import pandas as pd

from obsidiandroid.governance.frozen_source_snapshot import SealedSnapshot, validate_sealed_snapshot


class FrozenBenchmarkSourceProvider(Protocol):
    def cohort_rows(self) -> pd.DataFrame: ...
    def android_metadata(self) -> pd.DataFrame: ...
    def permission_rows(self) -> pd.DataFrame: ...
    def vt_rows(self) -> pd.DataFrame: ...
    def engine_metadata(self) -> pd.DataFrame: ...
    def taxonomy_aliases(self) -> pd.DataFrame: ...


@dataclass(frozen=True)
class FrozenBenchmarkSourceBundle:
    """Immutable, one-read source snapshot reused by every benchmark stage."""
    cohort: pd.DataFrame
    metadata: pd.DataFrame
    permissions: pd.DataFrame
    verdicts: pd.DataFrame
    engines: pd.DataFrame
    taxonomy: pd.DataFrame
    permission_knowledge: dict[str, object]

    @classmethod
    def acquire(cls, provider: FrozenBenchmarkSourceProvider) -> "FrozenBenchmarkSourceBundle":
        # Each provider surface is called exactly once.  Deep copies prevent
        # later accidental mutation from changing the locked source snapshot.
        values = {
            "cohort": provider.cohort_rows(), "metadata": provider.android_metadata(),
            "permissions": provider.permission_rows(), "verdicts": provider.vt_rows(),
            "engines": provider.engine_metadata(), "taxonomy": provider.taxonomy_aliases(),
        }
        knowledge_method = getattr(provider, "permission_knowledge", None)
        knowledge = knowledge_method() if callable(knowledge_method) else {}
        return cls(**{name: value.copy(deep=True) for name, value in values.items()}, permission_knowledge=dict(knowledge or {}))


@dataclass
class SyntheticFrozenBenchmarkSourceProvider:
    cohort: pd.DataFrame
    metadata: pd.DataFrame
    permissions: pd.DataFrame
    verdicts: pd.DataFrame
    engines: pd.DataFrame
    taxonomy: pd.DataFrame
    knowledge: dict[str, object] | None = None

    def cohort_rows(self) -> pd.DataFrame: return self.cohort.copy()
    def android_metadata(self) -> pd.DataFrame: return self.metadata.copy()
    def permission_rows(self) -> pd.DataFrame: return self.permissions.copy()
    def vt_rows(self) -> pd.DataFrame: return self.verdicts.copy()
    def engine_metadata(self) -> pd.DataFrame: return self.engines.copy()
    def taxonomy_aliases(self) -> pd.DataFrame: return self.taxonomy.copy()
    def permission_knowledge(self) -> dict[str, object]: return dict(self.knowledge or {})


class SealedSnapshotFrozenBenchmarkSourceProvider:
    """Read a hash-verified sealed filesystem snapshot and nothing else."""
    def __init__(self, snapshot_root: Path) -> None:
        self.snapshot: SealedSnapshot = validate_sealed_snapshot(snapshot_root)
        self.synthetic_only = self.snapshot.manifest.get("classification") == "synthetic_validation"
        self._frames = {entry["name"]: pd.read_csv(self.snapshot.root / entry["path"], compression="gzip") for entry in self.snapshot.manifest["extracts"]}

    @property
    def snapshot_identity(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot.manifest["snapshot_id"],
            "temporal_limitation_classification": self.snapshot.manifest["temporal_limitation_classification"],
            "vt_temporal_semantics": self.snapshot.manifest["vt_temporal_semantics"],
        }

    def _frame(self, name: str) -> pd.DataFrame:
        return self._frames[name].copy(deep=True)

    def cohort_rows(self) -> pd.DataFrame: return self._frame("cohort_candidates")
    def android_metadata(self) -> pd.DataFrame: return self._frame("android_metadata")
    def permission_rows(self) -> pd.DataFrame: return self._frame("permission_observations")
    def engine_metadata(self) -> pd.DataFrame: return self._frame("engine_metadata")
    def taxonomy_aliases(self) -> pd.DataFrame: return self._frame("taxonomy_aliases")

    def vt_rows(self) -> pd.DataFrame:
        rows = self._frame("vt_long_normalized")
        return rows.rename(columns={"raw_engine_name": "engine_name", "raw_result": "result"}).drop(columns=["normalized_status", "avdet", "avobs"], errors="ignore")

    def permission_knowledge(self) -> dict[str, object]:
        rows = self._frame("permission_knowledge")
        result: dict[str, object] = {}
        for row in rows.to_dict("records"):
            kind = str(row.get("knowledge_kind") or "")
            try:
                payload = json.loads(str(row.get("payload_json") or "null"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Snapshot permission knowledge is malformed: {kind}") from exc
            if kind in {"permission_dictionary", "authority_classification", "protection_level_classification"}:
                if not isinstance(payload, list):
                    raise ValueError(f"Snapshot permission knowledge must be a row list: {kind}")
                result[kind] = pd.DataFrame(payload)
            elif kind == "approved_oem_google_tokens":
                if not isinstance(payload, list):
                    raise ValueError("Snapshot approved permission allowlist must be a list.")
                result[kind] = [str(value) for value in payload]
            elif kind == "alias_map":
                if not isinstance(payload, dict):
                    raise ValueError("Snapshot permission alias map must be an object.")
                result[kind] = payload
            elif kind == "known_missing_protection_policy":
                result[kind] = str(payload)
        return result


class DatabaseFrozenBenchmarkSourceProvider:
    """Reserved until a read-only schema preflight verifies report identities."""
    def __init__(self, *_args, **_kwargs) -> None:
        raise RuntimeError("LIVE_SCHEMA_UNVERIFIED: Database frozen source provider is disabled pending report-snapshot preflight.")
