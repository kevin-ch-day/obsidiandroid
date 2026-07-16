"""Tests for prepared-cohort family feed-risk diagnostics."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from obsidiandroid.diagnostics import cohort_family_feed_risk


def test_build_family_feed_risk_payload_ranks_conflict_and_concentration() -> None:
    df = pd.DataFrame(
        [
            {
                "family_canonical": "Octo",
                "family_label_raw": "coper",
                "type_slug": "banker",
                "sample_label_kind": "family_or_common_name",
                "vt_family_token": "octo",
            },
            {
                "family_canonical": "Octo",
                "family_label_raw": "octo",
                "type_slug": "banker",
                "sample_label_kind": "family_or_common_name",
                "vt_family_token": "octo",
            },
            {
                "family_canonical": "SpyNote",
                "family_label_raw": "spynote",
                "type_slug": "rat",
                "sample_label_kind": "opaque_string",
                "vt_family_token": "",
            },
            {
                "family_canonical": "Irata",
                "family_label_raw": "irata",
                "type_slug": "banker",
                "sample_label_kind": "family_or_common_name",
                "vt_family_token": "irata",
            },
            {
                "family_canonical": "Irata",
                "family_label_raw": "irata",
                "type_slug": "banker",
                "sample_label_kind": "family_or_common_name",
                "vt_family_token": "irata",
            },
            {
                "family_canonical": "Irata",
                "family_label_raw": "irata",
                "type_slug": "banker",
                "sample_label_kind": "family_or_common_name",
                "vt_family_token": "irata",
            },
        ]
    )

    payload = cohort_family_feed_risk.build_family_feed_risk_payload(df, top_n=10)

    assert payload["total_rows"] == 6
    assert payload["family_count"] == 3
    ranked = payload["ranked_families"]
    assert ranked[0]["family_canonical"] == "Octo"
    assert ranked[0]["family_conflict_rows"] == 1
    assert any(row["family_canonical"] == "SpyNote" and row["opaque_label_rows"] == 1 for row in ranked)
    assert any(row["family_canonical"] == "Irata" and row["sample_share_pct"] == 50.0 for row in ranked)


def test_export_family_feed_risk_reports_writes_expected_files(tmp_path: Path) -> None:
    df = pd.DataFrame(
        [
            {
                "family_canonical": "SpyNote",
                "family_label_raw": "spynote",
                "type_slug": "rat",
                "sample_label_kind": "opaque_string",
                "vt_family_token": "",
            }
        ]
    )

    out = cohort_family_feed_risk.export_family_feed_risk_reports(
        diagnostics_dir=tmp_path,
        run_id="r1",
        samples_df=df,
    )

    assert len(out) == 3
    for path in out:
        assert Path(path).exists()


def test_feed_risk_normalizes_known_aliases_and_textual_nulls() -> None:
    df = pd.DataFrame(
        [
            {
                "family_canonical": "RoamingMantis",
                "family_label_raw": "Wroba",
                "type_slug": "banker",
                "sample_label_kind": "family_or_common_name",
                "vt_family_token": "wroba",
            },
            {
                "family_canonical": "nan",
                "family_label_raw": "n/a",
                "type_slug": "banker",
                "sample_label_kind": "family_or_common_name",
                "vt_family_token": "possiblefamily",
            },
        ]
    )

    payload = cohort_family_feed_risk.build_family_feed_risk_payload(df, top_n=10)

    assert payload["family_count"] == 1
    roaming = next(row for row in payload["ranked_families"] if row["family_canonical"] == "RoamingMantis")
    assert roaming["family_conflict_rows"] == 0
    blank = next(row for row in payload["ranked_families"] if row["family_canonical"] == "<blank>")
    assert blank["blank_family_with_token_rows"] == 1
