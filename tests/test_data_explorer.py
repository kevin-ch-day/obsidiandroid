"""Synthetic explorer contracts: no network, fitting, archiving or source writes."""
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import Mock
import pytest

from obsidiandroid.database import data_explorer as db
from obsidiandroid.cli import data_explorer as ui


class Cursor:
    def __init__(self, rows, calls, error=None):
        self.rows, self.calls, self.error = rows, calls, error
        self.closed = False
    def execute(self, sql, params):
        self.calls.append((sql, params))
        if self.error:
            raise self.error
    def fetchall(self):
        return self.rows
    def close(self):
        self.closed = True


def service(rows=None, error=None):
    calls = []
    cursor = Cursor(rows or [], calls, error)
    connection = Mock()
    connection.cursor.return_value = cursor
    return db.Explorer(connection), calls, cursor


@pytest.mark.parametrize('kind', ['family', 'type', 'relationship'])
@pytest.mark.parametrize('low', [False, True])
def test_pages_filter_bound_and_counts_preserved(kind, low):
    e, calls, cursor = service([{'label': 'x', 'samples': 17}])
    label = "x' OR 1=1 --"
    assert e.browse(kind=kind, term=label, page=2, low_support=low)[0]['samples'] == 17
    sql, params = calls[0]
    assert label not in sql
    assert params == (label, 21, 40)
    assert ('HAVING COUNT(*) < 3' in sql) == low
    assert cursor.closed


@pytest.mark.parametrize('value', ['0', '-1', '1 OR 1=1', 'a'*63, '', '1'*65])
def test_lookup_rejects_inexact_identity(value):
    e, calls, _ = service()
    with pytest.raises(ValueError):
        e.lookup(value)
    assert calls == []


@pytest.mark.parametrize('value,expected', [('42', 42), ('A'*64, 'a'*64)])
def test_lookup_is_exact_and_bounded(value, expected):
    e, calls, _ = service([{'sample_id': 42}])
    assert e.lookup(value) == [{'sample_id': 42}]
    assert calls[0][1] == (expected,)
    assert 'LIMIT 2' in calls[0][0]


def test_unavailable_never_becomes_zero():
    e, _, cursor = service(error=PermissionError('private credential detail'))
    with pytest.raises(db.ExplorerUnavailable, match='no count inferred') as err:
        e.overview()
    assert 'private credential' not in str(err.value)
    assert cursor.closed


def test_readonly_session_rolls_back_even_after_failure(monkeypatch):
    from obsidiandroid.database import db_engine
    conn = Mock()
    monkeypatch.setattr(db_engine, '_get_connection', lambda: conn)
    with pytest.raises(db.ExplorerUnavailable):
        with db.explorer_session():
            raise RuntimeError('failure')
    conn.start_transaction.assert_called_once_with(readonly=True)
    conn.rollback.assert_called_once()
    conn.close.assert_called_once()
    conn.commit.assert_not_called()


@pytest.mark.parametrize('sql', ['DELETE FROM x', 'SELECT 1; DELETE FROM x'])
def test_query_rejects_non_select(sql):
    e, calls, _ = service()
    with pytest.raises(ValueError):
        e.query(sql)
    assert not calls


def test_permission_unavailable_and_unapproved(monkeypatch):
    from obsidiandroid.orchestration import permission_v2_export as v2
    e, calls, _ = service()
    assert 'Unavailable' in e.permission_coverage(None)['status']
    monkeypatch.setattr(v2, '_checked_export', Mock(side_effect=ValueError('not approved')))
    assert 'Unavailable' in e.permission_coverage('export.json')['status']
    assert not calls


def test_permission_exact_identity_intersection(monkeypatch):
    from obsidiandroid.orchestration import permission_v2_export as v2
    e, calls, _ = service([{'n': 1}])
    monkeypatch.setattr(v2, '_checked_export', lambda p: (b'', b'', {'samples': [{'sample_id': 1, 'sha256': 'a'*64}]}))
    assert e.permission_coverage('approved')['covered'] == 1
    assert 'BINARY m.sha256=%s' in calls[0][0]
    assert calls[0][1] == (1, 'a'*64)
    assert e.permission_coverage('approved', {'sample_id': 1, 'sha256': 'b'*64})['covered'] == 0
    assert e.permission_coverage('approved', {'sample_id': 1, 'sha256': 'a'*64})['evidence'] == 'PROVIDER_REPORTED_UNRESOLVED'


@pytest.mark.parametrize('choice,action', [(1,'show_overview'),(2,'browse_families'),(3,'show_quality'),(4,'show_coverage'),(5,'find_sample')])
def test_every_explorer_action_returns_without_pipeline(monkeypatch, choice, action):
    import obsidiandroid.pipeline as pipeline
    from obsidiandroid.common import run_slots
    monkeypatch.setattr(pipeline, 'run_pipeline', Mock(side_effect=AssertionError('training forbidden')))
    for name in dir(run_slots):
        if 'archive' in name and callable(getattr(run_slots, name)):
            monkeypatch.setattr(run_slots, name, Mock(side_effect=AssertionError('archive forbidden')))
    choices = iter([choice, 0])
    monkeypatch.setattr(ui.mu, 'display_menu', lambda *a, **k: next(choices))
    monkeypatch.setenv('OBSIDIANDROID_EXPLORER_PI_V2_EXPORT', 'approved')
    e = Mock()
    @contextmanager
    def session():
        yield e
    monkeypatch.setattr(ui, 'explorer_session', session)
    called = Mock()
    monkeypatch.setattr(ui, action, called)
    assert ui.launch_data_explorer() == 0
    assert called.call_count == 1
    assert called.call_args.args[0] is e


def test_browse_pagination_and_filter(monkeypatch):
    e = Mock(checked_utc='now')
    e.browse.side_effect = [[{'label': 'x', 'samples': 1}]*21, [{'label': 'x', 'samples': 1}]]
    choices = iter([1, 2, 1, 0])
    monkeypatch.setattr(ui.mu, 'display_menu', lambda *a, **k: next(choices))
    monkeypatch.setattr('builtins.input', lambda _: 'x')
    ui.browse_families(e)
    assert [c.kwargs['page'] for c in e.browse.call_args_list] == [0, 1]
    assert all(c.kwargs['term'] == 'x' for c in e.browse.call_args_list)


def test_coverage_denied_av_still_shows_pi(monkeypatch, capsys):
    e = Mock(checked_utc='2026-10-18')
    e.av_coverage.side_effect = db.ExplorerUnavailable('AV unavailable')
    e.permission_coverage.return_value = {'status': 'Uncovered; permissions unknown'}
    ui.show_coverage(e, None)
    output = capsys.readouterr().out
    assert 'AV unavailable' in output and 'permissions unknown' in output
    assert 'Lifecycle readiness: not computed' in output


def test_overview_is_live_not_saved_or_training(capsys):
    e = Mock(checked_utc='2026-10-18')
    e.catalog_summary.return_value = {'android_catalog_records': 4}
    e.label_summary.return_value = {'selected_apks': 3}
    e.browse.return_value = e.sources.return_value = []
    ui.show_overview(e)
    out = capsys.readouterr().out
    assert 'Live catalog' in out and 'Training eligibility' in out and 'Not evaluated' in out


def test_classification_targets_open_readonly_overview(monkeypatch):
    from obsidiandroid.cli import startup_menu as menu
    from obsidiandroid.cli import classification_overview
    choices = iter([1, 2, 0])
    monkeypatch.setattr(menu.mu, 'display_menu', lambda *a, **k: next(choices))
    overview = Mock()
    monkeypatch.setattr(classification_overview, 'launch_experiment', overview)
    run = Mock()
    monkeypatch.setattr(menu, '_run_full_pipeline_with_persistence_choice', run)
    menu._launch_classification_menu()
    assert [call.args[0] for call in overview.call_args_list] == [
        'android_malware_major_families', 'android_malware_type_taxonomy']
    run.assert_not_called()


def test_all_profiles_remain_discoverable():
    from obsidiandroid.cli import profile_manager, profile_selection
    paths = profile_manager.list_profiles()
    catalog = profile_selection.build_profile_catalog(paths)
    assert len(paths) == 25
    assert {p.stem for p in paths} == {pid for pid, _ in catalog}
    assert 'dev_ablation_fast' in {pid for pid, _ in catalog}




def test_quality_uses_alias_semantics_and_no_clean_zero(capsys):
    e = Mock(checked_utc='now')
    e.quality.return_value = {'raw_canonical_disagreements': 264, 'missing_package': None}
    e.catalog_summary.return_value = dict(android_catalog_records=35371, apk_records=35369, missing_effective_date=2, missing_registry=0)
    ui.show_quality(e)
    text = capsys.readouterr().out
    assert '264' in text and 'Unavailable / not measured' in text
    assert 'alias-aware' in text


def test_sample_screen_warns_missing_and_uncovered(monkeypatch, capsys):
    e = Mock(checked_utc='now')
    e.lookup.return_value = [{'sample_id': 42, 'sha256': 'a'*64, 'android_package_name': None,
                             'source_family': 'androrat', 'canonical_family': 'CapraRAT'}]
    e.av_coverage.return_value = {'with_scan_summary': 1}
    e.permission_coverage.return_value = {'status': 'Uncovered; permissions unknown'}
    monkeypatch.setattr('builtins.input', lambda _: '42')
    ui.find_sample(e, None)
    text = capsys.readouterr().out
    assert 'Missing metadata' in text and 'disagreement needs review' in text
    assert 'Uncovered; permissions unknown' in text


def test_terminal_metadata_controls_are_escaped(capsys):
    ui.show_fields({'label': '\x1b[2Jbad'})
    assert '\\x1b[2Jbad' in capsys.readouterr().out


def test_av_observed_is_not_lifecycle_readiness(monkeypatch):
    e, _, _ = service()
    answers = iter([[{'COLUMN_NAME':'sample_id'}, {'COLUMN_NAME':'engine_a'}, {'COLUMN_NAME':'engine_b'}],
                    {'engine_a': 1, 'engine_b': 0}])
    def query(sql, params=()):
        answer = next(answers)
        return [answer] if isinstance(answer, dict) else answer
    monkeypatch.setattr(e, 'query', query)
    result = e.av_engines()
    assert result == {'observed_nonblank_engine_columns':1, 'visible_engine_columns':2, 'lifecycle_ready_engines':None}




def test_frozen_contract_is_not_advertised_as_runnable_profile():
    from obsidiandroid.cli.profile_selection import summarize_profile
    from obsidiandroid.cli.profile_manager import PROFILES_DIR
    summary = summarize_profile(PROFILES_DIR / 'android_malware_major_families_frozen_n20_v1.yaml')
    assert 'Specialized frozen cohort contract' in summary
    assert 'not a normal run profile' in summary


def test_overview_paints_catalog_before_taxonomy(monkeypatch, capsys):
    e = Mock(checked_utc='now')
    e.catalog_summary.return_value = {'android_catalog_records': 35371}
    def label_summary():
        text = capsys.readouterr().out
        assert '35,371' in text
        assert 'FAMILY COVERAGE' in text
        return {'selected_apks': 35369}
    e.label_summary.side_effect = label_summary
    e.browse.return_value = e.sources.return_value = []
    ui.show_overview(e)
    assert '35,369' in capsys.readouterr().out


def test_normalized_family_join_preserves_resolution_and_family_multiplicity():
    import sqlite3
    connection = sqlite3.connect(':memory:')
    try:
        connection.executescript("""
            CREATE TABLE malware_sample_catalog (sample_id INTEGER);
            CREATE TABLE v_android_apk_family_resolved (sample_id INTEGER, resolved_family_lc TEXT);
            CREATE TABLE android_malware_family
                (family_id INTEGER PRIMARY KEY, family_name TEXT, primary_type_id INTEGER, family_slug TEXT);
            CREATE TABLE android_malware_type (type_id INTEGER PRIMARY KEY, type_slug TEXT);
            INSERT INTO malware_sample_catalog VALUES (1),(2),(3);
            INSERT INTO v_android_apk_family_resolved VALUES (1,'alpha'),(1,'alpha'),(1,'zeta'),(2,'beta'),(3,NULL);
            INSERT INTO android_malware_family VALUES (10,'Alpha',1,'ALPHA'),(11,'Other Alpha',1,'alpha'),(20,'Beta',2,'beta');
            INSERT INTO android_malware_type VALUES (1,'banker'),(2,'rat');
        """)
        original = db.JOINS[:db.JOINS.index('LEFT JOIN (\n    SELECT DISTINCT')] + (
            'LEFT JOIN android_malware_family f ON LOWER(f.family_slug)=v.resolved_family_lc '
            'LEFT JOIN android_malware_type t ON t.type_id=f.primary_type_id')
        select = 'SELECT m.sample_id,f.family_id,t.type_slug '
        order = ' ORDER BY m.sample_id,f.family_id'
        before = connection.execute(select + original + order).fetchall()
        after = connection.execute(select + db.JOINS + order).fetchall()
        assert after == before == [(1,10,'banker'),(1,11,'banker'),(2,20,'rat'),(3,None,None)]
    finally:
        connection.close()


def test_main_menu_opens_readonly_data_explorer(monkeypatch):
    from obsidiandroid.cli import data_explorer, startup_menu

    called = []
    monkeypatch.setattr(data_explorer, "launch_data_explorer", lambda: called.append(True) or 0)
    command = next(
        item for item in startup_menu._build_main_menu_commands()
        if item.label == "Explore Android data"
    )
    assert command.action() == 0
    assert called == [True]


def test_explorer_menu_custom_prompt_keeps_numeric_selection(monkeypatch):
    from obsidiandroid.cli.ui import menu

    prompts = []
    answers = iter(["invalid", "1"])

    def answer(prompt):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", answer)
    assert menu.display_menu(["Research"], title="Explorer", selection_prompt="Select: ") == 1
    assert prompts == ["Select: ", "Select: "]
