"""ML feature vectorization (canonical).

**Pass 83:** Implementation lives here; ``ml_classification/vectorization/*.py`` are thin
identity shims. Register legacy import paths on ``sys.modules`` so
``ml_classification.vectorization.<submodule>`` resolves to the same
:class:`types.ModuleType` objects as ``obsidiandroid.features.vectorization.<submodule>``.
"""

from __future__ import annotations

import sys

from . import feature_encoder  # noqa: F401
from . import feature_engine_selection  # noqa: F401
from . import feature_vendor_extractor  # noqa: F401
from . import feature_vector_builder  # noqa: F401

_LEGACY_V_PREFIX = "ml_classification.vectorization."
for _name in (
    "feature_encoder",
    "feature_engine_selection",
    "feature_vendor_extractor",
    "feature_vector_builder",
):
    sys.modules[_LEGACY_V_PREFIX + _name] = sys.modules[__name__ + "." + _name]

__all__ = [
    "feature_encoder",
    "feature_engine_selection",
    "feature_vendor_extractor",
    "feature_vector_builder",
]

del _LEGACY_V_PREFIX, _name
