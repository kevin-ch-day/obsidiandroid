"""Unit tests for database error normalization helpers."""

from __future__ import annotations

from mysql.connector import errors

from obsidiandroid.database.db_errors import (
    is_transient_mysql_error,
    mysql_error_summary,
    operator_facing_db_message,
)


def test_mysql_error_summary_includes_errno_and_transient_flag() -> None:
    exc = errors.OperationalError("server gone", errno=2006)
    s = mysql_error_summary(exc)
    assert s["errno"] == 2006
    assert s["transient"] is True
    assert "gone" in s["message"].lower() or "server" in s["message"].lower()


def test_mysql_error_summary_deadlock_is_transient() -> None:
    exc = errors.OperationalError("deadlock", errno=1213)
    assert mysql_error_summary(exc)["transient"] is True
    assert is_transient_mysql_error(exc) is True


def test_non_mysql_exception_summary() -> None:
    s = mysql_error_summary(ValueError("bad arg"))
    assert s["error_type"] == "ValueError"
    assert s["errno"] is None
    assert s["transient"] is False


def test_operator_facing_db_message_truncates() -> None:
    exc = errors.ProgrammingError("x" * 500, errno=1146)
    msg = operator_facing_db_message(exc, max_len=80)
    assert len(msg) <= 80
    assert "1146" in msg
