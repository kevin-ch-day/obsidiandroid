"""Reporting must not fabricate clusters or retry internal failures as old APIs."""
import inspect
import pandas as pd
import pytest
from config import app_config
from obsidiandroid.pipeline import stage_permission_trends_report as reports
from obsidiandroid.cli.menu import vendor_diagnostics_actions as actions
from obsidiandroid.cli.menu import vendor_parser_state as state
from obsidiandroid.vendors.parsing import vendor_parser_map


def cluster_inputs():
    core = pd.DataFrame({'family_id': [10, 20], 'type_slug': ['banker', 'banker']})
    profiles = pd.DataFrame({'family_id': [10, 10, 20, 20],
        'family_canonical': ['a', 'a', 'b', 'b'], 'sample_count': [30]*4,
        'permission': ['p', 'q', 'p', 'q'], 'profile_scope': ['main']*4,
        'prevalence': [.9, .1, .2, .8]})
    return core, profiles


def test_current_cluster_api_and_single_group(monkeypatch):
    monkeypatch.setattr(app_config, 'BANKER_PATTERN_CLUSTER_K', 2, raising=False)
    assignments, profiles = reports._build_banker_family_pattern_clusters(*cluster_inputs(), 'fixture')
    assert set(assignments.family_id) == {10, 20}
    assert assignments.cluster_id.nunique() == 2
    assert not profiles.empty
    monkeypatch.setattr(app_config, 'BANKER_PATTERN_CLUSTER_K', 1)
    assignments, _ = reports._build_banker_family_pattern_clusters(*cluster_inputs(), 'fixture')
    assert set(assignments.cluster_id) == {0}


@pytest.mark.parametrize('failure', ['constructor', 'fit'])
def test_clustering_errors_never_produce_round_robin_assignments(monkeypatch, failure):
    import sklearn.cluster
    calls = []
    class BrokenClustering:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            if failure == 'constructor':
                raise TypeError('internal constructor failure')
        def fit_predict(self, _matrix):
            raise RuntimeError('clustering failed')
    monkeypatch.setattr(sklearn.cluster, 'AgglomerativeClustering', BrokenClustering)
    monkeypatch.setattr(app_config, 'BANKER_PATTERN_CLUSTER_K', 2, raising=False)
    with pytest.raises((TypeError, RuntimeError)):
        reports._build_banker_family_pattern_clusters(*cluster_inputs(), 'fixture')
    assert len(calls) == 1
    assert calls[0]['metric'] == 'precomputed'
    assert 'affinity' not in calls[0]


def test_workbook_internal_type_error_is_not_retried(monkeypatch):
    for name in ['resolve_vendor_parser_coverage_csv', 'resolve_vendor_parser_coverage_candidates_csv',
                 'resolve_vendor_gate_pre_gate_csv']:
        monkeypatch.setattr(state, name, lambda: None)
    calls = []
    def loader(**kwargs):
        calls.append(kwargs)
        if kwargs:
            raise TypeError('workbook reader failed')
        return pd.DataFrame()
    with pytest.raises(TypeError, match='workbook reader failed'):
        state.build_parser_diagnostics_state(workbook_loader=loader)
    assert calls == [{'emit_warnings': False}]


def test_registered_vendor_parsers_accept_current_call_contract():
    for name, metadata in vendor_parser_map.get_vendor_parser_map().items():
        assert callable(metadata['func']), name
        inspect.signature(metadata['func']).bind('synthetic label', None)


@pytest.mark.parametrize('broken', [False, True])
def test_vendor_parser_internal_error_counted_once_with_explicit_fallback(monkeypatch, broken):
    calls, fallback, stats, warnings = [], [], {}, []
    parsed = {'family': 'unknown', 'malware_type': 'unknown', 'threat_class': 'unknown'}
    def parser(*args):
        calls.append(args)
        if broken and len(args) == 2:
            raise TypeError('internal parser error')
        return parsed
    def generic(*args):
        fallback.append(args)
        return parsed
    monkeypatch.setattr(actions, 'load_enriched_matrix_for_menu', lambda **_: pd.DataFrame({'Test': ['label']}))
    monkeypatch.setattr(actions.vendor_parser_map, 'get_vendor_parser_map', lambda: {'Test': {'func': parser}})
    monkeypatch.setattr(actions.vendor_parser_map, 'resolve_vendor_column_name', lambda *_: 'Test')
    monkeypatch.setattr(actions.mu, 'display_menu', lambda *a, **k: 1)
    monkeypatch.setattr(actions, 'parse_generic_classification', generic)
    monkeypatch.setattr(actions.du, 'print_stat', lambda key, value: stats.update({key: value}))
    monkeypatch.setattr(actions.du, 'print_warning', warnings.append)
    monkeypatch.setattr(actions.du, 'print_table', lambda *a, **k: None)
    assert actions.run_single_vendor_parser_check() == 0
    assert calls == [('label', None)]
    assert stats['Parser Errors'] == int(broken)
    assert stats['Generic Fallback Rows'] == int(broken)
    assert len(fallback) == int(broken)
    assert bool(warnings) == broken


def test_permission_reporting_stops_at_denied_source_gate(monkeypatch):
    from obsidiandroid.pipeline.permission_trends import sample_permission_data
    calls = []
    def deny_query(query, **kwargs):
        calls.append(query)
        return pd.DataFrame({'legacy_observation_reads': ['BLOCK']})
    monkeypatch.setattr(sample_permission_data.db_engine, 'execute_permission_query', deny_query)
    with pytest.raises(RuntimeError, match='blocks legacy permission features'):
        sample_permission_data.fetch_permission_rows_for_samples([1])
    assert len(calls) == 1
    assert 'android_permission_research_gate_v2_candidate' in calls[0]
