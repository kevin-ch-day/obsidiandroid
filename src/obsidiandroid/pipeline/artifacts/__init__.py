"""Pipeline artifact path/registry helpers.

Implementation is canonical under ``obsidiandroid.pipeline.artifacts`` (**Pass 76**);
``analysis.pipeline.artifacts`` is an identity shim to this package and its submodules.
"""

from __future__ import annotations

from . import paths, registry
from .paths import ArtifactPaths
from .registry import ArtifactRecord, ArtifactRegistry

__all__ = [
    "ArtifactPaths",
    "ArtifactRecord",
    "ArtifactRegistry",
    "paths",
    "registry",
]
