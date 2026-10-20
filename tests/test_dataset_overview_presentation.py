"""Dataset overview presentation contracts independent of live data."""
from decimal import Decimal
from unittest.mock import Mock
import pytest
from obsidiandroid.cli import data_explorer as ui
from obsidiandroid.database.data_explorer import ExplorerUnavailable


def service(selected=10, known=6, unknown=4, rows=None, timestamp='2026-10-18T02:47:59Z'):
    e = Mock(checked_utc=timestamp)
    e.catalog_summary.return_value = {
        'android_catalog_records': selected + 2, 'apk_records': selected,
        'missing_effective_date': 2, 'missing_registry': 0,
        'earliest_effective_date': '2010-06-12 00:00:00',
        'latest_effective_date': '2026-09-22 04:01:31',
    }
    e.label_summary.return_value = dict(selected_apks=selected, known_family_samples=known,
                                       unknown_family_samples=unknown, observed_known_families=2)
    data = rows if rows is not None else [{'label': 'rat', 'samples': 4}, {'label': 'banker', 'samples': 6}]
    e.browse.side_effect = lambda *, kind, page: data[page*20:page*20+21]
    return e


def test_clean_sections_percentages_and_complete_total(capsys):
    e = service()
    ui.show_overview(e)
    out = capsys.readouterr().out
    for section in ('CATALOG','FAMILY COVERAGE','MALWARE TYPES','NOTES'):
        assert section in out
    assert '6 (60.0%)' in out and '4 (40.0%)' in out
    assert out.index('banker') < out.index('rat')
    assert 'Total' in out and '10' in out
    assert '[DATAFRAME]' not in out and 'first 20' not in out and 'loading' not in out.lower()
    assert '[CDT] Oct 17, 2026 · 9:47 PM' in out
    assert '[UTC] Oct 18, 2026 · 2:47 AM' in out
    assert ':59' not in out and '04:01:31' not in out
    assert 'First provider date         : 6-12-2010' in out
    assert 'Latest provider date        : 9-22-2026' in out
    assert 'Android records             : 12' in out
    assert 'locally verified APK' in out and 'not verified collection or deployment' in out
    e.sources.assert_not_called()


def test_large_distribution_has_actual_category_count_and_subtotal(capsys):
    rows = [{'label': f'type{i:02d}', 'samples': 1} for i in range(25)]
    ui.show_overview(service(selected=25, known=20, unknown=5, rows=rows))
    out = capsys.readouterr().out
    assert 'Showing 20 of 25 types' in out
    assert 'Displayed subtotal' in out
    assert 'Population mismatch' not in out
    assert 'type19' in out and 'type20' not in out


@pytest.mark.parametrize('known,unknown', [(7,4),(None,4),(6,None),(Decimal('6.5'),4)])
def test_bad_family_denominator_does_not_claim_percentages(known, unknown, capsys):
    ui.show_overview(service(known=known, unknown=unknown))
    out = capsys.readouterr().out
    assert '%' not in out
    assert 'Family coverage consistency:' in out


def test_distribution_mismatch_is_visible(capsys):
    ui.show_overview(service(rows=[{'label':'rat','samples':8}]))
    assert 'Population mismatch: all types total 8; selected APKs 10.' in capsys.readouterr().out


def test_empty_population_does_not_divide_by_zero(capsys):
    ui.show_overview(service(selected=0, known=0, unknown=0, rows=[]))
    out = capsys.readouterr().out
    assert 'No malware-type categories returned.' in out
    assert 'Total' in out and 'percentage unavailable' in out
    assert 'Population mismatch' not in out


def test_missing_fields_do_not_become_zero(capsys):
    e = service(rows=[{'label':'rat','samples':None}])
    e.catalog_summary.return_value = {}
    e.label_summary.return_value = {}
    ui.show_overview(e)
    out = capsys.readouterr().out
    assert 'Unavailable' in out and 'Population consistency: unavailable' in out
    assert '0.0%' not in out


def test_winter_abbreviation_uses_observation_date(capsys):
    ui.show_overview(service(timestamp='2026-12-16T03:00:01Z'))
    out = capsys.readouterr().out
    assert '[CST] Dec 15, 2026 · 9:00 PM' in out
    assert '[UTC] Dec 16, 2026 · 3:00 AM' in out
    assert '[CDT]' not in out


def test_progress_cleared_on_failure(monkeypatch, capsys):
    monkeypatch.setattr(ui.sys.stdout, 'isatty', lambda: True)
    def fail():
        raise ExplorerUnavailable('denied')
    with pytest.raises(ExplorerUnavailable):
        ui._overview_read('Reading...', fail)
    assert capsys.readouterr().out.endswith('\r' + ' '*len('Reading...') + '\r')


def test_repeated_category_is_unavailable_not_double_counted():
    e = Mock()
    e.browse.return_value = [{'label':'rat','samples':1}]*21
    with pytest.raises(ExplorerUnavailable, match='repeated'):
        ui._overview_types(e)
