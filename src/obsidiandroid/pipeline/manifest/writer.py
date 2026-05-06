"""Atomic manifest writer utilities."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any


def write_manifest_atomic(
    *,
    target_path: Path,
    payload: dict[str, Any],
    retries: int = 3,
    retry_delay_sec: float = 0.15,
) -> Path:
    """Write manifest atomically with Windows-friendly replace retries.

    Args:
        target_path: Manifest destination.
        payload: Serializable payload.
        retries: Replace retry attempts on file locking errors.
        retry_delay_sec: Delay between retries.

    Returns:
        Final target path.

    Raises:
        OSError: If atomic replace fails after retries.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f"{target_path.name}.",
        suffix=".tmp",
        dir=str(target_path.parent),
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        last_error: OSError | None = None
        for _ in range(max(1, retries)):
            try:
                os.replace(str(tmp_path), str(target_path))
                last_error = None
                break
            except OSError as exc:
                last_error = exc
                time.sleep(max(0.0, retry_delay_sec))
        if last_error is not None:
            raise last_error
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    return target_path
