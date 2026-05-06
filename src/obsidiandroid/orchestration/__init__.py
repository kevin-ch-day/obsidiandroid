"""Pipeline orchestration helpers: profile filters, permission features, methodology exports, runtime reporting.

Implementation is canonical here (**Pass 80**); ``analysis.orchestration`` is an identity shim to this
package and its submodules (same :class:`types.ModuleType` objects).
"""

from __future__ import annotations

import sys

from . import (
    metadata_features,
    methodology_artifacts,
    permission_features,
    profile_filters,
    runtime_reporting,
)

__all__ = [
    "metadata_features",
    "methodology_artifacts",
    "permission_features",
    "profile_filters",
    "runtime_reporting",
]

_LEGACY_ORCH_PREFIX = "analysis.orchestration."
for _name in __all__:
    sys.modules[_LEGACY_ORCH_PREFIX + _name] = sys.modules[__name__ + "." + _name]
