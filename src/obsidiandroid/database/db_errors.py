# Filename: src/obsidiandroid/database/db_errors.py
# Purpose  : Normalize MySQL connector errors for logging, health checks, and retries.
#
# Canonical implementation; the repo-root ``database.db_errors`` shim has been retired.

from __future__ import annotations

from typing import Any

from mysql.connector import Error as MySQLConnectorError

# errno values commonly treated as transient (network, server restart, locks).
# See MySQL reference manual / connector mapping; not exhaustive.
_TRANSIENT_ERRNOS: frozenset[int] = frozenset(
    {
        1040,  # ER_CON_COUNT_ERROR — too many connections
        1205,  # ER_LOCK_WAIT_TIMEOUT
        1213,  # ER_LOCK_DEADLOCK
        2002,  # CR_CONNECTION_ERROR — cannot connect
        2003,  # CR_CONN_HOST_ERROR
        2006,  # CR_SERVER_GONE_ERROR — server has gone away
        2013,  # CR_SERVER_LOST — lost connection during query
        2055,  # CR_FETCH_CANCELED — cursor / connection lost mid-fetch
    }
)


def mysql_error_summary(exc: BaseException) -> dict[str, Any]:
    """Return a JSON/log-friendly summary of a database exception (no passwords)."""
    out: dict[str, Any] = {
        "error_type": type(exc).__name__,
        "errno": None,
        "sqlstate": None,
        "message": "",
        "transient": False,
    }
    if isinstance(exc, MySQLConnectorError):
        errno = getattr(exc, "errno", None)
        out["errno"] = errno
        out["sqlstate"] = getattr(exc, "sqlstate", None)
        raw_msg = getattr(exc, "msg", None) or str(exc)
        out["message"] = str(raw_msg).replace("\n", " ").strip()[:500]
        try:
            out["transient"] = bool(errno is not None and int(errno) in _TRANSIENT_ERRNOS)
        except (TypeError, ValueError):
            out["transient"] = False
    else:
        out["message"] = str(exc).replace("\n", " ").strip()[:500]
    return out


def operator_facing_db_message(exc: BaseException, *, max_len: int = 240) -> str:
    """Short, user-facing message for CLI/health JSON (no stack traces)."""
    summary = mysql_error_summary(exc)
    parts: list[str] = []
    if summary.get("errno") is not None:
        parts.append(f"MySQL errno {summary['errno']}")
    if summary.get("sqlstate"):
        parts.append(f"SQLSTATE {summary['sqlstate']}")
    msg = str(summary.get("message") or "").strip()
    if msg:
        parts.append(msg[: max_len - 20])
    text = " — ".join(parts) if parts else summary.get("error_type", "database_error")
    return text[:max_len]


def is_transient_mysql_error(exc: BaseException) -> bool:
    """Return True when the error is often retryable (locks, dropped connections)."""
    return bool(mysql_error_summary(exc).get("transient"))
