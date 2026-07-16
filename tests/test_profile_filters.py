"""Regression coverage for taxonomy-aware profile filtering."""

from __future__ import annotations

import pandas as pd

from obsidiandroid.orchestration.profile_filters import malicious_signal_or_taxonomy_mask


def test_textual_null_taxonomy_tokens_do_not_rescue_missing_consensus_rows() -> None:
    """CSV-style null strings are absence of evidence, not malicious taxonomy."""
    frame = pd.DataFrame(
        {
            "family_canonical": ["nan", "n/a", "NamedFamily"],
            "type_slug": ["n/a", "null", "banker"],
            "category_primary": ["", "", ""],
            "category_subtype": ["", "", ""],
            "vt_suggested_label": ["", "", ""],
        }
    )

    assert malicious_signal_or_taxonomy_mask(frame).tolist() == [False, False, True]
