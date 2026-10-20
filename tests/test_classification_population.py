"""The census compiles maintained cohort SQL without executing the normal loader."""
from contextlib import contextmanager
from unittest.mock import Mock
from obsidiandroid.database import classification_population as population
from obsidiandroid.database import db_sample_metadata_fetchers as loader
from obsidiandroid.cli.profile_manager import load_profile


def test_census_reuses_bounded_readonly_loader_sql(monkeypatch):
    normal = Mock(side_effect=AssertionError('normal database loader must not execute'))
    monkeypatch.setattr(loader.db_engine, 'execute_query', normal)
    source = Mock()
    source.checked_utc = '2026-10-18T12:00:00+00:00'
    source.query.return_value = [{'family_id': 1, 'family_canonical': 'Anubis',
                                  'samples': 10, 'av_source_rows': 8}]
    @contextmanager
    def session():
        yield source
    monkeypatch.setattr(population, 'explorer_session', session)
    result = population.major_family_population(load_profile('android_malware_major_families'))
    assert result['samples'] == 10 and result['av_source_rows'] == 8
    sql, params = source.query.call_args.args
    assert 'LIMIT 1001' in sql and 'android_permission_obs_sample' not in sql
    assert '2026-01-01' in str(params)
    source.connection.cmd_query.assert_called_once_with('SET SESSION max_statement_time=45')
    normal.assert_not_called()
