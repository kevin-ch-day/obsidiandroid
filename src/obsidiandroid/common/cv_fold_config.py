# Filename: src/obsidiandroid/common/cv_fold_config.py
# Purpose : CV fold coercion and safe int parsing for config (no heavy modeling imports).

"""CV fold configuration helpers used by training, grid search, and manifests."""


def safe_int_config_value(raw: object, *, default: int) -> int:
    """Coerce a config value to ``int``; ``None`` and invalid values use ``default``.

    Avoids ``int(getattr(...))`` when the attribute exists but is explicitly ``None``.
    """
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def coerce_stratified_cv_folds_config(raw: object, *, default: int = 5) -> int:
    """Return a stratified-CV fold count from config, floored at 2.

    ``StratifiedKFold`` requires ``n_splits >= 2``. Invalid or missing values
    (``None``, non-numeric strings, etc.) fall back to ``default`` before the
    floor is applied so callers never pass ``int(None)`` or ``n_splits=1``.
    """
    return max(2, safe_int_config_value(raw, default=default))
