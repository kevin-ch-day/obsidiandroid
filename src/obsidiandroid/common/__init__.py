"""Canonical shared primitives for paths, hashing, canonicalization, and output hygiene.

Key modules include :mod:`obsidiandroid.common.hash_utils`,
:mod:`obsidiandroid.common.canonicalization`, :mod:`obsidiandroid.common.path_safety`,
:mod:`obsidiandroid.common.runtime_paths`, :mod:`obsidiandroid.common.ml_console`,
:mod:`obsidiandroid.common.display_distribution`, :mod:`obsidiandroid.common.export_naming`,
:mod:`obsidiandroid.common.export_vendor_raw`, :mod:`obsidiandroid.common.export_workbook`,
:mod:`obsidiandroid.common.output_cleanup_clutter`, :mod:`obsidiandroid.common.av_detection_tiers`,
:mod:`obsidiandroid.common.sample_metadata_preprocessor`,
:mod:`obsidiandroid.common.output_paths`, :mod:`obsidiandroid.common.output_hygiene`,
:mod:`obsidiandroid.common.json_io`,
and :mod:`obsidiandroid.common.repo_paths`.

Import these modules directly from ``obsidiandroid.common`` in new code.
"""

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

__all__ = ["ensure_repo_src_on_sys_path"]
