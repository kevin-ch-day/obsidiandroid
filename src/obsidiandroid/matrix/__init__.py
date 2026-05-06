"""Binary AV matrix construction and malicious-score enrichment.

Implementation is canonical here (**Pass 80**); ``analysis.matrix`` is an identity shim to this
package and its submodules (same :class:`types.ModuleType` objects).
"""

from __future__ import annotations

import sys

from . import av_binary_matrix_builder, enrich_malicious_scores, enrich_score_features

__all__ = ["av_binary_matrix_builder", "enrich_malicious_scores", "enrich_score_features"]

_LEGACY_MATRIX_PREFIX = "analysis.matrix."
for _name in __all__:
    sys.modules[_LEGACY_MATRIX_PREFIX + _name] = sys.modules[__name__ + "." + _name]
