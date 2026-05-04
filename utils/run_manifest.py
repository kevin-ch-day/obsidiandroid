"""Compatibility shim; implementation in :mod:`obsidiandroid.governance.run_manifest`.

Prefer ``from obsidiandroid.governance import run_manifest`` (submodule) or
``import obsidiandroid.governance.run_manifest`` in new code.
"""

import utils.repo_import_paths  # noqa: F401

from obsidiandroid.governance.run_manifest import *  # noqa: F401,F403
