"""Tests for evidence-mode perturbation-axis guard."""

from __future__ import annotations

import pytest

from obsidiandroid.pipeline import runtime_policy

enforce_paper_perturbation_axes = runtime_policy.enforce_paper_perturbation_axes


def test_enforce_paper_perturbation_axes_rejects_invalid_axis() -> None:
    """Evidence mode should fail when profile declares non-approved perturbation axis."""
    profile = {
        "profile_id": "repro_bad",
        "evidence_perturbation_axes": ["min_malicious_detections", "random_undersampling"],
    }
    with pytest.raises(ValueError, match="Invalid perturbation axis"):
        enforce_paper_perturbation_axes(profile=profile, paper_mode=True)


def test_enforce_paper_perturbation_axes_accepts_locked_axes() -> None:
    """Evidence mode should accept approved perturbation axes."""
    profile = {
        "profile_id": "paper2_primary",
        "evidence_perturbation_axes": [
            "min_malicious_detections",
            "family_cap",
            "exclude_unknown_type_slug",
        ],
    }
    enforce_paper_perturbation_axes(profile=profile, paper_mode=True)
