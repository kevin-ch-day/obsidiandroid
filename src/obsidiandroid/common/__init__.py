"""Shared primitives (paths, hashing, canonicalization; incremental migration).

Canonical modules include :mod:`obsidiandroid.common.hash_utils`,
:mod:`obsidiandroid.common.canonicalization`, :mod:`obsidiandroid.common.path_safety`,
:mod:`obsidiandroid.common.runtime_paths`, :mod:`obsidiandroid.common.ml_console`,
:mod:`obsidiandroid.common.display_distribution`, and :mod:`obsidiandroid.common.repo_paths`.
Legacy ``utils/*`` shims re-export the same objects.
"""

from obsidiandroid.common.repo_paths import ensure_repo_src_on_sys_path

__all__ = ["ensure_repo_src_on_sys_path"]
