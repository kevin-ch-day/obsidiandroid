# Filename: models/risk_band_config.py
# Purpose : Configurable parameters and labels used to assign categorical risk bands to samples.

from dataclasses import dataclass, field
from typing import List, Literal
from obsidiandroid.cli.ui import display as du

# Default ordered labels for 4-bin severity
DEFAULT_LABELS = ["Low", "Moderate", "Elevated", "Critical"]
# Extended label set including non-detection or fallback states
EXTENDED_LABELS = ["None", "Low", "Moderate", "Elevated", "Critical", "Unclassified"]

# Allowed methods for risk band scoring
ScoringMethod = Literal["quantile", "static", "auto"]

@dataclass
class RiskBandConfig:
    # Risk band assignment strategy ('quantile', 'static', or 'auto')
    method: ScoringMethod = "auto"

    # Number of bins for fallback static cut
    fallback_bin_count: int = 4

    # Minimum unique values required for quantile binning to be applied
    min_bins_required: int = 4

    # Labels used when fallback static binning is performed
    fallback_labels: List[str] = field(default_factory=lambda: DEFAULT_LABELS)

    # Whether to assign 'Unclassified' label if banding fails
    include_unclassified: bool = True

    # For static cuts: whether to compute bin edges from data (True) or use fixed cutoffs (False)
    use_dynamic_bins: bool = True

    # Optional precision to round bin edges (only for display/diagnostics)
    cut_precision: int = 2

    # Optional scoring weights used for computing risk_score
    score_weights: dict = field(default_factory=lambda: {
        "malicious_pct": 0.5,
        "detection_density": 0.3,
        "engine_diversity": 0.2
    })

    def validate_labels(self):
        # Ensures fallback labels align with the number of bins
        if len(self.fallback_labels) != self.fallback_bin_count:
            raise ValueError(
                f"[Config Error] Label count ({len(self.fallback_labels)}) must match bin count ({self.fallback_bin_count})."
            )
        if not all(isinstance(label, str) for label in self.fallback_labels):
            raise TypeError("[Config Error] All fallback labels must be strings.")

    def describe(self):
        # Outputs configuration settings for debugging
        du.print_key_values({
            "Method": self.method,
            "Fallback Bin Count": self.fallback_bin_count,
            "Min Bins for Quantile": self.min_bins_required,
            "Fallback Labels": self.fallback_labels,
            "Dynamic Binning": self.use_dynamic_bins,
            "Allow Unclassified": self.include_unclassified,
            "Score Weights": self.score_weights,
            "Precision": self.cut_precision
        }, "[CONFIG] Risk Band Configuration")
