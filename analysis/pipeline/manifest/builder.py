"""Pure manifest payload assembly helpers."""

from __future__ import annotations

from typing import Any


def build_manifest_payload(base_payload: dict[str, Any], *, artifacts: list[str]) -> dict[str, Any]:
    """Build final manifest payload without performing I/O.

    Args:
        base_payload: Caller-provided manifest dictionary.
        artifacts: Materialized artifact paths.

    Returns:
        New manifest dictionary with stable artifact list.
    """
    manifest = dict(base_payload)
    manifest["artifact_list"] = sorted(set(map(str, artifacts)))
    return manifest

