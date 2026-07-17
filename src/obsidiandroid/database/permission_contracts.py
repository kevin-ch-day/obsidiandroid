"""Shared Permission Intel schema-contract helpers."""

from __future__ import annotations

from . import db_engine


_PERMISSION_OBS_NORM_AVAILABLE: bool | None = None
_PERMISSION_DICTIONARY_NORM_AVAILABLE: bool | None = None


def reset_permission_obs_norm_cache() -> None:
    """Reset cached `permission_string_norm` availability for tests or schema refresh."""
    global _PERMISSION_OBS_NORM_AVAILABLE, _PERMISSION_DICTIONARY_NORM_AVAILABLE  # pylint: disable=global-statement
    _PERMISSION_OBS_NORM_AVAILABLE = None
    _PERMISSION_DICTIONARY_NORM_AVAILABLE = None


def permission_obs_norm_available() -> bool:
    """Return whether `android_permission_obs_sample` exposes `permission_string_norm`."""
    global _PERMISSION_OBS_NORM_AVAILABLE  # pylint: disable=global-statement
    if _PERMISSION_OBS_NORM_AVAILABLE is None:
        columns = {
            str(col).strip().lower()
            for col in db_engine.get_table_columns("android_permission_obs_sample")
        }
        _PERMISSION_OBS_NORM_AVAILABLE = "permission_string_norm" in columns
    return bool(_PERMISSION_OBS_NORM_AVAILABLE)


def permission_obs_key_expr(*, alias: str | None = None) -> str:
    """Return the canonical SQL expression for permission observation grouping keys."""
    base = "permission_string"
    norm = "permission_string_norm"
    if alias:
        base = f"{alias}.{base}"
        norm = f"{alias}.{norm}"
    if permission_obs_norm_available():
        return f"COALESCE(NULLIF(TRIM({norm}), ''), LOWER(TRIM({base})))"
    return f"LOWER(TRIM({base}))"


def permission_dictionary_norm_available() -> bool:
    """Return whether both permission dictionaries expose indexed normalized keys."""
    global _PERMISSION_DICTIONARY_NORM_AVAILABLE  # pylint: disable=global-statement
    if _PERMISSION_DICTIONARY_NORM_AVAILABLE is None:
        aosp_columns = {
            str(column).strip().lower()
            for column in db_engine.get_table_columns("android_permission_dict_aosp")
        }
        oem_columns = {
            str(column).strip().lower()
            for column in db_engine.get_table_columns("android_permission_dict_oem")
        }
        _PERMISSION_DICTIONARY_NORM_AVAILABLE = (
            "constant_value_norm" in aosp_columns
            and "permission_string_norm" in oem_columns
        )
    return bool(_PERMISSION_DICTIONARY_NORM_AVAILABLE)
