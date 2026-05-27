"""Unit tests for family label taxonomy audit (no DB)."""

from pathlib import Path

import pandas as pd

from obsidiandroid.diagnostics import family_label_taxonomy_audit as fla


def test_support_threshold_preview_counts() -> None:
    df = pd.DataFrame(
        {
            "family_id": [1, 1, 1, 2, 2, 2, 3, 3, 3],
            "family_canonical": ["A"] * 3 + ["B"] * 3 + ["C"] * 3,
            "type_slug": ["banker"] * 9,
        }
    )
    fam, th, summary = fla.build_family_taxonomy_audit_frames(df, training_min_support=20)
    assert summary["governed_samples"] == 9
    assert summary["governed_distinct_families"] == 3
    row20 = th[th["min_support_threshold"] == 20].iloc[0]
    assert int(row20["retained_families"]) == 0
    assert int(row20["retained_samples"]) == 0
    row3 = th[th["min_support_threshold"] == 3].iloc[0]
    assert int(row3["retained_families"]) == 3


def test_classify_label_quality() -> None:
    assert fla.classify_label_quality("Irata", sample_count=50, is_alias_duplicate=False) == "canonical_named_family"
    assert fla.classify_label_quality("trojan/android.generic.foo", sample_count=50, is_alias_duplicate=False) == "generic_av_label"
    assert fla.classify_label_quality("", sample_count=5, is_alias_duplicate=False) == "unknown_or_unresolved"
    assert fla.classify_label_quality("Irata", sample_count=50, is_alias_duplicate=True) == "alias_candidate"


def test_write_artifacts(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "family_id": [1, 1, 2, 2],
            "family_canonical": ["Irata", "Irata", "y", "y"],
            "type_slug": ["banker", "banker", "adware", "adware"],
        }
    )
    lines: list[str] = []

    fla.write_family_label_taxonomy_audit(
        df,
        diagnostics_dir=tmp_path,
        profile_id="test_profile",
        training_min_support=2,
        run_id="test_run",
        print_fn=lambda s: lines.append(s),
    )
    assert (tmp_path / "family_label_taxonomy_audit.csv").is_file()
    assert (tmp_path / "support_threshold_preview.csv").is_file()
    assert any("FAMILY LABEL SPACE AUDIT" in x for x in lines)


def test_write_artifacts_supports_prefixed_outputs(tmp_path: Path) -> None:
    df = pd.DataFrame(
        {
            "family_id": [1, 1, 2, 2],
            "family_canonical": ["Irata", "Irata", "y", "y"],
            "type_slug": ["banker", "banker", "adware", "adware"],
        }
    )

    fla.write_family_label_taxonomy_audit(
        df,
        diagnostics_dir=tmp_path,
        profile_id="test_profile",
        training_min_support=2,
        run_id="test_run",
        artifact_prefix="sql_governed_",
        print_fn=None,
    )
    assert (tmp_path / "sql_governed_family_label_taxonomy_audit.csv").is_file()
    assert (tmp_path / "sql_governed_support_threshold_preview.csv").is_file()
