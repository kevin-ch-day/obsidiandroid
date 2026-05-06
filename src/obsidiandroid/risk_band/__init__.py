"""Risk band assignment and AV engine tier scoring helpers.

Implementation is canonical here (**Pass 81**); ``analysis.risk_band`` is an identity shim to this
package and its submodules (same :class:`types.ModuleType` objects).
"""

from __future__ import annotations

import sys

from . import assign_risk_band, phase_score_engines

__all__ = ["assign_risk_band", "phase_score_engines"]

_LEGACY_RISK_BAND_PREFIX = "analysis.risk_band."
for _name in __all__:
    sys.modules[_LEGACY_RISK_BAND_PREFIX + _name] = sys.modules[__name__ + "." + _name]

