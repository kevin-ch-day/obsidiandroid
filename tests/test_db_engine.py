"""Tests for database engine helpers."""

from __future__ import annotations

from mysql.connector import Error

from database import db_engine


def test_test_connection_does_not_raise_unboundlocal_on_connect_failure(monkeypatch) -> None:
    """Connection smoke test should swallow connector errors without masking them."""

    def _raise(*_args, **_kwargs):
        raise Error("boom")

    monkeypatch.setattr(db_engine.mysql.connector, "connect", _raise)
    db_engine.test_connection(verbose=False)
