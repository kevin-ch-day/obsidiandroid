"""Small UTF-8 JSON file helpers shared across reporting, diagnostics, and CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json_dict(path: Path | str) -> dict[str, Any]:
    """Load a JSON object from disk.

    Returns an empty dict when the path is missing, unreadable, invalid JSON,
    or when the document root is not a JSON object (e.g. array or scalar).
    """
    p = Path(path)
    if not p.is_file():
        return {}
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
