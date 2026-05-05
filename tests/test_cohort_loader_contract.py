"""Regression: cohort loader must return one row per sample_id (primary DB joins)."""

from __future__ import annotations

import pandas as pd
import pytest

from obsidiandroid.database import db_sample_metadata_queries
from obsidiandroid.database.db_sample_metadata_contracts import log_and_assert_loader_sample_grain


def test_log_and_assert_loader_sample_grain_raises_on_duplicate_sample_ids() -> None:
    df = pd.DataFrame({"sample_id": [1, 1, 2]})
    with pytest.raises(ValueError, match="duplicate_surplus"):
        log_and_assert_loader_sample_grain(df, label="unit")


def test_load_samples_by_type_raises_when_fetch_returns_duplicate_sample_ids(monkeypatch) -> None:
    """Guardrail if SQL regresses and multiplies rows per sample_id."""

    def _fake_fetch(**kwargs):
        del kwargs
        return (
            ["sample_id", "sha256"],
            [
                (1, "a" * 64),
                (1, "b" * 64),
            ],
        )

    monkeypatch.setattr(db_sample_metadata_queries, "_fetch_samples_by_type", _fake_fetch)
    with pytest.raises(ValueError, match="duplicate_surplus"):
        db_sample_metadata_queries.load_samples_by_type(type_slug=None)


def test_load_samples_by_type_unique_sample_id_contract(monkeypatch) -> None:
    def _fake_fetch(**kwargs):
        del kwargs
        return (
            ["sample_id", "sha256"],
            [(10, "c" * 64), (11, "d" * 64)],
        )

    monkeypatch.setattr(db_sample_metadata_queries, "_fetch_samples_by_type", _fake_fetch)
    df = db_sample_metadata_queries.load_samples_by_type(type_slug=None)
    assert bool(df["sample_id"].is_unique)
