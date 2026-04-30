# Filename: db_engine.py
# Purpose  : Centralized MySQL engine for ObsidianDroid platform queries

import mysql.connector
from mysql.connector import Error
from mysql.connector import pooling
from contextlib import contextmanager
from collections import namedtuple
from time import perf_counter
import pandas as pd

from database.db_config import (
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_CHARSET,
    DB_ENABLE_POOLING, DB_POOL_SIZE, DB_POOL_NAME
)
from config import app_config
from utils.logging import get_logger, log_event

DEBUG_SQL = False   # Set True only for dev debugging
VERBOSE_ERRORS = False  # Toggle detailed error logs for production
DB_LOGGER = get_logger(f"{getattr(app_config, 'APP_LOG_NAMESPACE', 'framework')}.db", "database")
_CONNECTION_POOL = None


def _build_connect_kwargs() -> dict:
    """Build shared connector kwargs for direct and pooled connections."""
    return {
        "host": DB_HOST,
        "port": DB_PORT,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "database": DB_NAME,
        "charset": DB_CHARSET,
        "autocommit": False,
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


# === Connection Context Manager === #
@contextmanager
def database_connection():
    conn = None
    try:
        conn = _get_connection()
        yield conn
        conn.commit()
    except Error as e:
        if getattr(app_config, "ENABLE_DB_LOGGING", True):
            DB_LOGGER.error("db_connection_error error=%r", e, exc_info=True)
        if VERBOSE_ERRORS:
            print(f"[ERROR] DB connection error: {e}")
        if conn:
            conn.rollback()
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()


# === Core Query Executor === #
def execute_query(
    query,
    params=None,
    fetch=False,
    return_columns=False,
    as_dataframe=False,
    as_namedtuple=False
):
    started = perf_counter()
    with database_connection() as conn:
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
                        "sql_exec",
                        fetch=False,
                        duration_ms=round((perf_counter() - started) * 1000, 2),
                    )
                return

            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            if getattr(app_config, "ENABLE_DB_LOGGING", True):
                log_event(
                    DB_LOGGER,
                    "sql_fetch",
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
            if getattr(app_config, "ENABLE_DB_LOGGING", True):
                DB_LOGGER.error(
                    "sql_error error=%r duration_ms=%.2f query=%r",
                    e,
                    (perf_counter() - started) * 1000,
                    query if DEBUG_SQL else "<hidden>",
                    exc_info=True,
                )
            if VERBOSE_ERRORS:
                print(f"[ERROR] SQL execution failed\nQuery: {query}\nError: {e}")
            conn.rollback()
            raise
        finally:
            cursor.close()


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
def get_table_columns(table_name: str) -> list:
    """
    Return a list of column names for the given table.
    """
    try:
        query = f"SHOW COLUMNS FROM `{table_name}`"
        rows = execute_query(query, fetch=True)
        return [row[0] for row in rows]
    except Exception as e:
        if getattr(app_config, "ENABLE_DB_LOGGING", True):
            DB_LOGGER.error("get_table_columns_error table=%r error=%r", table_name, e, exc_info=True)
        if VERBOSE_ERRORS:
            print(f"[ERROR] Failed to get columns for '{table_name}': {e}")
        return []


# === Basic Connection Diagnostic === #
def test_connection(verbose: bool = False):
    conn = None
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        if conn.is_connected() and verbose:
            print("[OK] Database connection successful.")
        if conn.is_connected() and getattr(app_config, "ENABLE_DB_LOGGING", True):
            log_event(DB_LOGGER, "test_connection_ok", host=DB_HOST, db=DB_NAME)
    except Error as e:
        if getattr(app_config, "ENABLE_DB_LOGGING", True):
            DB_LOGGER.error("test_connection_error error=%r", e, exc_info=True)
        if verbose:
            print(f"[ERROR] Connection failed: {e}")
    finally:
        if conn and conn.is_connected():
            conn.close()
