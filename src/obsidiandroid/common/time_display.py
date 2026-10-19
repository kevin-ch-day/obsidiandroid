"""Minnesota/UTC presentation without changing stored timestamps or precision."""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from zoneinfo import ZoneInfo

LOCAL_ZONE = ZoneInfo('America/Chicago')
_ISO_TIME = re.compile(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}')


def format_timestamp(value, *, assume_utc=False):
    """Render an instant in Central time and UTC; leave unknown/date-only values intact.

    Naive values need an explicit UTC source contract. Date-only values are not
    instants and must not move to the preceding local date.
    """
    parsed = value
    if isinstance(value, str):
        if not _ISO_TIME.match(value):
            return value
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return value
    if isinstance(parsed, datetime) and parsed != parsed:  # pandas NaT
        return value
    if not isinstance(parsed, datetime):
        return value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        if not assume_utc:
            return value
        parsed = parsed.replace(tzinfo=timezone.utc)

    def display(dt):
        hour = dt.hour % 12 or 12
        period = 'AM' if dt.hour < 12 else 'PM'
        return f'{dt:%b} {dt.day}, {dt.year} · {hour}:{dt.minute:02d} {period} {dt.tzname()}'

    return f'{display(parsed.astimezone(LOCAL_ZONE))} | {display(parsed.astimezone(timezone.utc))}'


class LocalUTCFormatter(logging.Formatter):
    """Use each log record's actual instant, not today's DST offset."""

    def formatTime(self, record, datefmt=None):
        return format_timestamp(datetime.fromtimestamp(record.created, timezone.utc))
