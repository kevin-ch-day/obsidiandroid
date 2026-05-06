"""Interactive startup menu for pipeline execution modes.

Implementation lives in ``obsidiandroid.cli.startup_menu``; this module remains a
compatibility import path (including ``python -m utils.startup_menu``).
"""

from __future__ import annotations


from obsidiandroid.cli.startup_menu import *  # noqa: F403

if __name__ == "__main__":
    from obsidiandroid.cli.startup_menu import main

    raise SystemExit(main())
