"""Pipeline artifact path/registry helpers.

Implementation is canonical under ``obsidiandroid.pipeline.artifacts`` (**Pass 76**);
``analysis.pipeline.artifacts`` is an identity shim to this package and its submodules.
"""

from __future__ import annotations

import sys

from . import paths, registry
from .paths import ArtifactPaths
from .registry import ArtifactRecord, ArtifactRegistry

_LEGACY_ARTIFACTS_PREFIX = "analysis.pipeline.artifacts."
for _name in ("paths", "registry"):
    sys.modules[_LEGACY_ARTIFACTS_PREFIX + _name] = sys.modules[__name__ + "." + _name]

__all__ = [
    "ArtifactPaths",
    "ArtifactRecord",
    "ArtifactRegistry",
    "paths",
    "registry",
]
