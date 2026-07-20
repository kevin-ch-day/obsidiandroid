# Filename: src/obsidiandroid/database/db_engine.py
# Purpose  : Centralized MySQL engine for ObsidianDroid platform queries
#
# Canonical implementation; the repo-root ``database.db_engine`` shim has been retired.

import json
from pathlib import Path
import mysql.connector
from mysql.connector import Error
from mysql.connector import pooling
from contextlib import contextmanager
from collections import namedtuple
from time import perf_counter
import pandas as pd

from .db_config import (
    DB_HOST,
    DB_PORT,
    DB_USER,
    DB_PASSWORD,
    DB_NAME,
    DB_OPTION_FILE,
    PERMISSION_INTEL_DB_NAME,
    DB_CHARSET,
    DB_ENABLE_POOLING,
    DB_POOL_SIZE,
    DB_POOL_NAME,
    DB_CONNECT_TIMEOUT,
    PERMISSION_INTEL_DB_HOST,
    PERMISSION_INTEL_DB_PORT,
    PERMISSION_INTEL_DB_USER,
    PERMISSION_INTEL_DB_PASSWORD,
    PERMISSION_INTEL_DB_OPTION_FILE,
    CORE_DB_HOST,
    CORE_DB_PORT,
    CORE_DB_USER,
    CORE_DB_PASSWORD,
    CORE_DB_NAME,
    CORE_PERSISTENCE_ENABLED,
)
from .db_errors import mysql_error_summary, operator_facing_db_message
from config import app_config
from obsidiandroid.observability.logging import get_logger, log_event

DEBUG_SQL = False   # Set True only for dev debugging
VERBOSE_ERRORS = False  # Toggle detailed error logs for production
DB_LOGGER = get_logger(f"{getattr(app_config, 'APP_LOG_NAMESPACE', 'framework')}.db", "database")
_CONNECTION_POOL = None
_CORE_FORBIDDEN_DATABASES = frozenset(
    {"erebus_threat_intel_prod", "android_permission_intel", "scytaledroid_core_prod"}
)
_CORE_READ_ONLY_SQL_PREFIXES = ("SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN")


class CoreDatabaseConfigurationError(RuntimeError):
    """Raised when the isolated ObsidianDroid core connection is unsafe or unavailable."""


class CoreDatabaseWriteBlockedError(CoreDatabaseConfigurationError):
    """Raised when Phase 1 code attempts DDL or DML through the Core helper."""


class SourceDatabaseConfigurationError(RuntimeError):
    """Raised when an upstream source connection lacks explicit credentials."""


def _private_source_option_file(value: str, *, role: str) -> str:
    """Accept only an explicit, private client option file for a source role."""
    path = Path(value).expanduser()
    try:
        mode = path.stat().st_mode & 0o777
    except OSError as exc:
        raise SourceDatabaseConfigurationError(f"{role} option file is unavailable") from exc
    if not path.is_file() or mode & 0o077:
        raise SourceDatabaseConfigurationError(f"{role} option file must be private (0600)")
    return str(path)


def _require_source_connection_config(*, role: str, host: str, user: str, password: str, database: str, option_file: str) -> None:
    if str(option_file or "").strip():
        _private_source_option_file(option_file, role=role)
        if not str(database or "").strip():
            raise SourceDatabaseConfigurationError(f"{role} database configuration is incomplete; missing database")
        return
    missing = [
        name
        for name, value in (("host", host), ("user", user), ("password", password), ("database", database))
        if not str(value or "").strip()
    ]
    if missing:
        raise SourceDatabaseConfigurationError(
            f"{role} database configuration is incomplete; set explicit environment credentials (missing "
            + ", ".join(missing)
            + ")"
        )


def _should_retry_via_tcp_loopback(exc: BaseException, connect_kwargs: dict) -> bool:
    """Return True when a localhost socket-style failure should retry via TCP loopback."""
    host = str(connect_kwargs.get("host") or "").strip().lower()
    if host != "localhost":
        return False
    summary = mysql_error_summary(exc)
    errno = summary.get("errno")
    message = str(summary.get("message") or "").lower()
    return bool(
        errno in {2002, 2003, 2004}
        or "socket" in message
        or "can't connect to local server" in message
        or "can't create tcp/ip socket" in message
    )


def _tcp_loopback_kwargs(connect_kwargs: dict) -> dict:
    """Clone connector kwargs and force TCP loopback instead of localhost/socket lookup."""
    tcp_kwargs = dict(connect_kwargs)
    tcp_kwargs["host"] = "127.0.0.1"
    return tcp_kwargs


def _connect_with_localhost_fallback(connect_kwargs: dict, *, database_name: str):
    """Open a connector connection, retrying localhost failures via 127.0.0.1 when safe."""
    try:
        return mysql.connector.connect(**connect_kwargs)
    except Error as exc:
        if not _should_retry_via_tcp_loopback(exc, connect_kwargs):
            raise
        fallback_kwargs = _tcp_loopback_kwargs(connect_kwargs)
        log_event(
            DB_LOGGER,
            "db_localhost_tcp_fallback",
            original_host=connect_kwargs.get("host"),
            fallback_host=fallback_kwargs.get("host"),
            database=database_name,
            errno=mysql_error_summary(exc).get("errno"),
        )
        return mysql.connector.connect(**fallback_kwargs)


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


def _safe_rollback(conn, *, context: str, original_exc: BaseException | None = None) -> None:
    """Best-effort rollback that never masks the original database failure."""
    if conn is None:
        return
    try:
        conn.rollback()
    except Error as rollback_exc:
        _log_mysql_failure(
            "db_rollback_suppressed",
            rollback_exc,
            context=context,
            during_exception=type(original_exc).__name__ if original_exc is not None else None,
        )
    except Exception:
        pass


def _build_connect_kwargs() -> dict:
    """Build shared connector kwargs for direct and pooled connections (primary DB)."""
    _require_source_connection_config(role="Erebus source", host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME, option_file=DB_OPTION_FILE)
    if str(DB_OPTION_FILE).strip():
        return {
            "option_files": _private_source_option_file(DB_OPTION_FILE, role="Erebus source"),
            "database": DB_NAME,
            "charset": DB_CHARSET,
            "autocommit": False,
            "connection_timeout": max(2, int(DB_CONNECT_TIMEOUT)),
        }
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
    _require_source_connection_config(
        role="Permission Intel source",
        host=PERMISSION_INTEL_DB_HOST,
        user=PERMISSION_INTEL_DB_USER,
        password=PERMISSION_INTEL_DB_PASSWORD,
        database=PERMISSION_INTEL_DB_NAME,
        option_file=PERMISSION_INTEL_DB_OPTION_FILE,
    )
    if str(PERMISSION_INTEL_DB_OPTION_FILE).strip():
        return {
            "option_files": _private_source_option_file(PERMISSION_INTEL_DB_OPTION_FILE, role="Permission Intel source"),
            "database": PERMISSION_INTEL_DB_NAME,
            "charset": DB_CHARSET,
            "autocommit": False,
            "connection_timeout": max(2, int(DB_CONNECT_TIMEOUT)),
        }
    return {
        "host": PERMISSION_INTEL_DB_HOST,
        "port": PERMISSION_INTEL_DB_PORT,
        "user": PERMISSION_INTEL_DB_USER,
        "password": PERMISSION_INTEL_DB_PASSWORD,
        "database": PERMISSION_INTEL_DB_NAME,
        "charset": DB_CHARSET,
        "autocommit": False,
        "connection_timeout": max(2, int(DB_CONNECT_TIMEOUT)),
    }


def _build_core_connect_kwargs() -> dict:
    """Build connector kwargs for the independently configured core ledger.

    Core settings intentionally have no fallback to the primary Erebus settings.
    This makes an omitted service-account configuration a visible preflight
    failure rather than a silent source-database write.
    """
    missing = [
        name
        for name, value in (
            ("OBSIDIANDROID_CORE_DB_HOST", CORE_DB_HOST),
            ("OBSIDIANDROID_CORE_DB_USER", CORE_DB_USER),
            ("OBSIDIANDROID_CORE_DB_PASSWORD", CORE_DB_PASSWORD),
        )
        if not str(value or "").strip()
    ]
    if missing:
        raise CoreDatabaseConfigurationError(
            "Core database configuration is incomplete; missing " + ", ".join(missing)
        )
    _validate_core_database_name(CORE_DB_NAME)
    return {
        "host": CORE_DB_HOST,
        "port": CORE_DB_PORT,
        "user": CORE_DB_USER,
        "password": CORE_DB_PASSWORD,
        "database": CORE_DB_NAME,
        "charset": DB_CHARSET,
        "autocommit": False,
        "connection_timeout": max(2, int(DB_CONNECT_TIMEOUT)),
    }


def _validate_core_database_name(database_name: str) -> str:
    """Reject source and unrelated database names from the core connection."""
    name = str(database_name or "").strip()
    if not name:
        raise CoreDatabaseConfigurationError("Core database name is empty")
    if name.casefold() in _CORE_FORBIDDEN_DATABASES:
        raise CoreDatabaseConfigurationError(
            f"Unsafe core database name {name!r}; source and Scytale catalogs are forbidden"
        )
    return name


def _get_connection():
    """Return a database connection, optionally from a connector-managed pool."""
    global _CONNECTION_POOL
    use_pool = bool(DB_ENABLE_POOLING)
    if not use_pool:
        return _connect_with_localhost_fallback(
            _build_connect_kwargs(),
            database_name=DB_NAME,
        )

    if _CONNECTION_POOL is None:
        connect_kwargs = _build_connect_kwargs()
        try:
            _CONNECTION_POOL = pooling.MySQLConnectionPool(
                pool_name=str(DB_POOL_NAME),
                pool_size=max(1, int(DB_POOL_SIZE)),
                **connect_kwargs,
            )
        except Error as exc:
            if not _should_retry_via_tcp_loopback(exc, connect_kwargs):
                raise
            fallback_kwargs = _tcp_loopback_kwargs(connect_kwargs)
            log_event(
                DB_LOGGER,
                "db_pool_localhost_tcp_fallback",
                original_host=connect_kwargs.get("host"),
                fallback_host=fallback_kwargs.get("host"),
                database=DB_NAME,
                errno=mysql_error_summary(exc).get("errno"),
            )
            _CONNECTION_POOL = pooling.MySQLConnectionPool(
                pool_name=f"{DB_POOL_NAME}_tcp",
                pool_size=max(1, int(DB_POOL_SIZE)),
                **fallback_kwargs,
            )
    return _CONNECTION_POOL.get_connection()


def _get_permission_intel_connection():
    """Return a connection to the Permission Intel schema (no pooling for secondary DB)."""
    return _connect_with_localhost_fallback(
        _build_permission_intel_connect_kwargs(),
        database_name=PERMISSION_INTEL_DB_NAME,
    )


def _get_core_connection():
    """Open a core-ledger connection after configuration validation."""
    kwargs = _build_core_connect_kwargs()
    return _connect_with_localhost_fallback(kwargs, database_name=CORE_DB_NAME)


# === Connection Context Managers === #
@contextmanager
def database_connection():
    conn = None
    try:
        conn = _get_connection()
        yield conn
        conn.commit()
    except (Error, SourceDatabaseConfigurationError) as e:
        _log_mysql_failure("db_connection_error", e, database=DB_NAME)
        if VERBOSE_ERRORS:
            print(f"[ERROR] DB connection error: {e}")
        if conn:
            _safe_rollback(conn, context="database_connection", original_exc=e)
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
    except (Error, SourceDatabaseConfigurationError) as e:
        _log_mysql_failure(
            "permission_intel_connection_error",
            e,
            database=PERMISSION_INTEL_DB_NAME,
        )
        if VERBOSE_ERRORS:
            print(f"[ERROR] Permission Intel DB connection error: {e}")
        if conn:
            _safe_rollback(conn, context="permission_intel_database_connection", original_exc=e)
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()


@contextmanager
def core_database_connection():
    """Yield an isolated core-ledger connection with an explicit UTC session.

    No caller may use this context until the server confirms that ``DATABASE()``
    is the configured core schema.  This is deliberately separate from both
    source connection helpers and does not pool credentials with them.
    """
    conn = None
    try:
        conn = _get_core_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SET time_zone = '+00:00'")
            cursor.execute("SELECT DATABASE()")
            row = cursor.fetchone()
            actual = str(row[0] if row else "").strip()
        finally:
            cursor.close()
        expected = _validate_core_database_name(CORE_DB_NAME)
        if actual != expected:
            raise CoreDatabaseConfigurationError(
                f"Core connection schema mismatch: expected {expected!r}, got {actual!r}"
            )
        yield conn
        conn.commit()
    except Exception as exc:
        if conn:
            _safe_rollback(conn, context="core_database_connection", original_exc=exc)
        if isinstance(exc, CoreDatabaseConfigurationError):
            raise
        _log_mysql_failure("core_database_connection_error", exc, database=CORE_DB_NAME)
        raise CoreDatabaseConfigurationError(
            "Core database connection failed; no fallback to Erebus is permitted"
        ) from exc
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
    active_exc: BaseException | None = None
    try:
        if DEBUG_SQL:
            print("[SQL] Query:", query)
            if params:
                print("[SQL] Params:", params)
            if getattr(app_config, "ENABLE_DB_LOGGING", True):
                log_event(
                    DB_LOGGER,
                    "sql_debug",
                    level="DEBUG",
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

    except (Error, SourceDatabaseConfigurationError) as e:
        active_exc = e
        _log_mysql_failure(
            "sql_error",
            e,
            log_label=log_label,
            duration_ms=round((perf_counter() - started) * 1000, 2),
            query_preview=query if DEBUG_SQL else "<hidden>",
        )
        if VERBOSE_ERRORS:
            print(f"[ERROR] SQL execution failed\nQuery: {query}\nError: {e}")
        _safe_rollback(conn, context="_run_query", original_exc=e)
        raise
    except BaseException as e:
        active_exc = e
        try:
            if conn:
                _safe_rollback(conn, context="_run_query_base_exception", original_exc=e)
        except Exception:
            pass
        raise
    finally:
        try:
            cursor.close()
        except Error as close_exc:
            if active_exc is None:
                raise
            _log_mysql_failure(
                "sql_cursor_close_suppressed",
                close_exc,
                log_label=log_label,
                during_exception=type(active_exc).__name__,
            )


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


def execute_core_query(
    query,
    params=None,
    fetch=False,
    return_columns=False,
    as_dataframe=False,
    as_namedtuple=False,
):
    """Execute a read-only query through the verified ObsidianDroid Core connection.

    Phase 1 intentionally exposes no Core DDL/DML helper.  Future persistence
    must use a separately reviewed Phase 2 write path rather than turning this
    diagnostic/read-preflight helper into an implicit writer.
    """
    _assert_core_read_only_query(query)
    started = perf_counter()
    with core_database_connection() as conn:
        return _run_query(
            conn,
            query,
            params=params,
            fetch=fetch,
            return_columns=return_columns,
            as_dataframe=as_dataframe,
            as_namedtuple=as_namedtuple,
            started=started,
            log_label="core_sql",
        )


def _assert_core_read_only_query(query: object) -> None:
    """Reject empty, multi-statement, and write SQL in the Phase 1 Core helper."""
    statement = str(query or "").strip()
    if not statement:
        raise CoreDatabaseWriteBlockedError("Core query is empty; only read-only SQL is permitted in Phase 1")
    if statement.endswith(";"):
        statement = statement[:-1].rstrip()
    if ";" in statement:
        raise CoreDatabaseWriteBlockedError(
            "Core multi-statement SQL is blocked; only one read-only statement is permitted in Phase 1"
        )
    keyword = statement.split(None, 1)[0].upper() if statement else ""
    if keyword not in _CORE_READ_ONLY_SQL_PREFIXES:
        allowed = ", ".join(_CORE_READ_ONLY_SQL_PREFIXES)
        raise CoreDatabaseWriteBlockedError(
            f"Core {keyword or 'unknown'} SQL is blocked in Phase 1; allowed read-only prefixes: {allowed}"
        )


def core_database_health() -> dict[str, object]:
    """Return a credential-redacted, fail-closed core connection preflight."""
    try:
        with core_database_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT DATABASE(), @@session.time_zone")
                database_name, time_zone = cursor.fetchone()
            finally:
                cursor.close()
        return {
            "ok": True,
            "database": str(database_name),
            "time_zone": str(time_zone),
            "configured_database": CORE_DB_NAME,
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "database": None,
            "time_zone": None,
            "configured_database": CORE_DB_NAME,
            "error": _core_health_error(exc),
        }


def _core_health_error(exc: BaseException) -> str:
    """Return a diagnostic error without exposing connector credentials or endpoint details."""
    if isinstance(exc, CoreDatabaseConfigurationError):
        return str(exc)
    return "Core database connection unavailable"


def core_persistence_preflight() -> dict[str, object]:
    """Fail closed before any future core persistence is permitted.

    Phase 1 deliberately leaves persistence disabled.  Once explicitly enabled,
    the database must contain the single append-only migration ledger defined by
    the reviewed core schema; otherwise callers receive a blocked result and
    must not issue DDL or DML.
    """
    if not CORE_PERSISTENCE_ENABLED:
        return {"ready": False, "status": "disabled", "reason": "feature_flag_disabled"}
    health = core_database_health()
    if not health["ok"]:
        return {"ready": False, "status": "blocked", "reason": "core_connection_unhealthy", "health": health}
    try:
        rows = execute_core_query(
            "SELECT COUNT(*) FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'core_schema_migration'",
            fetch=True,
        )
        if not rows or int(rows[0][0]) != 1:
            return {"ready": False, "status": "blocked", "reason": "core_schema_migration_missing"}
        applied_rows = execute_core_query(
            "SELECT COUNT(*) FROM core_schema_migration "
            "WHERE migration_version = '0001' AND execution_status = 'applied'",
            fetch=True,
        )
        if not applied_rows or int(applied_rows[0][0]) != 1:
            return {"ready": False, "status": "blocked", "reason": "core_schema_migration_not_applied"}
    except Exception as exc:
        return {"ready": False, "status": "blocked", "reason": "core_schema_check_failed", "error": str(exc)}
    return {"ready": True, "status": "ready", "reason": None}


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
    except (Error, SourceDatabaseConfigurationError) as e:
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


def table_exists(table_name: str) -> bool:
    """Return whether *table_name* exists on the appropriate database surface."""
    try:
        return bool(get_table_columns(table_name))
    except Exception:
        return False


# === Basic Connection Diagnostic === #
def test_connection(verbose: bool = False) -> bool:
    """Return True if the primary database accepts a connection, else False."""
    conn = None
    try:
        conn = _connect_with_localhost_fallback(
            _build_connect_kwargs(),
            database_name=DB_NAME,
        )
        if conn.is_connected() and verbose:
            print("[OK] Database connection successful.")
        if conn.is_connected() and getattr(app_config, "ENABLE_DB_LOGGING", True):
            log_event(DB_LOGGER, "test_connection_ok", host=DB_HOST, db=DB_NAME)
        return bool(conn.is_connected())
    except (Error, SourceDatabaseConfigurationError) as e:
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
        conn = _connect_with_localhost_fallback(
            _build_permission_intel_connect_kwargs(),
            database_name=PERMISSION_INTEL_DB_NAME,
        )
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
    except (Error, SourceDatabaseConfigurationError) as e:
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
        conn = _connect_with_localhost_fallback(
            _build_connect_kwargs(),
            database_name=DB_NAME,
        )
        try:
            result["primary_ok"] = bool(conn.is_connected())
        finally:
            if conn and conn.is_connected():
                conn.close()
    except (Error, SourceDatabaseConfigurationError) as e:
        result["primary_error"] = operator_facing_db_message(e) if isinstance(e, Error) else str(e)
        _log_mysql_failure("split_db_health_primary_failed", e, database=DB_NAME)

    try:
        conn = _connect_with_localhost_fallback(
            _build_permission_intel_connect_kwargs(),
            database_name=PERMISSION_INTEL_DB_NAME,
        )
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
    except (Error, SourceDatabaseConfigurationError) as e:
        result["permission_intel_error"] = operator_facing_db_message(e) if isinstance(e, Error) else str(e)
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
