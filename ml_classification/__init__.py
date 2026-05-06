"""Transitional ML subtree (implementations migrated to ``obsidiandroid.*``).

Subpackages here are overwhelmingly **thin shims** or facades wired to canonical
modules. Prefer ``obsidiandroid.modeling``, ``obsidiandroid.features``,
``obsidiandroid.labeling``, ``obsidiandroid.evaluation``, ``obsidiandroid.inference``,
``obsidiandroid.classification_builder``, and ``obsidiandroid.engine_weights`` for
new code. See ``docs/STRUCTURE_MIGRATION_PLAN.md``.
"""

# Intentionally empty: lazy loading via submodule shims and package __getattr__.
