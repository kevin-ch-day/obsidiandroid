"""Tests for the shared raw/canonical family identity contract."""

from __future__ import annotations

import pandas as pd

from obsidiandroid.common.family_label_semantics import (
    family_identity_sql,
    family_label_conflict_mask,
    is_family_label_conflict,
    normalize_family_identity_token,
)


def test_known_aliases_do_not_create_family_label_conflicts() -> None:
    """Parser aliases must compare equal to their governed canonical target."""
    frame = pd.DataFrame(
        {
            "family_label_raw": ["Wroba", "BlackLoan", "Black Rock", "Gold Digger"],
            "family_canonical": ["RoamingMantis", "SpyLoan", "BlackRock", "GoldDigger"],
        }
    )

    assert family_label_conflict_mask(frame).tolist() == [False, False, False, False]


def test_substantive_difference_and_placeholders_are_distinguished() -> None:
    """Only real family drift is a conflict; missing/ID-shaped labels are not."""
    assert is_family_label_conflict("SpyC23", "HiddenAd")
    assert not is_family_label_conflict("family_id=12", "HiddenAd")
    assert not is_family_label_conflict("n/a", "HiddenAd")
    assert normalize_family_identity_token("family_id=12") == ""


def test_sql_identity_matches_separator_normalization_and_alias_contract() -> None:
    """The generated SQL handles parser separators without REGEXP_REPLACE."""
    expression = family_identity_sql("y.family_label")

    assert "REPLACE(REPLACE(REPLACE(REPLACE(" in expression
    assert "WHEN 'black_rock' THEN 'blackrock'" in expression
    assert "WHEN 'gold_digger' THEN 'golddigger'" in expression
    assert "WHEN 'wroba' THEN 'roamingmantis'" in expression
