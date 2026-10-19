"""DST and minute-precision presentation across calendar and clock boundaries."""
from datetime import datetime, timezone
import logging
import pytest
from obsidiandroid.common.time_display import format_timestamp, LocalUTCFormatter

@pytest.mark.parametrize('instant,local', [
    ('2026-10-18T02:00:59Z', 'Oct 17, 2026 · 9:00 PM CDT'),
    ('2026-12-16T03:00:59Z', 'Dec 15, 2026 · 9:00 PM CST'),
    ('2026-03-08T07:59:59Z', 'Mar 8, 2026 · 1:59 AM CST'),
    ('2026-03-08T08:00:00Z', 'Mar 8, 2026 · 3:00 AM CDT'),
    ('2026-11-01T06:30:00Z', 'Nov 1, 2026 · 1:30 AM CDT'),
    ('2026-11-01T07:30:00Z', 'Nov 1, 2026 · 1:30 AM CST'),
    ('2027-07-01T17:45:33Z', 'Jul 1, 2027 · 12:45 PM CDT'),
    ('2020-01-02T06:00:00Z', 'Jan 2, 2020 · 12:00 AM CST'),
])
def test_date_specific_zone_and_no_seconds(instant, local):
    text = format_timestamp(instant)
    assert text.startswith(local + ' | ')
    assert text.endswith(' UTC')
    assert ':59:' not in text and ':00:' not in text and ':45:' not in text


def test_unknown_zone_and_date_only_are_not_invented():
    assert format_timestamp('2026-10-17') == '2026-10-17'
    value = datetime(2026, 10, 18, 2)
    assert format_timestamp(value) is value
    assert '9:00 PM CDT' in format_timestamp(value, assume_utc=True)


def test_log_uses_record_time_not_current_zone():
    record = logging.LogRecord('test', logging.INFO, '', 0, 'hello', (), None)
    record.created = datetime(2026, 12, 16, 3, tzinfo=timezone.utc).timestamp()
    text = LocalUTCFormatter('%(asctime)s %(message)s').format(record)
    assert '9:00 PM CST' in text and '3:00 AM UTC' in text


def test_shared_console_table_does_not_mutate_source(capsys):
    import pandas as pd
    from obsidiandroid.cli.ui.display import print_table
    frame = pd.DataFrame({'timestamp_utc': ['2026-10-18T02:45:38Z']})
    print_table(frame)
    text = capsys.readouterr().out
    assert '9:45 PM CDT' in text and '2:45 AM UTC' in text
    assert frame.iloc[0, 0] == '2026-10-18T02:45:38Z'


def test_missing_timestamp_remains_missing():
    import pandas as pd
    assert format_timestamp(pd.NaT) is pd.NaT
