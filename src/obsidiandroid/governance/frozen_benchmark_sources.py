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


@dataclass
class SyntheticFrozenBenchmarkSourceProvider:
    cohort: pd.DataFrame
    metadata: pd.DataFrame
    permissions: pd.DataFrame
    verdicts: pd.DataFrame
    engines: pd.DataFrame
    taxonomy: pd.DataFrame

    def cohort_rows(self) -> pd.DataFrame: return self.cohort.copy()
    def android_metadata(self) -> pd.DataFrame: return self.metadata.copy()
    def permission_rows(self) -> pd.DataFrame: return self.permissions.copy()
    def vt_rows(self) -> pd.DataFrame: return self.verdicts.copy()
    def engine_metadata(self) -> pd.DataFrame: return self.engines.copy()
    def taxonomy_aliases(self) -> pd.DataFrame: return self.taxonomy.copy()


class DatabaseFrozenBenchmarkSourceProvider:
    """Reserved until a read-only schema preflight verifies report identities."""
    def __init__(self, *_args, **_kwargs) -> None:
        raise RuntimeError("LIVE_SCHEMA_UNVERIFIED: Database frozen source provider is disabled pending report-snapshot preflight.")
