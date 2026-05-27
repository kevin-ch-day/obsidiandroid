from __future__ import annotations

import pandas as pd

from obsidiandroid.diagnostics import family_label_confidence_audit


def test_build_family_label_confidence_payload_ranks_conflicts_and_type_mismatches() -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "family_canonical": ["Gigabud", "Gigabud", "SpyNote", "DoNot"],
            "family_label_raw": ["Gigabud", "WrongFam", "SpyNote", ""],
            "type_slug": ["banker", "banker", "rat", "spyware"],
            "category_primary": ["trojan", "trojan", "rat", "trojan"],
            "category_subtype": ["banker", "spyware", "rat", ""],
            "sample_label_kind": [
                "family_or_common_name",
                "family_or_common_name",
                "opaque_string",
                "family_or_common_name",
            ],
            "vt_family_token": ["gigabud", "gigabud", "", "donot"],
        }
    )

    payload = family_label_confidence_audit.build_family_label_confidence_payload(
        df,
        min_support=2,
    )

    assert payload["row_count"] == 4
    assert payload["family_count"] == 3
    assert payload["sample_rows"]
    worst = payload["sample_rows"][0]
    assert worst["sample_id"] == 2
    assert "family_conflict" in worst["reasons"]
    assert "raw_type_mismatch" in worst["reasons"]

    families = {row["family_canonical"]: row for row in payload["family_rows"]}
    assert families["gigabud"]["family_conflict_rows"] == 1
    assert families["gigabud"]["type_mismatch_rows"] == 1
    assert families["spynote"]["weak_label_rows"] == 1


def test_export_family_label_confidence_reports_writes_expected_files(tmp_path) -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "family_canonical": ["A", "B"],
            "family_label_raw": ["A", "B"],
            "type_slug": ["banker", "rat"],
            "category_primary": ["trojan", "rat"],
            "category_subtype": ["banker", "rat"],
            "sample_label_kind": ["family_or_common_name", "family_or_common_name"],
            "vt_family_token": ["a", "b"],
        }
    )
    paths = family_label_confidence_audit.export_family_label_confidence_reports(
        diagnostics_dir=tmp_path,
        run_id="runx",
        samples_df=df,
        min_support=2,
    )
    assert len(paths) == 4
    for path in paths:
        assert tmp_path.joinpath(path.split("/")[-1]).is_file()
