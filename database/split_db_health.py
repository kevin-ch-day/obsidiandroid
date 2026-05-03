"""CLI entry point for split-database connectivity checks.

Run:

    python -m database.split_db_health

Exits with status 0 when the primary Erebus DB, Permission Intel DB, and
``android_permission_obs_sample`` (in PI) are all reachable; otherwise 1.
"""

from database.db_engine import split_database_health_cli

if __name__ == "__main__":
    raise SystemExit(split_database_health_cli())
