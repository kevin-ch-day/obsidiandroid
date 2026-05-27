from __future__ import annotations

import pandas as pd

from obsidiandroid.diagnostics import taxonomy_target_surface_report


def test_build_taxonomy_target_surface_summary_reports_authoritative_and_raw_surfaces() -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "family_id": [10, 10, 11, 12],
            "family_canonical": ["Gigabud", "Gigabud", "SpyNote", "DoNot"],
            "type_slug": ["banker", "banker", "rat", "spyware"],
            "category_primary": ["trojan", "trojan", "rat", "trojan"],
            "category_subtype": ["banker", "banker", "rat", "spyware"],
        }
    )

    summary = taxonomy_target_surface_report.build_taxonomy_target_surface_summary(
        df,
        min_support=2,
    )

    targets = {
        row["surface_name"]: row
        for row in summary["targets"]
    }
    assert targets["family_id"]["unique_classes"] == 3
    assert targets["family_id"]["trainable_classes_at_min_support"] == 1
    assert targets["family_id"]["recommended_use"] == "preferred_supervised_target"
    assert targets["type_slug"]["unique_classes"] == 3
    assert targets["type_slug"]["recommended_use"] == "preferred_coarse_target"
    assert targets["family_within_type"]["unique_classes"] == 3
    assert targets["category_primary"]["recommended_use"] == "avoid_primary_claim_target"
    assert targets["category_primary"]["unique_classes"] == 2
    assert targets["category_subtype"]["unique_classes"] == 3
    assert summary["alignment"]["subtype_exact_type_match_pct"] == 100.0
    assert summary["alignment"]["inferred_type_match_pct"] == 100.0
    assert summary["label_strategy"]["preferred_family_target"] == "family_id"
    assert summary["label_strategy"]["preferred_type_target"] == "type_slug"
    assert summary["label_strategy"]["avoid_for_primary_claims"] == ["category_primary"]
    assert "subtype aligns materially better than raw primary" in summary["label_strategy"]["alignment_interpretation"].lower()


def test_export_taxonomy_target_surface_reports_writes_all_formats(tmp_path) -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "family_id": [1, 2],
            "family_canonical": ["A", "B"],
            "type_slug": ["banker", "rat"],
            "category_primary": ["trojan", "rat"],
            "category_subtype": ["banker", "rat"],
        }
    )
    paths = taxonomy_target_surface_report.export_taxonomy_target_surface_reports(
        diagnostics_dir=tmp_path,
        run_id="runx",
        samples_df=df,
        min_support=2,
    )
    assert len(paths) == 3
    for path in paths:
        assert path
        assert tmp_path.joinpath(path.split("/")[-1]).is_file()
    md_text = (tmp_path / "taxonomy_target_surfaces_runx.md").read_text(encoding="utf-8")
    assert "Recommended label strategy" in md_text
    assert "preferred family supervision target" in md_text
