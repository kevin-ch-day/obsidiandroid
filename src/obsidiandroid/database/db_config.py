# Filename: src/obsidiandroid/database/db_config.py
# db_config.py

"""MySQL connection configuration for ObsidianDroid.

ObsidianDroid uses two logical databases on the same MySQL/MariaDB server by default:

- Primary Erebus schema (samples, VirusTotal, catalog).
- Permission Intel schema (all ``android_permission_*`` live tables).

Override via ``OBSIDIAN_*`` environment variables. Do not commit real passwords.

- ``OBSIDIAN_DB_CONNECT_TIMEOUT`` — TCP/connect timeout in seconds (default ``30``).

Optional: place a repo-root ``.env`` or ``.env.local`` file; variables are loaded
with ``override=False`` so existing shell exports still win.

Canonical implementation; ``database.db_config`` is an identity shim.
"""

from __future__ import annotations

import os
from pathlib import Path


def _repo_root() -> Path:
    """Checkout root (``<repo>``) when this file lives under ``<repo>/src/...``."""
    here = Path(__file__).resolve()
    if len(here.parents) >= 4 and here.parents[2].name == "src":
        return here.parents[3]
    return Path.cwd()


def _load_env_files() -> None:
    """Load optional repo-root dotenv files when python-dotenv is installed."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    root = _repo_root()
    for name in (".env", ".env.local"):
        path = root / name
        if path.is_file():
            load_dotenv(path, override=False)


_load_env_files()

# === MySQL Database Connection Configuration === #

DB_HOST = os.getenv("OBSIDIAN_DB_HOST", "localhost")
DB_PORT = int(os.getenv("OBSIDIAN_DB_PORT", "3306"))
DB_USER = os.getenv("OBSIDIAN_DB_USER", "root")
DB_PASSWORD = os.getenv("OBSIDIAN_DB_PASSWORD", "Password123!")
DB_NAME = os.getenv("OBSIDIAN_DB_NAME", "erebus_threat_intel_prod")

PERMISSION_INTEL_DB_NAME = os.getenv(
    "OBSIDIAN_PERMISSION_INTEL_DB_NAME",
    "android_permission_intel",
)

# === Optional Advanced Settings === #

DB_CHARSET = os.getenv("OBSIDIAN_DB_CHARSET", "utf8mb4")
DB_ENABLE_POOLING = os.getenv("OBSIDIAN_DB_ENABLE_POOLING", "false").lower() in (
    "1",
    "true",
    "yes",
)
DB_POOL_SIZE = int(os.getenv("OBSIDIAN_DB_POOL_SIZE", "8"))
DB_POOL_NAME = os.getenv("OBSIDIAN_DB_POOL_NAME", "obsidiandroid_pool")

# TCP/connect timeout in seconds (passed to mysql-connector ``connection_timeout``).
DB_CONNECT_TIMEOUT = int(os.getenv("OBSIDIAN_DB_CONNECT_TIMEOUT", "30"))
