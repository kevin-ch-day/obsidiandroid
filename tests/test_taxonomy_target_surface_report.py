from __future__ import annotations

import pandas as pd
import pytest

from obsidiandroid.diagnostics import taxonomy_target_surface_report

pytestmark = pytest.mark.contract


def test_build_taxonomy_target_surface_summary_reports_authoritative_and_raw_surfaces() -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "family_id": [10, 10, 11, 12],
            "family_canonical": ["Gigabud", "Gigabud", "SpyNote", "DoNot"],
            "type_slug": ["banker", "banker", "rat", "spyware"],
            "category_primary": ["trojan", "trojan", "rat", "trojan"],
            "category_subtype": ["banker", "banker", "rat", "spyware"],
            "sample_label_kind": ["family_or_common_name"] * 4,
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
    assert summary["label_strategy"]["major_family_target_scope"] == "curated_major_family_authority"
    assert summary["tier_counts"]["mapped_family_samples"] == 4
    assert summary["tier_counts"]["major_family_samples"] == 2
    assert summary["tier_counts"]["minor_family_samples"] == 2
    assert summary["tier_counts"]["generic_coarse_label_samples"] == 0
    assert summary["tier_counts"]["family_target_eligible_samples"] == 4
    assert summary["major_family_authority"]["family_count"] == 39
    assert summary["major_family_coverage"]["present_major_family_count"] == 2
    assert summary["major_family_coverage"]["missing_major_family_count"] == 37
    assert "spynote" in summary["major_family_coverage"]["present_major_families"]
    assert "donot" in summary["major_family_coverage"]["present_major_families"]
    assert summary["support_diagnostics"][0]["support_floor"] == 20
    assert "subtype aligns materially better than raw primary" in summary["label_strategy"]["alignment_interpretation"].lower()


def test_build_taxonomy_target_surface_summary_keeps_clean_type_only_rows_unresolved() -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "family_id": [None, None, None],
            "family_canonical": ["", "", ""],
            "type_slug": ["banker", "rat", "spyware"],
            "category_primary": ["", "", ""],
            "category_subtype": ["", "", ""],
            "sample_label_kind": ["family_or_common_name", "family_or_common_name", "family_or_common_name"],
        }
    )

    summary = taxonomy_target_surface_report.build_taxonomy_target_surface_summary(
        df,
        min_support=1,
    )

    assert summary["tier_counts"]["mapped_family_samples"] == 0
    assert summary["tier_counts"]["generic_coarse_label_samples"] == 0
    assert summary["tier_counts"]["unresolved_samples"] == 3
    assert summary["tier_counts"]["type_target_eligible_samples"] == 3
    assert summary["tier_counts"]["family_target_eligible_samples"] == 0


def test_numeric_or_id_shaped_family_display_tokens_are_not_supervised_targets() -> None:
    """Readable canonical family names are required in addition to numeric IDs."""
    df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3],
            "family_id": [30, 31, 32],
            "family_canonical": ["30", "family_id=31", "unresolved family id 32"],
            "type_slug": ["banker", "banker", "rat"],
            "category_primary": ["", "", ""],
            "category_subtype": ["", "", ""],
            "sample_label_kind": ["family_or_common_name"] * 3,
        }
    )

    summary = taxonomy_target_surface_report.build_taxonomy_target_surface_summary(
        df,
        min_support=1,
    )

    assert summary["tier_counts"]["mapped_family_samples"] == 0
    assert summary["tier_counts"]["unresolved_samples"] == 3
    assert summary["tier_counts"]["family_target_eligible_samples"] == 0


def test_type_target_eligibility_excludes_retired_and_unknown_type_tokens() -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4],
            "family_id": [None, None, None, None],
            "family_canonical": ["", "", "", ""],
            "type_slug": ["banker", "worm", "pua", "unknown"],
            "category_primary": ["", "", "", ""],
            "category_subtype": ["", "", "", ""],
            "sample_label_kind": ["family_or_common_name"] * 4,
        }
    )

    summary = taxonomy_target_surface_report.build_taxonomy_target_surface_summary(df, min_support=1)

    assert summary["tier_counts"]["type_target_eligible_samples"] == 1


def test_build_family_tier_audit_rows_reports_major_minor_and_unresolved_reasons() -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4, 5],
            "family_id": [10, 10, 11, None, None],
            "family_canonical": ["DoNot", "DoNot", "Gigabud", "", ""],
            "type_slug": ["spyware", "spyware", "banker", "rat", "banker"],
            "category_primary": ["trojan", "trojan", "trojan", "", ""],
            "category_subtype": ["spyware", "spyware", "banker", "trojan", ""],
            "sample_label_kind": [
                "family_or_common_name",
                "family_or_common_name",
                "family_or_common_name",
                "family_or_common_name",
                "family_or_common_name",
            ],
            "source_batch_label": ["A", "A", "B", "C", "C"],
        }
    )
    df.attrs["support_floor_mode"] = "benchmark_eligibility"
    df.attrs["configured_min_samples_per_family"] = 3
    df.attrs["diagnostic_min_samples_per_family"] = 3

    rows = taxonomy_target_surface_report.build_family_tier_audit_rows(df)
    by_key = {(row["authority_tier"], row["family_slug"]): row for row in rows}

    assert ("major", "donot") in by_key
    assert by_key[("major", "donot")]["tier_reason"] == "listed_in_major_family_authority"
    assert by_key[("major", "donot")]["sample_count"] == 2
    assert by_key[("major", "donot")]["benchmark_eligible"] is False
    assert by_key[("major", "donot")]["benchmark_exclusion_reason"] == "support_below_3"
    assert ("minor", "gigabud") in by_key
    assert by_key[("minor", "gigabud")]["tier_reason"] == "mapped_family_not_in_major_authority"
    assert by_key[("minor", "gigabud")]["benchmark_eligible"] is False
    assert ("generic_or_coarse", "trojan") in by_key
    assert by_key[("generic_or_coarse", "trojan")]["tier_reason"] == "generic_or_type_like_subtype"
    assert by_key[("generic_or_coarse", "trojan")]["benchmark_exclusion_reason"] == "non_family_target"
    assert ("unresolved", "banker") in by_key
    assert by_key[("unresolved", "banker")]["tier_reason"] == "no_safe_family_mapping"
    assert by_key[("unresolved", "banker")]["type_target_eligible"] is True
    assert by_key[("unresolved", "banker")]["family_target_eligible"] is False


def test_build_taxonomy_target_surface_summary_reports_benchmark_eligibility_split() -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4, 5, 6],
            "family_id": [10, 10, 10, 11, None, None],
            "family_canonical": ["DoNot", "DoNot", "DoNot", "Gigabud", "", ""],
            "type_slug": ["spyware", "spyware", "spyware", "banker", "banker", "rat"],
            "category_primary": ["trojan", "trojan", "trojan", "trojan", "", ""],
            "category_subtype": ["spyware", "spyware", "spyware", "banker", "trojan", ""],
            "sample_label_kind": ["family_or_common_name"] * 6,
        }
    )
    df.attrs["support_floor_mode"] = "benchmark_eligibility"
    df.attrs["configured_min_samples_per_family"] = 3
    df.attrs["diagnostic_min_samples_per_family"] = 3

    summary = taxonomy_target_surface_report.build_taxonomy_target_surface_summary(df, min_support=3)

    assert summary["tier_counts"]["authority_eligible_samples"] == 4
    assert summary["tier_counts"]["benchmark_eligible_samples"] == 3
    assert summary["tier_counts"]["excluded_below_benchmark_support_samples"] == 1
    assert summary["tier_counts"]["excluded_non_family_target_samples"] == 2
    assert summary["benchmark_support_policy"]["benchmark_min_support"] == 3
    assert summary["benchmark_support_policy"]["benchmark_eligible_family_count"] == 1
    assert summary["benchmark_support_policy"]["excluded_below_support_family_count"] == 1


def test_export_taxonomy_target_surface_reports_writes_all_formats(tmp_path) -> None:
    df = pd.DataFrame(
        {
            "sample_id": [1, 2],
            "family_id": [1, 2],
            "family_canonical": ["A", "B"],
            "type_slug": ["banker", "rat"],
            "category_primary": ["trojan", "rat"],
            "category_subtype": ["banker", "rat"],
            "sample_label_kind": ["family_or_common_name", "family_or_common_name"],
        }
    )
    paths = taxonomy_target_surface_report.export_taxonomy_target_surface_reports(
        diagnostics_dir=tmp_path,
        run_id="runx",
        samples_df=df,
        min_support=2,
    )
    assert len(paths) == 6
    for path in paths:
        assert path
        assert tmp_path.joinpath(path.split("/")[-1]).is_file()
    md_text = (tmp_path / "taxonomy_target_surfaces_runx.md").read_text(encoding="utf-8")
    assert "Recommended label strategy" in md_text
    assert "preferred family supervision target" in md_text
    assert "Family Tiers" in md_text
    assert "major-family authority version" in md_text
    tier_md_text = (tmp_path / "family_tier_audit_runx.md").read_text(encoding="utf-8")
    assert "Family Tier Audit" in tier_md_text
    assert "benchmark eligible" in tier_md_text.lower()
    assert "listed_in_major_family_authority" in tier_md_text or "mapped_family_not_in_major_authority" in tier_md_text
