"""Legacy entry for ``python -m database.split_db_health`` (module identity + CLI).

``python -m`` sets ``__name__`` to ``__main__``, so this file does not use
``sys.modules[__name__]`` indirection (unlike leaf shims that only support imports).
"""

from __future__ import annotations

import importlib
import sys

_canon = importlib.import_module("obsidiandroid.database.split_db_health")
sys.modules["database.split_db_health"] = _canon

if __name__ == "__main__":
    raise SystemExit(_canon.split_database_health_cli())
