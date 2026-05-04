"""Compatibility shim; implementation in :mod:`obsidiandroid.common.output_paths`.

Prefer ``from obsidiandroid.common import output_paths`` in new code.
"""

import utils.repo_import_paths  # noqa: F401

from obsidiandroid.common.output_paths import *  # noqa: F401,F403
