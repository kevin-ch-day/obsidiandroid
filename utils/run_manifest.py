"""Run manifest generation utilities."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from config import app_config
from database import db_engine
from utils.hash_utils import hash_payload, short_hash

MANIFEST_SCHEMA_VERSION = "1.0.0"
_INITIAL_MANIFEST_PATH = (
    Path(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")) / "diagnostics" / "run_manifest.latest.json"
)
MANIFEST_PATH = _INITIAL_MANIFEST_PATH


def generate_run_id() -> str:
    """Generate global unique run id."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}__{str(uuid4())[:6]}"


def get_git_commit() -> str:
    """Return short git commit or unknown."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out
    except Exception:
        return "unknown"


def compute_taxonomy_version_hash() -> str:
    """Compute taxonomy version from canonical family snapshot."""
    query = """
        SELECT family_id, family_name
        FROM android_malware_family
        WHERE is_active = 1
        ORDER BY family_id
    """
    cols, rows = db_engine.execute_query(query, fetch=True, return_columns=True)
    payload = [{"family_id": r[0], "family_canonical": r[1]} for r in rows or []]
    return short_hash(hash_payload(payload), 12)


def resolve_manifest_path() -> Path:
    """Return active latest-manifest path for the current runtime context.

    The module-level ``MANIFEST_PATH`` is preserved for backward-compatible
    monkeypatching in tests and callers. When left untouched, the path is
    recomputed from the current ``DEFAULT_OUTPUT_DIR`` so late runtime
    overrides do not keep writing to a stale import-time location.
    """
    configured_path = Path(MANIFEST_PATH)
    if configured_path != _INITIAL_MANIFEST_PATH:
        return configured_path
    return Path(getattr(app_config, "DEFAULT_OUTPUT_DIR", "output")) / "diagnostics" / "run_manifest.latest.json"


def write_run_manifest(manifest: Dict[str, Any]) -> Path:
    """Write manifest file; caller handles fail-closed if this raises."""
    manifest = dict(manifest)
    manifest["manifest_schema_version"] = MANIFEST_SCHEMA_VERSION
    manifest_path = resolve_manifest_path()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
    return manifest_path
