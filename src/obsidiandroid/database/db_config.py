# Filename: src/obsidiandroid/database/db_config.py
# db_config.py

"""MySQL connection configuration for ObsidianDroid.

ObsidianDroid uses two upstream read-only logical databases on the same MySQL/MariaDB
server by default, plus a planned curated research ledger (v2.2+):

- Primary Erebus schema (samples, VirusTotal, catalog).
- Permission Intel schema (all ``android_permission_*`` live tables).
- ObsidianDroid research schema (curated run outputs; ``OBSIDIANDROID_RESEARCH_DB_NAME``).

Override via ``OBSIDIAN_*`` environment variables. Do not commit real passwords.

- ``OBSIDIAN_DB_CONNECT_TIMEOUT`` — TCP/connect timeout in seconds (default ``30``).

Optional: place a repo-root ``.env`` or ``.env.local`` file; variables are loaded
with ``override=False`` so existing shell exports still win.

Canonical implementation; the repo-root ``database.db_config`` shim has been retired.
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


def _env_first(names: tuple[str, ...], default: str) -> str:
    """Return the first non-empty environment value across compatible variable names."""
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip() != "":
            return str(value)
    return default


def _env_first_int(names: tuple[str, ...], default: int) -> int:
    """Return the first valid integer env value across compatible variable names."""
    for name in names:
        value = os.getenv(name)
        if value is None or str(value).strip() == "":
            continue
        try:
            return int(str(value).strip())
        except ValueError:
            continue
    return int(default)

# === MySQL Database Connection Configuration === #

DB_HOST = _env_first(("OBSIDIAN_DB_HOST", "EREBUS_DB_HOST"), "localhost")
DB_PORT = _env_first_int(("OBSIDIAN_DB_PORT", "EREBUS_DB_PORT"), 3306)
DB_USER = _env_first(("OBSIDIAN_DB_USER", "EREBUS_DB_USER"), "root")
DB_PASSWORD = _env_first(("OBSIDIAN_DB_PASSWORD", "EREBUS_DB_PASSWORD"), "Password123!")
DB_NAME = _env_first(("OBSIDIAN_DB_NAME", "EREBUS_DB_NAME"), "erebus_threat_intel_prod")

PERMISSION_INTEL_DB_NAME = _env_first(
    (
        "OBSIDIAN_PERMISSION_INTEL_DB_NAME",
        "EREBUS_PERMISSION_INTEL_DB_NAME",
        "ANDROID_PERMISSION_INTEL_DB_NAME",
    ),
    "android_permission_intel",
)
PERMISSION_INTEL_DB_HOST = _env_first(
    ("OBSIDIAN_PERMISSION_INTEL_DB_HOST", "EREBUS_PERMISSION_INTEL_DB_HOST"),
    DB_HOST,
)
PERMISSION_INTEL_DB_PORT = _env_first_int(
    ("OBSIDIAN_PERMISSION_INTEL_DB_PORT", "EREBUS_PERMISSION_INTEL_DB_PORT"),
    DB_PORT,
)
PERMISSION_INTEL_DB_USER = _env_first(
    ("OBSIDIAN_PERMISSION_INTEL_DB_USER", "EREBUS_PERMISSION_INTEL_DB_USER"),
    DB_USER,
)
PERMISSION_INTEL_DB_PASSWORD = _env_first(
    ("OBSIDIAN_PERMISSION_INTEL_DB_PASSWORD", "EREBUS_PERMISSION_INTEL_DB_PASSWORD"),
    DB_PASSWORD,
)

# Curated ObsidianDroid research ledger (v2.2+). No runtime writes until importer --apply.
RESEARCH_DB_HOST = _env_first(("OBSIDIANDROID_RESEARCH_DB_HOST",), DB_HOST)
RESEARCH_DB_PORT = _env_first_int(("OBSIDIANDROID_RESEARCH_DB_PORT",), DB_PORT)
RESEARCH_DB_USER = _env_first(("OBSIDIANDROID_RESEARCH_DB_USER",), DB_USER)
RESEARCH_DB_PASSWORD = _env_first(
    ("OBSIDIANDROID_RESEARCH_DB_PASSWORD",),
    DB_PASSWORD,
)
RESEARCH_DB_NAME = _env_first(
    ("OBSIDIANDROID_RESEARCH_DB_NAME", "OBSIDIAN_RESEARCH_DB_NAME"),
    "obsidiandroid_research",
)

# === Optional Advanced Settings === #

DB_CHARSET = _env_first(("OBSIDIAN_DB_CHARSET",), "utf8mb4")
DB_ENABLE_POOLING = _env_first(("OBSIDIAN_DB_ENABLE_POOLING",), "false").lower() in (
    "1",
    "true",
    "yes",
)
DB_POOL_SIZE = _env_first_int(("OBSIDIAN_DB_POOL_SIZE",), 8)
DB_POOL_NAME = _env_first(("OBSIDIAN_DB_POOL_NAME",), "obsidiandroid_pool")

# TCP/connect timeout in seconds (passed to mysql-connector ``connection_timeout``).
DB_CONNECT_TIMEOUT = _env_first_int(("OBSIDIAN_DB_CONNECT_TIMEOUT",), 30)
