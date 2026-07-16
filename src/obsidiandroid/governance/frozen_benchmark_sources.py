"""Explicit sources for the isolated frozen benchmark; no legacy DB fallback."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd


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


class DatabaseFrozenBenchmarkSourceProvider:
    """Reserved until a read-only schema preflight verifies report identities."""
    def __init__(self, *_args, **_kwargs) -> None:
        raise RuntimeError("LIVE_SCHEMA_UNVERIFIED: Database frozen source provider is disabled pending report-snapshot preflight.")
