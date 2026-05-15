"""Legacy shim for ``ml_classification.training.feature_schema_audit``.

Canonical implementation lives at ``obsidiandroid.features.feature_schema_audit``.
"""

from __future__ import annotations

import sys

from obsidiandroid.legacy_shim_lazy import import_legacy_shim

_mod = import_legacy_shim("obsidiandroid.features.feature_schema_audit", __name__)
sys.modules[__name__] = _mod
