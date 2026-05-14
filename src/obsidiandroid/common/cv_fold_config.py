# Filename: src/obsidiandroid/common/cv_fold_config.py
# Purpose : Shared stratified CV fold-count coercion (no heavy modeling imports).

"""CV fold configuration helpers used by training, grid search, and manifests."""


def coerce_stratified_cv_folds_config(raw: object, *, default: int = 5) -> int:
    """Return a stratified-CV fold count from config, floored at 2.

    ``StratifiedKFold`` requires ``n_splits >= 2``. Invalid or missing values
    (``None``, non-numeric strings, etc.) fall back to ``default`` before the
    floor is applied so callers never pass ``int(None)`` or ``n_splits=1``.
    """
    if raw is None:
        n = default
    else:
        try:
            n = int(raw)
        except (TypeError, ValueError):
            n = default
    return max(2, n)
