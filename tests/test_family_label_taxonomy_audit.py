"""Unit tests for family label taxonomy audit (no DB)."""

import json
from pathlib import Path

import pandas as pd

from obsidiandroid.diagnostics.hostile_audit.taxonomy_label_quality_audit import (
    write_taxonomy_label_quality_audit,
)
from obsidiandroid.diagnostics import family_label_taxonomy_audit as fla
from obsidiandroid.diagnostics import family_label_confidence_audit


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


def test_write_family_label_taxonomy_audit_artifacts(tmp_path: Path) -> None:
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


def test_write_family_label_taxonomy_audit_artifacts_supports_prefixed_outputs(tmp_path: Path) -> None:
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


def test_taxonomy_label_quality_audit_uses_global_latest_summary_when_run_local_latest_is_pruned(
    make_run_diagnostics_layout,
) -> None:
    """Audit markdown should resolve the global latest taxonomy summary mirror."""
    _, diagnostics_dir, global_diag = make_run_diagnostics_layout("run_tax")

    (global_diag / "taxonomy_consistency_summary.latest.json").write_text(
        json.dumps(
            {
                "rows_evaluated": 10,
                "type_rows_evaluated": 8,
                "family_rows_evaluated": 10,
                "type_missing_label_count": 1,
                "type_noncanonical_count": 0,
                "type_mismatch_count": 2,
                "family_label_mismatch_count": 0,
                "taxonomy_mismatch_count": 3,
                "prediction_error_count": 1,
            }
        ),
        encoding="utf-8",
    )

    out = write_taxonomy_label_quality_audit(diagnostics_dir=diagnostics_dir, run_id="run_tax")

    text = out.read_text(encoding="utf-8")
    assert "taxonomy_consistency_summary.latest.json" in text
    assert "| taxonomy_mismatch_count | 3 |" in text


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


def test_export_family_label_confidence_reports_writes_expected_files(tmp_path: Path) -> None:
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
