"""Fail-closed gate for legacy PI observation-based research features.

This is an unpublished candidate. The matching PI gate table defaults to
BLOCK. A reviewed deployment must install the table and SELECT grant before
this consumer is released; the old published consumer remains unprotected.
"""

from __future__ import annotations

import pandas as pd

from obsidiandroid.database import db_engine


def assert_legacy_observation_read_allowed() -> None:
    """Refuse legacy ML reads unless the PI authority explicitly permits them."""

    try:
        rows = db_engine.execute_permission_query(
            "SELECT legacy_observation_reads "
            "FROM android_permission_research_gate_v2_candidate "
            "WHERE gate_id=1",
            params=(),
            fetch=True,
            as_dataframe=True,
        )
    except Exception as exc:
        raise RuntimeError(
            "PI V2 research gate unavailable; legacy permission features abstain"
        ) from exc
    if (
        not isinstance(rows, pd.DataFrame)
        or len(rows) != 1
        or list(rows.columns) != ["legacy_observation_reads"]
        or rows.iloc[0, 0] != "ALLOW"
    ):
        raise RuntimeError(
            "PI V2 research gate blocks legacy permission features"
        )
