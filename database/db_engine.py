# Filename: db_engine.py
# Purpose  : Centralized MySQL engine for ObsidianDroid platform queries

import json
import mysql.connector
from mysql.connector import Error
from mysql.connector import pooling
from contextlib import contextmanager
from collections import namedtuple
from time import perf_counter
import pandas as pd

from database.db_config import (
    DB_HOST,
    DB_PORT,
    DB_USER,
    DB_PASSWORD,
    DB_NAME,
    PERMISSION_INTEL_DB_NAME,
    DB_CHARSET,
    DB_ENABLE_POOLING,
    DB_POOL_SIZE,
    DB_POOL_NAME,
    DB_CONNECT_TIMEOUT,
)
from database.db_errors import mysql_error_summary, operator_facing_db_message
from config import app_config
from obsidiandroid.observability.logging import get_logger, log_event

DEBUG_SQL = False   # Set True only for dev debugging
VERBOSE_ERRORS = False  # Toggle detailed error logs for production
DB_LOGGER = get_logger(f"{getattr(app_config, 'APP_LOG_NAMESPACE', 'framework')}.db", "database")
_CONNECTION_POOL = None


def _log_mysql_failure(event: str, exc: BaseException, **extra: object) -> None:
    """Emit a structured DB failure log (errno/sqlstate/transient when available)."""
    if not getattr(app_config, "ENABLE_DB_LOGGING", True):
        return
    summary = mysql_error_summary(exc)
    transient = bool(summary.get("transient"))
    parts = (
        f"{event} error_type={summary['error_type']!r} errno={summary['errno']!r} "
        f"sqlstate={summary['sqlstate']!r} transient={transient} message={summary['message']!r}"
    )
    for k in sorted(extra):
        parts += f" {k}={extra[k]!r}"
    if transient:
        DB_LOGGER.warning(parts, exc_info=True)
    else:
        DB_LOGGER.error(parts, exc_info=True)


def _build_connect_kwargs() -> dict:
    """Build shared connector kwargs for direct and pooled connections (primary DB)."""
    return {
        "host": DB_HOST,
        "port": DB_PORT,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "database": DB_NAME,
        "charset": DB_CHARSET,
        "autocommit": False,
        "connection_timeout": max(2, int(DB_CONNECT_TIMEOUT)),
    }


def _build_permission_intel_connect_kwargs() -> dict:
    """Connector kwargs for the Permission Intel database (android_permission_* tables)."""
    return {
        "host": DB_HOST,
        "port": DB_PORT,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "database": PERMISSION_INTEL_DB_NAME,
        "charset": DB_CHARSET,
        "autocommit": False,
        "connection_timeout": max(2, int(DB_CONNECT_TIMEOUT)),
    }


def _get_connection():
    """Return a database connection, optionally from a connector-managed pool."""
    global _CONNECTION_POOL
    use_pool = bool(DB_ENABLE_POOLING)
    if not use_pool:
        return mysql.connector.connect(**_build_connect_kwargs())

    if _CONNECTION_POOL is None:
        _CONNECTION_POOL = pooling.MySQLConnectionPool(
            pool_name=str(DB_POOL_NAME),
            pool_size=max(1, int(DB_POOL_SIZE)),
            **_build_connect_kwargs(),
        )
    return _CONNECTION_POOL.get_connection()


def _get_permission_intel_connection():
    """Return a connection to the Permission Intel schema (no pooling for secondary DB)."""
    return mysql.connector.connect(**_build_permission_intel_connect_kwargs())


# === Connection Context Managers === #
@contextmanager
def database_connection():
    conn = None
    try:
        conn = _get_connection()
        yield conn
        conn.commit()
    except Error as e:
        _log_mysql_failure("db_connection_error", e, database=DB_NAME)
        if VERBOSE_ERRORS:
            print(f"[ERROR] DB connection error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()


@contextmanager
def permission_intel_database_connection():
    """Context manager for Permission Intel database connections."""
    conn = None
    try:
        conn = _get_permission_intel_connection()
        yield conn
        conn.commit()
    except Error as e:
        _log_mysql_failure(
            "permission_intel_connection_error",
            e,
            database=PERMISSION_INTEL_DB_NAME,
        )
        if VERBOSE_ERRORS:
            print(f"[ERROR] Permission Intel DB connection error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()


def _run_query(
    conn,
    query,
    params=None,
    fetch=False,
    return_columns=False,
    as_dataframe=False,
    as_namedtuple=False,
    started: float | None = None,
    log_label: str = "sql",
):
    """Execute a query on an existing connection (internal)."""
    started = perf_counter() if started is None else started
    cursor = conn.cursor()
    try:
        if DEBUG_SQL:
            print("[SQL] Query:", query)
            if params:
                print("[SQL] Params:", params)
            if getattr(app_config, "ENABLE_DB_LOGGING", True):
                log_event(
                    DB_LOGGER,
                    "sql_debug",
                    query=query,
                    params=params,
                )

        cursor.execute(query, params or ())

        if not fetch:
            if getattr(app_config, "ENABLE_DB_LOGGING", True):
                log_event(
                    DB_LOGGER,
                    f"{log_label}_exec",
                    fetch=False,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                )
            return

        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        if getattr(app_config, "ENABLE_DB_LOGGING", True):
            log_event(
                DB_LOGGER,
                f"{log_label}_fetch",
                rows=len(rows),
                columns=len(columns),
                as_dataframe=as_dataframe,
                as_namedtuple=as_namedtuple,
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )

        if as_dataframe:
            return pd.DataFrame(rows, columns=columns)

        if as_namedtuple:
            Row = namedtuple("Row", columns)
            return [Row(*r) for r in rows]

        if return_columns:
            return columns, rows

        return rows

    except Error as e:
        _log_mysql_failure(
            "sql_error",
            e,
            log_label=log_label,
            duration_ms=round((perf_counter() - started) * 1000, 2),
            query_preview=query if DEBUG_SQL else "<hidden>",
        )
        if VERBOSE_ERRORS:
            print(f"[ERROR] SQL execution failed\nQuery: {query}\nError: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()


# === Core Query Executors === #
def execute_query(
    query,
    params=None,
    fetch=False,
    return_columns=False,
    as_dataframe=False,
    as_namedtuple=False,
):
    """Execute SQL against the primary Erebus database (samples, VT, catalog)."""
    started = perf_counter()
    with database_connection() as conn:
        return _run_query(
            conn,
            query,
            params=params,
            fetch=fetch,
            return_columns=return_columns,
            as_dataframe=as_dataframe,
            as_namedtuple=as_namedtuple,
            started=started,
            log_label="sql",
        )


def execute_permission_query(
    query,
    params=None,
    fetch=False,
    return_columns=False,
    as_dataframe=False,
    as_namedtuple=False,
):
    """Execute SQL against the Permission Intel database (android_permission_* tables)."""
    started = perf_counter()
    with permission_intel_database_connection() as conn:
        return _run_query(
            conn,
            query,
            params=params,
            fetch=fetch,
            return_columns=return_columns,
            as_dataframe=as_dataframe,
            as_namedtuple=as_namedtuple,
            started=started,
            log_label="permission_sql",
        )


# === Insert / Update / Delete Utilities === #
def execute_insert(table: str, data: dict):
    cols = ', '.join(data.keys())
    placeholders = ', '.join(['%s'] * len(data))
    query = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
    execute_query(query, tuple(data.values()))


def execute_update(table: str, data: dict, condition_column: str, condition_value):
    set_clause = ', '.join([f"{col} = %s" for col in data])
    query = f"UPDATE {table} SET {set_clause} WHERE {condition_column} = %s"
    values = tuple(data.values()) + (condition_value,)
    execute_query(query, values)


def execute_delete(table: str, condition_column: str, condition_value):
    query = f"DELETE FROM {table} WHERE {condition_column} = %s"
    execute_query(query, (condition_value,))


# === Table Metadata Utility === #
def _show_columns_statement(table_name: str) -> tuple[str, bool]:
    """Build ``SHOW COLUMNS FROM ...`` SQL and whether it targets Permission Intel.

    ``android_permission_*`` live tables exist only in Permission Intel after the
    post-quarantine split; routing avoids silent failures when primary has no
    matching table.

    Args:
        table_name: Unqualified name, or ``schema`.`table`` with schema matching
            ``PERMISSION_INTEL_DB_NAME`` for PI tables.

    Returns:
        ``(sql, use_permission_intel_executor)``
    """
    raw = str(table_name).strip().strip("`")
    if "." in raw:
        schema_part, base_part = raw.rsplit(".", 1)
        schema = schema_part.strip().strip("`")
        base = base_part.strip().strip("`")
        qualified = f"`{schema}`.`{base}`"
        sql = f"SHOW COLUMNS FROM {qualified}"
        pi = base.startswith("android_permission_") and schema == PERMISSION_INTEL_DB_NAME
        return sql, pi
    base = raw
    if base.startswith("android_permission_"):
        qualified = f"`{PERMISSION_INTEL_DB_NAME}`.`{base}`"
        return f"SHOW COLUMNS FROM {qualified}", True
    return f"SHOW COLUMNS FROM `{base}`", False


def get_table_columns(table_name: str) -> list:
    """Return column names for *table_name*.

    Tables whose base name starts with ``android_permission_`` are inspected on
    the Permission Intel database; other tables use the primary database.
    """
    try:
        query, use_pi = _show_columns_statement(table_name)
        runner = execute_permission_query if use_pi else execute_query
        rows = runner(query, fetch=True)
        return [row[0] for row in rows]
    except Error as e:
        _log_mysql_failure("get_table_columns_error", e, table=table_name)
        if VERBOSE_ERRORS:
            print(f"[ERROR] Failed to get columns for '{table_name}': {e}")
        return []
    except Exception as e:
        if getattr(app_config, "ENABLE_DB_LOGGING", True):
            DB_LOGGER.error(
                "get_table_columns_error table=%r error=%r",
                table_name,
                e,
                exc_info=True,
            )
        if VERBOSE_ERRORS:
            print(f"[ERROR] Failed to get columns for '{table_name}': {e}")
        return []


# === Basic Connection Diagnostic === #
def test_connection(verbose: bool = False) -> bool:
    """Return True if the primary database accepts a connection, else False."""
    conn = None
    try:
        conn = mysql.connector.connect(**_build_connect_kwargs())
        if conn.is_connected() and verbose:
            print("[OK] Database connection successful.")
        if conn.is_connected() and getattr(app_config, "ENABLE_DB_LOGGING", True):
            log_event(DB_LOGGER, "test_connection_ok", host=DB_HOST, db=DB_NAME)
        return bool(conn.is_connected())
    except Error as e:
        _log_mysql_failure("test_connection_error", e, database=DB_NAME)
        if verbose:
            print(f"[ERROR] Connection failed: {e}")
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def test_permission_intel_connection(verbose: bool = False) -> bool:
    """Smoke-test connectivity to the Permission Intel database."""
    conn = None
    try:
        conn = mysql.connector.connect(**_build_permission_intel_connect_kwargs())
        if conn.is_connected() and verbose:
            print("[OK] Permission Intel database connection successful.")
        if conn.is_connected() and getattr(app_config, "ENABLE_DB_LOGGING", True):
            log_event(
                DB_LOGGER,
                "test_permission_intel_ok",
                host=DB_HOST,
                db=PERMISSION_INTEL_DB_NAME,
            )
        return bool(conn.is_connected())
    except Error as e:
        _log_mysql_failure(
            "test_permission_intel_error",
            e,
            database=PERMISSION_INTEL_DB_NAME,
        )
        if verbose:
            print(f"[ERROR] Permission Intel connection failed: {e}")
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def check_split_database_health() -> dict:
    """Verify primary DB, Permission Intel DB, and ``android_permission_obs_sample`` in PI.

    Returns:
        Dict with keys: ``primary_ok``, ``permission_intel_ok``,
        ``permission_obs_sample_in_pi`` (all booleans), plus optional
        ``primary_error`` / ``permission_intel_error`` (short strings when checks fail).
    """
    result: dict = {
        "primary_ok": False,
        "permission_intel_ok": False,
        "permission_obs_sample_in_pi": False,
        "primary_error": None,
        "permission_intel_error": None,
    }
    try:
        conn = mysql.connector.connect(**_build_connect_kwargs())
        try:
            result["primary_ok"] = bool(conn.is_connected())
        finally:
            if conn and conn.is_connected():
                conn.close()
    except Error as e:
        result["primary_error"] = operator_facing_db_message(e)
        _log_mysql_failure("split_db_health_primary_failed", e, database=DB_NAME)

    try:
        conn = mysql.connector.connect(**_build_permission_intel_connect_kwargs())
        try:
            if conn.is_connected():
                cur = conn.cursor()
                try:
                    cur.execute(
                        """
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = %s AND table_name = %s
                        LIMIT 1
                        """,
                        (PERMISSION_INTEL_DB_NAME, "android_permission_obs_sample"),
                    )
                    result["permission_obs_sample_in_pi"] = cur.fetchone() is not None
                    result["permission_intel_ok"] = True
                except Error as inner:
                    result["permission_intel_ok"] = False
                    result["permission_intel_error"] = operator_facing_db_message(inner)
                    _log_mysql_failure(
                        "split_db_health_pi_metadata_query_failed",
                        inner,
                        database=PERMISSION_INTEL_DB_NAME,
                    )
                finally:
                    cur.close()
        finally:
            if conn and conn.is_connected():
                conn.close()
    except Error as e:
        result["permission_intel_error"] = operator_facing_db_message(e)
        _log_mysql_failure(
            "split_db_health_permission_intel_connect_failed",
            e,
            database=PERMISSION_INTEL_DB_NAME,
        )

    return result


def split_database_health_cli() -> int:
    """Print JSON health status; exit 0 if all checks pass."""
    report = check_split_database_health()
    print(json.dumps(report, indent=2))
    if report["primary_ok"] and report["permission_intel_ok"] and report["permission_obs_sample_in_pi"]:
        return 0
    return 1
