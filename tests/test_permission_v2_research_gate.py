"""The legacy ML permission path must abstain before reading observations."""

import pandas as pd
import pytest

from obsidiandroid.orchestration import permission_v2_research_gate as gate
from obsidiandroid.orchestration import permission_features
from obsidiandroid.pipeline.permission_trends import sample_permission_data
from obsidiandroid.database import db_permission_analysis_queries


@pytest.mark.parametrize("state", ["BLOCK", "UNKNOWN", None])
def test_gate_rejects_non_allow_state(monkeypatch, state):
    monkeypatch.setattr(
        gate.db_engine,
        "execute_permission_query",
        lambda *_args, **_kwargs: pd.DataFrame(
            {"legacy_observation_reads": [state]}
        ),
    )
    with pytest.raises(RuntimeError, match="blocks legacy"):
        gate.assert_legacy_observation_read_allowed()


def test_gate_rejects_missing_table_or_ambiguous_rows(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise RuntimeError("table missing")

    monkeypatch.setattr(gate.db_engine, "execute_permission_query", unavailable)
    with pytest.raises(RuntimeError, match="gate unavailable"):
        gate.assert_legacy_observation_read_allowed()
    monkeypatch.setattr(
        gate.db_engine,
        "execute_permission_query",
        lambda *_args, **_kwargs: pd.DataFrame(
            {"legacy_observation_reads": ["ALLOW", "ALLOW"]}
        ),
    )
    with pytest.raises(RuntimeError, match="blocks legacy"):
        gate.assert_legacy_observation_read_allowed()


def test_allow_is_explicit_and_precedes_observation_query(monkeypatch):
    queries = []

    def permitted(query, **_kwargs):
        queries.append(query)
        return pd.DataFrame({"legacy_observation_reads": ["ALLOW"]})

    monkeypatch.setattr(gate.db_engine, "execute_permission_query", permitted)
    gate.assert_legacy_observation_read_allowed()
    assert len(queries) == 1 and "gate_id=1" in queries[0]

    def blocked():
        raise RuntimeError("blocked")

    monkeypatch.setattr(
        permission_features, "assert_legacy_observation_read_allowed", blocked
    )
    with pytest.raises(RuntimeError, match="blocked"):
        permission_features._fetch_permission_rows([42])


@pytest.mark.parametrize("entry_point", [
    lambda: sample_permission_data.fetch_permission_aggregates(),
    lambda: sample_permission_data.fetch_permission_rows_for_samples([42]),
    lambda: db_permission_analysis_queries.fetch_android_banking_trojans_with_permissions(),
])
def test_alternate_observation_entry_points_fail_before_query(monkeypatch, entry_point):
    def deny_gate(*_args, **_kwargs):
        raise RuntimeError("gate BLOCK")

    def unguarded(*_args, **_kwargs):
        raise AssertionError("observation query reached before gate")

    monkeypatch.setattr(gate, "assert_legacy_observation_read_allowed", deny_gate)
    monkeypatch.setattr(sample_permission_data.db_engine, "execute_permission_query", unguarded)
    monkeypatch.setattr(db_permission_analysis_queries.db_engine, "execute_query", unguarded)
    with pytest.raises(RuntimeError, match="gate BLOCK"):
        entry_point()


@pytest.mark.parametrize("state", ["BLOCK", "UNKNOWN", "ALLOW"])
def test_required_preflight_checks_authority_without_observation_reads(monkeypatch, state):
    queries = []
    def query(sql, **kwargs):
        queries.append(sql)
        return pd.DataFrame({"legacy_observation_reads": [state]})
    monkeypatch.setattr(gate.db_engine, "execute_permission_query", query)
    flags = {"enable_permission_features": True, "permission_input_policy": "required"}
    if state == "ALLOW":
        gate.preflight_required_permission_access(flags)
    else:
        with pytest.raises(RuntimeError, match="Permission preflight stopped"):
            gate.preflight_required_permission_access(flags)
    assert len(queries) == 1
    assert "FROM android_permission_research_gate_v2_candidate" in queries[0]


def test_required_menu_preflight_stops_before_cohort_probe(monkeypatch):
    from obsidiandroid.cli.menu import profile_preflight as menu
    def unexpected(*args, **kwargs):
        pytest.fail("Cohort query must not run after permission denial")
    monkeypatch.setattr(menu.db_sample_metadata_fetchers, "probe_profile_cohort_viability", unexpected)
    monkeypatch.setattr(gate.db_engine, "execute_permission_query",
                        lambda *args, **kwargs: pd.DataFrame({"legacy_observation_reads": ["BLOCK"]}))
    ok, reason = menu.validate_profile_runnable("android_catalog_all_exploratory")
    assert not ok
    assert "Permission preflight stopped" in reason


def test_required_permission_preflight_never_silently_disables_features():
    with pytest.raises(ValueError, match="cannot disable"):
        gate.preflight_required_permission_access({"permission_input_policy": "required", "enable_permission_features": False})
