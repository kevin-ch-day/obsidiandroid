"""Shared helpers: paths, manifests, profiles, logging, exports, and CLI glue.

Import concrete modules explicitly (e.g. ``from utils import runtime_paths``) to keep
startup cost predictable; this package does not re-export everything by default.

Bootstrap: the first import of any ``utils.*`` submodule runs :mod:`utils.repo_import_paths`
once (prepend ``src/`` for checkout installs and call
:func:`obsidiandroid.common.repo_paths.ensure_repo_src_on_sys_path`). Leaf shims do not
"""

from __future__ import annotations

