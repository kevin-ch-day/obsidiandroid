"""Transitional ``analysis`` subtree (implementations migrated to ``obsidiandroid.*``).

Subpackages are **thin shims** or lazy facades wired to canonical modules under
``src/obsidiandroid/``. Prefer ``obsidiandroid.pipeline``, ``obsidiandroid.diagnostics``,
``obsidiandroid.matrix``, ``obsidiandroid.orchestration``, ``obsidiandroid.risk_band``,
``obsidiandroid.feature_engineering``, ``obsidiandroid.evaluation``, and
``obsidiandroid.vendors`` for new code. See ``docs/STRUCTURE_MIGRATION_PLAN.md``.
"""

# Intentionally minimal: legacy imports use explicit subpaths (e.g. ``analysis.pipeline.runner``).
