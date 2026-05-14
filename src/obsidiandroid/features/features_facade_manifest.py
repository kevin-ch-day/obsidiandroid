# Filename: src/obsidiandroid/features/features_facade_manifest.py
"""``obsidiandroid.features`` façade alias targets (name → canonical implementation module).

Used by :mod:`obsidiandroid.features` and :mod:`scripts.dev.check_import_surface`.
"""

from __future__ import annotations

FEATURES_FACADE_ALIAS_TARGETS: tuple[tuple[str, str], ...] = (
    ("feature_encoder", "obsidiandroid.features.vectorization.feature_encoder"),
    ("feature_engine_selection", "obsidiandroid.features.vectorization.feature_engine_selection"),
    ("feature_schema_audit", "obsidiandroid.features.feature_schema_audit"),
    ("feature_vector_builder", "obsidiandroid.features.vectorization.feature_vector_builder"),
    ("feature_vendor_extractor", "obsidiandroid.features.vectorization.feature_vendor_extractor"),
)

__all__ = ("FEATURES_FACADE_ALIAS_TARGETS",)
