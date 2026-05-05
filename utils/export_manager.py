"""Compatibility shim: ``utils.export_manager`` aliases the canonical module object.

Implementation lives in :mod:`obsidiandroid.reporting.export_manager`. The import
system entry for ``utils.export_manager`` is replaced with the canonical module so
``from utils import export_manager`` and ``import obsidiandroid.reporting.export_manager``
refer to the same object (monkeypatches and identity checks stay stable).
"""

from __future__ import annotations

import sys

import utils.repo_import_paths  # noqa: F401

from obsidiandroid.reporting import export_manager as _canonical

sys.modules[__name__] = _canonical
