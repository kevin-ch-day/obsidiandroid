"""Configurable parameters and labels for categorical risk-band assignment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from obsidiandroid.cli.ui import display as du

DEFAULT_LABELS = ["Low", "Moderate", "Elevated", "Critical"]
EXTENDED_LABELS = ["None", "Low", "Moderate", "Elevated", "Critical", "Unclassified"]

ScoringMethod = Literal["quantile", "static", "auto"]


@dataclass
class RiskBandConfig:
    method: ScoringMethod = "auto"
    fallback_bin_count: int = 4
    min_bins_required: int = 4
    fallback_labels: list[str] = field(default_factory=lambda: DEFAULT_LABELS)
    include_unclassified: bool = True
    use_dynamic_bins: bool = True
    cut_precision: int = 2
    score_weights: dict = field(
        default_factory=lambda: {
            "malicious_pct": 0.5,
            "detection_density": 0.3,
            "engine_diversity": 0.2,
        }
    )

    def validate_labels(self):
        if len(self.fallback_labels) != self.fallback_bin_count:
            raise ValueError(
                f"[Config Error] Label count ({len(self.fallback_labels)}) must match bin count ({self.fallback_bin_count})."
            )
        if not all(isinstance(label, str) for label in self.fallback_labels):
            raise TypeError("[Config Error] All fallback labels must be strings.")

    def describe(self):
        du.print_key_values(
            {
                "Method": self.method,
                "Fallback Bin Count": self.fallback_bin_count,
                "Min Bins for Quantile": self.min_bins_required,
                "Fallback Labels": self.fallback_labels,
                "Dynamic Binning": self.use_dynamic_bins,
                "Allow Unclassified": self.include_unclassified,
                "Score Weights": self.score_weights,
                "Precision": self.cut_precision,
            },
            "[CONFIG] Risk Band Configuration",
        )
