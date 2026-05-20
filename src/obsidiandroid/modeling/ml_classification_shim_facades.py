# Filename: src/obsidiandroid/modeling/ml_classification_shim_facades.py
"""Compatibility wrapper for legacy ``ml_classification.*`` shim manifests.

Canonical shim-manifest definitions now live in
:mod:`obsidiandroid.modeling.legacy_ml_classification_manifest`. This module is retained
so existing tests, scripts, and repo-root package shims keep working during the
structure migration.
"""

from __future__ import annotations

from obsidiandroid.modeling.legacy_ml_classification_manifest import *  # noqa: F403
from obsidiandroid.modeling.legacy_ml_classification_manifest import __all__  # noqa: F401
