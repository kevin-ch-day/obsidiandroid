"""Tests for governed paper-facing family display policy metadata."""

from __future__ import annotations

from obsidiandroid.governance import paper_family_display_policy


def test_paper_family_display_policy_payload_loads_governed_artifact() -> None:
    """Paper-facing family display policy should be artifact-backed and hashed."""
    payload = paper_family_display_policy.paper_family_display_policy_payload()
    assert payload["policy_id"] == "android_paper_family_display_policy"
    assert payload["version"] == "20260601-v1"
    assert payload["handle"] == "android_paper_family_display_policy.family_confusion_matrix"
    assert payload["artifact_path"] == "config/taxonomy/paper_family_display_policy.yaml"
    matrix = payload["family_confusion_matrix"]
    assert matrix["top_k_major_families"] == 12
    assert matrix["require_full_artifact_matrix"] is True
    assert matrix["minor_long_tail_label"] == "Minor/Long-tail"
    assert len(str(payload["hash"])) == 64
