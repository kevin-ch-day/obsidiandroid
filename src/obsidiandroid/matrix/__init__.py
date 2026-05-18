"""Binary AV matrix construction and malicious-score enrichment.

Implementation is canonical here (**Pass 80**); ``analysis.matrix`` is an identity shim to this
package and its submodules (same :class:`types.ModuleType` objects).
"""

from __future__ import annotations

from . import av_binary_matrix_builder, enrich_malicious_scores, enrich_score_features

__all__ = ["av_binary_matrix_builder", "enrich_malicious_scores", "enrich_score_features"]
