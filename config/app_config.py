"""Central application configuration (compatibility aggregator).

This module preserves the long-standing import contract used across the codebase:

    from config import app_config

Settings are now organized under ``config/settings`` and re-exported here so
runtime mutation patterns (for example ``setattr(app_config, "...", value)``)
continue to work without changing call sites.
"""

from config.settings.app_identity import *  # noqa: F401,F403
from config.settings.cohort import *  # noqa: F401,F403
from config.settings.logging_flags import *  # noqa: F401,F403
from config.settings.methodology import *  # noqa: F401,F403
from config.settings.model_hyperparams import *  # noqa: F401,F403
from config.settings.model_summary import *  # noqa: F401,F403
from config.settings.output_flags import *  # noqa: F401,F403
from config.settings.parser_quality import *  # noqa: F401,F403
from config.settings.reproducibility import *  # noqa: F401,F403
from config.settings.tuning_cv import *  # noqa: F401,F403
from config.settings.vendor_engine import *  # noqa: F401,F403

