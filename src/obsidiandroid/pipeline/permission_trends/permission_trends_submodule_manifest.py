# Filename: src/obsidiandroid/pipeline/permission_trends/permission_trends_submodule_manifest.py
"""Physical submodule names under :mod:`obsidiandroid.pipeline.permission_trends`.

Shared by the package façade bootstrap and :mod:`scripts.dev.check_import_surface`.
"""

from __future__ import annotations

PERMISSION_TRENDS_FACADE_SUBMODULE_NAMES: tuple[str, ...] = (
    "bundle_manifest",
    "constants",
    "publish_paths",
    "reporting_support",
    "sample_permission_data",
    "stats_core",
)

__all__ = ("PERMISSION_TRENDS_FACADE_SUBMODULE_NAMES",)
