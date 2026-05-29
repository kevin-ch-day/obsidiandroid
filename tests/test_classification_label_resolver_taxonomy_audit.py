"""Tests for taxonomy consistency auditing in classification label resolver."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.labeling import classification_label_resolver as resolver


def test_extract_type_slug_from_label_parses_structured_path(monkeypatch) -> None:
    """Type parser should extract slug token from structured label string."""
    monkeypatch.setattr(
        resolver.app_config,
        "TYPE_LABEL_ALIAS_MAP",
        {},
        raising=False,
    )
    value = resolver._extract_type_slug_from_label("trojan/android.dropper.applite[de]")  # pylint: disable=protected-access
    assert value == "dropper"


def test_extract_type_slug_from_label_applies_alias_map(monkeypatch) -> None:
    """Type parser should normalize known aliases (e.g., spy -> spyware)."""
    monkeypatch.setattr(
        resolver.app_config,
        "TYPE_LABEL_ALIAS_MAP",
        {"spy": "spyware"},
        raising=False,
    )
    value = resolver._extract_type_slug_from_label("trojan/android.spy.familytag")  # pylint: disable=protected-access
    assert value == "spyware"


def test_extract_type_slug_from_label_parses_prefix_type_form(monkeypatch) -> None:
    """Type parser should support `<type>/android.<family>` label variants."""
    monkeypatch.setattr(
        resolver.app_config,
        "TYPE_LABEL_ALIAS_MAP",
        {},
        raising=False,
    )
    value = resolver._extract_type_slug_from_label("rat/android.xrat[004c91f91]")  # pylint: disable=protected-access
    assert value == "rat"


def test_extract_family_slug_from_label_parses_prefix_type_form() -> None:
    """Family parser should support `<type>/android.<family>` label variants."""
    value = resolver._extract_family_slug_from_label("rat/android.xrat[004c91f91]")  # pylint: disable=protected-access
    assert value == "xrat"


def test_export_taxonomy_consistency_audit_writes_mismatch_report(monkeypatch, tmp_path: Path) -> None:
    """Audit should export mismatch report when canonical type/family diverge."""
    run_id = "run_taxonomy_test"
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    runtime_meta = pd.DataFrame(
        [
            {
                "sample_id": 1001,
                "type_slug": "adware",
                "family_canonical": "Applite",
            }
        ]
    )
    monkeypatch.setattr(resolver.app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", runtime_meta, raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(
        resolver.app_config,
        "TYPE_LABEL_ALIAS_MAP",
        {},
        raising=False,
    )
    monkeypatch.setattr(
        resolver.app_config,
        "ENABLE_TYPE_AUDIT_FROM_COHORT_TYPE_SLUG",
        True,
        raising=False,
    )

    labels_df = pd.DataFrame(
        [
            {
                "sample_id": 1001,
                "predicted_family": "Applite",
                "classification_label": "trojan/android.dropper.applite[de]",
            }
        ]
    )

    mismatch_path, mismatch_count, summary = resolver._export_taxonomy_consistency_audit(labels_df)  # pylint: disable=protected-access
    assert mismatch_path is not None
    assert mismatch_count == 1
    assert int(summary.get("taxonomy_mismatch_count", -1)) == 1

    mismatch_df = pd.read_csv(str(mismatch_path))
    assert int(mismatch_df.shape[0]) == 1
    assert str(mismatch_df.loc[0, "type_slug_expected"]) == "adware"
    assert str(mismatch_df.loc[0, "label_type_slug"]) == "dropper"
    prediction_path = diagnostics_dir / f"prediction_errors_{run_id}.csv"
    assert prediction_path.exists()
    noncanonical_path = diagnostics_dir / f"taxonomy_noncanonical_type_tokens_{run_id}.csv"
    assert noncanonical_path.exists()

    summary_path = diagnostics_dir / f"taxonomy_consistency_summary_{run_id}.json"
    assert summary_path.exists()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert int(payload["total_mismatch_count"]) == 1
    assert int(payload["paper_facing_taxonomy_mismatch_count"]) == 0
    assert payload["mismatch_reason_counts"] == [{"mismatch_reason": str(payload["mismatch_examples"][0]["mismatch_reason"]), "count": 1}]
    assert len(payload["mismatch_examples"]) == 1
    assert payload["mismatch_examples"][0]["type_slug_expected"] == "adware"
    assert payload["mismatch_examples"][0]["label_type_slug"] == "dropper"


def test_export_taxonomy_consistency_audit_omits_run_local_latest_duplicates(
    monkeypatch, tmp_path: Path
) -> None:
    """Run-scoped diagnostics should mirror taxonomy latest files globally, not locally."""
    run_id = "run_taxonomy_latest"
    output_root = tmp_path / "output"
    diagnostics_dir = output_root / "runs" / run_id / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    runtime_meta = pd.DataFrame(
        [
            {
                "sample_id": 1001,
                "type_slug": "adware",
                "family_canonical": "Applite",
            }
        ]
    )
    monkeypatch.setattr(resolver.app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", runtime_meta, raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(resolver.app_config, "TYPE_LABEL_ALIAS_MAP", {}, raising=False)
    monkeypatch.setattr(resolver.app_config, "ENABLE_TYPE_AUDIT_FROM_COHORT_TYPE_SLUG", True, raising=False)

    labels_df = pd.DataFrame(
        [
            {
                "sample_id": 1001,
                "predicted_family": "Applite",
                "classification_label": "trojan/android.dropper.applite[de]",
            }
        ]
    )

    resolver._export_taxonomy_consistency_audit(labels_df)  # pylint: disable=protected-access

    assert not (diagnostics_dir / "taxonomy_consistency_summary.latest.json").exists()
    assert not (diagnostics_dir / "taxonomy_consistency_mismatches.latest.csv").exists()
    assert not (diagnostics_dir / "prediction_errors.latest.csv").exists()
    assert not (diagnostics_dir / "taxonomy_noncanonical_type_tokens.latest.csv").exists()

    global_diag = output_root / "diagnostics"
    assert (global_diag / "taxonomy_consistency_summary.latest.json").exists()
    assert (global_diag / "taxonomy_consistency_mismatches.latest.csv").exists()
    assert (global_diag / "prediction_errors.latest.csv").exists()
    assert (global_diag / "taxonomy_noncanonical_type_tokens.latest.csv").exists()


def test_taxonomy_lineage_unknown_when_runtime_sets_not_attached(monkeypatch, tmp_path: Path) -> None:
    """Lineage columns must be NA when RUNTIME_* id lists were never set — not all-False."""
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    runtime_meta = pd.DataFrame(
        [{"sample_id": 1001, "type_slug": "adware", "family_canonical": "Applite"}]
    )
    monkeypatch.setattr(resolver.app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", runtime_meta, raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_RUN_ID", "run_lineage_na", raising=False)
    monkeypatch.setattr(resolver.app_config, "TYPE_LABEL_ALIAS_MAP", {}, raising=False)
    for attr in (
        "RUNTIME_FUSED_MATRIX_SAMPLE_IDS",
        "RUNTIME_ALIGNED_SUPERVISED_SAMPLE_IDS",
        "RUNTIME_POST_FAMILY_SUPPORT_TRAINABLE_SAMPLE_IDS",
    ):
        monkeypatch.setattr(resolver.app_config, attr, None, raising=False)

    labels_df = pd.DataFrame(
        [
            {
                "sample_id": 1001,
                "predicted_family": "Other",
                "classification_label": "trojan/android.banker.applite",
            }
        ]
    )
    mismatch_path, mismatch_count, _ = resolver._export_taxonomy_consistency_audit(labels_df)  # pylint: disable=protected-access
    assert mismatch_path is not None and mismatch_count >= 1
    mismatch_df = pd.read_csv(str(mismatch_path))
    assert bool(mismatch_df["reached_fused_feature_matrix"].isna().all()) is True


def test_export_taxonomy_consistency_audit_handles_missing_runtime_columns(
    monkeypatch, tmp_path: Path
) -> None:
    """Audit should not crash when runtime metadata lacks optional taxonomy columns."""
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    runtime_meta = pd.DataFrame([{"sample_id": 1001}])
    monkeypatch.setattr(resolver.app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", runtime_meta, raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_RUN_ID", "run_missing_cols", raising=False)

    labels_df = pd.DataFrame([{"sample_id": 1001, "classification_label": "trojan/android.banker.z"}])
    mismatch_path, mismatch_count, summary = resolver._export_taxonomy_consistency_audit(labels_df)  # pylint: disable=protected-access
    assert mismatch_path is not None
    assert mismatch_count == 0
    assert int(summary.get("rows_evaluated", 0)) == 1


def test_export_taxonomy_consistency_audit_uses_type_slug_expected_column(
    monkeypatch, tmp_path: Path
) -> None:
    """Audit should evaluate type rows when runtime metadata provides type_slug_expected."""
    run_id = "run_type_expected"
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    runtime_meta = pd.DataFrame(
        [
            {
                "sample_id": 2001,
                "type_slug_expected": "banker",
                "family_canonical": "TrickMo",
            }
        ]
    )
    monkeypatch.setattr(resolver.app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", runtime_meta, raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_RUN_ID", run_id, raising=False)

    labels_df = pd.DataFrame(
        [
            {
                "sample_id": 2001,
                "predicted_family": "TrickMo",
                "classification_label": "trojan/android.banker.trickmo",
            }
        ]
    )
    mismatch_path, mismatch_count, summary = resolver._export_taxonomy_consistency_audit(labels_df)  # pylint: disable=protected-access
    assert mismatch_path is not None
    assert mismatch_count == 0
    assert int(summary.get("type_rows_evaluated", 0)) == 1

    summary_path = diagnostics_dir / f"taxonomy_consistency_summary_{run_id}.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert int(payload["type_rows_evaluated"]) == 1
    assert int(payload["type_mismatch_count"]) == 0
    assert str(payload.get("type_expected_source", "")) == "type_slug_expected"


def test_taxonomy_audit_accepts_prefix_type_label_form(
    monkeypatch, tmp_path: Path
) -> None:
    """Audit should not flag valid `<type>/android.<family>` labels as missing type."""
    run_id = "run_prefix_type_ok"
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    runtime_meta = pd.DataFrame(
        [
            {
                "sample_id": 7001,
                "type_slug_expected": "rat",
                "family_canonical": "XRat",
            }
        ]
    )
    monkeypatch.setattr(resolver.app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", runtime_meta, raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(resolver.app_config, "TYPE_LABEL_ALIAS_MAP", {}, raising=False)

    labels_df = pd.DataFrame(
        [
            {
                "sample_id": 7001,
                "predicted_family": "XRat",
                "classification_label": "rat/android.xrat[004c91f91]",
            }
        ]
    )

    mismatch_path, mismatch_count, summary = resolver._export_taxonomy_consistency_audit(labels_df)  # pylint: disable=protected-access
    assert mismatch_path is not None
    assert mismatch_count == 0
    assert int(summary.get("type_missing_label_count", -1)) == 0
    assert int(summary.get("type_mismatch_count", -1)) == 0
    assert int(summary.get("family_label_mismatch_count", -1)) == 0


def test_export_taxonomy_consistency_audit_falls_back_to_type_slug_source(
    monkeypatch, tmp_path: Path
) -> None:
    """Audit should record fallback taxonomy source when type_slug_expected is absent."""
    run_id = "run_type_fallback"
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    runtime_meta = pd.DataFrame(
        [
            {
                "sample_id": 2101,
                "type_slug": "spyware",
                "family_canonical": "SpyNote",
            }
        ]
    )
    monkeypatch.setattr(resolver.app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", runtime_meta, raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_RUN_ID", run_id, raising=False)

    labels_df = pd.DataFrame(
        [
            {
                "sample_id": 2101,
                "predicted_family": "SpyNote",
                "classification_label": "trojan/android.spy.spynote",
            }
        ]
    )
    _, _, summary = resolver._export_taxonomy_consistency_audit(labels_df)  # pylint: disable=protected-access
    assert int(summary.get("type_rows_evaluated", 0)) == 1
    assert str(summary.get("type_expected_source", "")) == "type_slug"


def test_export_taxonomy_consistency_audit_counts_type_guard_suppressions(
    monkeypatch, tmp_path: Path
) -> None:
    """Taxonomy summary should expose type-guard suppression counts from row output."""
    run_id = "run_type_guard_count"
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    runtime_meta = pd.DataFrame(
        [
            {
                "sample_id": 2201,
                "type_slug": "banker",
                "family_canonical": "Irata",
            }
        ]
    )
    monkeypatch.setattr(resolver.app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", runtime_meta, raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_RUN_ID", run_id, raising=False)

    labels_df = pd.DataFrame(
        [
            {
                "sample_id": 2201,
                "predicted_family": "other",
                "raw_predicted_family": "SpyNote",
                "override_tag": "type_guard_family_suppressed",
                "classification_label": "trojan/android.banker.other",
            }
        ]
    )

    _, _, summary = resolver._export_taxonomy_consistency_audit(labels_df)  # pylint: disable=protected-access
    assert int(summary.get("type_guard_family_suppressed_count", -1)) == 1
    assert summary.get("override_tag_counts") == [
        {"override_tag": "type_guard_family_suppressed", "count": 1}
    ]

    prediction_path = diagnostics_dir / f"prediction_errors_{run_id}.csv"
    prediction_df = pd.read_csv(prediction_path)
    assert str(prediction_df.loc[0, "raw_predicted_family"]) == "SpyNote"
    assert str(prediction_df.loc[0, "override_tag"]) == "type_guard_family_suppressed"


def test_run_summary_and_export_fails_in_paper_mode_when_type_audit_blind(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Paper mode should hard-fail when taxonomy type audit evaluates zero rows."""
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    runtime_meta = pd.DataFrame([{"sample_id": 1001, "family_canonical": "Applite"}])
    labels_df = pd.DataFrame(
        [
            {
                "sample_id": 1001,
                "predicted_family": "Applite",
                "classification_label": "trojan/android.dropper.applite[de]",
            }
        ]
    )
    monkeypatch.setattr(resolver.app_config, "PAPER_MODE_ENABLED", True, raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", runtime_meta, raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_RUN_ID", "run_blind_taxonomy", raising=False)
    monkeypatch.setattr(resolver.app_config, "ENABLE_EXCEL_EXPORT", False, raising=False)
    monkeypatch.setattr(
        resolver,
        "summarize_prediction_results",
        lambda _df: None,
    )

    with pytest.raises(RuntimeError):
        resolver._run_summary_and_export(labels_df, model_output=None)  # pylint: disable=protected-access


def test_run_summary_and_export_warns_when_noncanonical_dominates(monkeypatch) -> None:
    """Warn when noncanonical type labels dominate taxonomy mismatches."""
    labels_df = pd.DataFrame([{"sample_id": 1, "classification_label": "trojan/android.banker.x"}])
    monkeypatch.setattr(
        resolver,
        "_export_taxonomy_consistency_audit",
        lambda _df: (
            "dummy.csv",
            100,
            {
                "taxonomy_mismatch_count": 100,
                "type_noncanonical_count": 90,
                "prediction_error_count": 5,
                "prediction_errors_csv_path": "prediction.csv",
                "type_rows_evaluated": 10,
            },
        ),
    )
    monkeypatch.setattr(resolver.app_config, "PAPER_MODE_ENABLED", False, raising=False)
    monkeypatch.setattr(resolver.app_config, "ENABLE_EXCEL_EXPORT", False, raising=False)
    monkeypatch.setattr(
        resolver.app_config,
        "TAXONOMY_NONCANONICAL_DOMINANCE_WARN_THRESHOLD",
        0.60,
        raising=False,
    )
    monkeypatch.setattr(
        resolver.app_config,
        "TAXONOMY_NONCANONICAL_DOMINANCE_MIN_COUNT",
        50,
        raising=False,
    )
    monkeypatch.setattr(resolver, "summarize_prediction_results", lambda _df: None)
    warned: dict[str, bool] = {"hit": False}

    def _capture_warning(msg: str) -> None:
        if "noncanonical type labels dominate" in str(msg):
            warned["hit"] = True

    monkeypatch.setattr(resolver.du, "print_warning", _capture_warning)
    monkeypatch.setattr(resolver.du, "print_info", lambda _msg: None)

    resolver._run_summary_and_export(labels_df, model_output=None)  # pylint: disable=protected-access
    assert warned["hit"] is True


def test_run_summary_and_export_does_not_strict_fail_for_non_paper_facing_taxonomy_noise(
    monkeypatch,
) -> None:
    """Strict paper/evidence policy should not fail on mismatches already excluded from paper-facing summaries."""
    labels_df = pd.DataFrame([{"sample_id": 1, "classification_label": "trojan/android.banker.x"}])
    monkeypatch.setattr(
        resolver,
        "_export_taxonomy_consistency_audit",
        lambda _df: (
            "dummy.csv",
            377,
            {
                "taxonomy_mismatch_count": 377,
                "paper_facing_taxonomy_mismatch_count": 0,
                "type_noncanonical_count": 3,
                "prediction_error_count": 2,
                "prediction_errors_csv_path": "prediction.csv",
                "type_rows_evaluated": 964,
            },
        ),
    )
    monkeypatch.setattr(resolver.app_config, "PAPER_MODE_ENABLED", True, raising=False)
    monkeypatch.setattr(resolver.app_config, "STRICT_TAXONOMY_MISMATCH_BLOCKING", True, raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_EVIDENCE_STRICT_MODE", True, raising=False)
    monkeypatch.setattr(resolver.app_config, "TAXONOMY_MISMATCH_STRICT_MAX_ALLOWED", 0, raising=False)
    monkeypatch.setattr(resolver.app_config, "ENABLE_EXCEL_EXPORT", False, raising=False)
    monkeypatch.setattr(resolver, "summarize_prediction_results", lambda _df: None)
    monkeypatch.setattr(resolver.du, "print_warning", lambda _msg: None)
    monkeypatch.setattr(resolver.du, "print_info", lambda _msg: None)

    resolver._run_summary_and_export(labels_df, model_output=None)  # pylint: disable=protected-access


def test_taxonomy_audit_treats_configured_canonical_types_as_canonical(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Configured canonical types should prevent false noncanonical flags."""
    run_id = "run_canonical_types"
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    runtime_meta = pd.DataFrame(
        [
            {
                "sample_id": 3001,
                "type_slug_expected": "banker",
                "family_canonical": "Irata",
            }
        ]
    )
    monkeypatch.setattr(resolver.app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", runtime_meta, raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(
        resolver.app_config,
        "CANONICAL_TYPE_SLUGS",
        ("banker", "adware", "stealer", "sms-trojan", "rat", "spyware"),
        raising=False,
    )

    labels_df = pd.DataFrame(
        [
            {
                "sample_id": 3001,
                "predicted_family": "Irata",
                "classification_label": "trojan/android.spyware.irata",
            }
        ]
    )
    _, _, summary = resolver._export_taxonomy_consistency_audit(labels_df)  # pylint: disable=protected-access
    assert int(summary.get("type_noncanonical_count", -1)) == 0
    assert int(summary.get("type_mismatch_count", -1)) == 1


def test_taxonomy_audit_handles_missing_label_and_prediction_tokens(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Audit should not mark family mismatches when label/prediction tokens are missing."""
    run_id = "run_missing_tokens"
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    runtime_meta = pd.DataFrame(
        [
            {
                "sample_id": 4010,
                "type_slug_expected": "banker",
                "family_canonical": "Anatsa",
            }
        ]
    )
    monkeypatch.setattr(resolver.app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", runtime_meta, raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_RUN_ID", run_id, raising=False)

    labels_df = pd.DataFrame(
        [
            {
                "sample_id": 4010,
                "predicted_family": "",
                "classification_label": "",
            }
        ]
    )

    mismatch_path, mismatch_count, summary = resolver._export_taxonomy_consistency_audit(labels_df)  # pylint: disable=protected-access
    assert mismatch_path is not None
    assert mismatch_count == 1
    assert int(summary.get("type_missing_label_count", -1)) == 1
    assert int(summary.get("family_label_mismatch_count", -1)) == 0
    assert int(summary.get("prediction_error_count", -1)) == 0

    mismatch_df = pd.read_csv(str(mismatch_path))
    assert int(mismatch_df.shape[0]) == 1
    assert str(mismatch_df.loc[0, "mismatch_reason"]) == "type_label_missing"


def test_taxonomy_audit_normalizes_alias_map_keys_and_values(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Type alias mappings should be normalized before taxonomy comparisons."""
    run_id = "run_alias_normalization"
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    runtime_meta = pd.DataFrame(
        [
            {
                "sample_id": 5010,
                "type_slug_expected": "banker",
                "family_canonical": "Anatsa",
            }
        ]
    )
    monkeypatch.setattr(resolver.app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", runtime_meta, raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_RUN_ID", run_id, raising=False)
    monkeypatch.setattr(
        resolver.app_config,
        "TYPE_LABEL_ALIAS_MAP",
        {"Banking": "Banker", "": "ignore", "dropper": ""},
        raising=False,
    )

    labels_df = pd.DataFrame(
        [
            {
                "sample_id": 5010,
                "predicted_family": "Anatsa",
                "classification_label": "trojan/android.banking.anatsa",
            }
        ]
    )

    _, mismatch_count, summary = resolver._export_taxonomy_consistency_audit(labels_df)  # pylint: disable=protected-access
    assert mismatch_count == 0
    assert int(summary.get("type_mismatch_count", -1)) == 0


def test_taxonomy_audit_skips_invalid_sample_id_keys(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Rows with invalid sample IDs should not be evaluated by taxonomy audit joins."""
    run_id = "run_invalid_sample_ids"
    diagnostics_dir = tmp_path / "output" / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    runtime_meta = pd.DataFrame(
        [
            {"sample_id": None, "type_slug_expected": "banker", "family_canonical": "Anatsa"},
            {"sample_id": 6001, "type_slug_expected": "banker", "family_canonical": "Anatsa"},
        ]
    )
    monkeypatch.setattr(resolver.app_config, "RUNTIME_SPLIT_SAMPLE_METADATA", runtime_meta, raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_DIAGNOSTICS_DIR", str(diagnostics_dir), raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_RUN_ID", run_id, raising=False)

    labels_df = pd.DataFrame(
        [
            {"sample_id": float("nan"), "predicted_family": "Anatsa", "classification_label": "trojan/android.banker.anatsa"},
            {"sample_id": 6001, "predicted_family": "Anatsa", "classification_label": "trojan/android.banker.anatsa"},
        ]
    )

    _, mismatch_count, summary = resolver._export_taxonomy_consistency_audit(labels_df)  # pylint: disable=protected-access
    assert mismatch_count == 0
    assert int(summary.get("rows_evaluated", -1)) == 1
    assert int(summary.get("type_rows_evaluated", -1)) == 1


def test_apply_family_name_projection_uses_runtime_label_name_map(monkeypatch) -> None:
    """Family-name projection should use explicit runtime label maps instead of DB lookups."""
    monkeypatch.setattr(
        resolver.app_config,
        "RUNTIME_LABEL_NAME_MAP",
        {"44": "Irata", "51": "Applite"},
        raising=False,
    )

    df = pd.DataFrame(
        [
            {"true_family": "44", "predicted_family": "51"},
        ]
    )

    projected = resolver._apply_family_name_projection(df, model_output=None)  # pylint: disable=protected-access
    assert str(projected.loc[0, "true_family"]) == "Irata"
    assert str(projected.loc[0, "predicted_family"]) == "Applite"
    assert str(projected.loc[0, "true_family_id"]) == "44"
    assert str(projected.loc[0, "predicted_family_id"]) == "51"


def test_apply_family_name_projection_fails_in_paper_mode_without_label_map(monkeypatch) -> None:
    """Paper-mode exports should fail fast when numeric family IDs cannot be projected."""
    monkeypatch.setattr(resolver.app_config, "PAPER_MODE_ENABLED", True, raising=False)
    monkeypatch.setattr(resolver.app_config, "RUNTIME_LABEL_NAME_MAP", {}, raising=False)
    monkeypatch.setattr(
        resolver.app_config,
        "RUNTIME_SPLIT_SAMPLE_METADATA",
        pd.DataFrame(),
        raising=False,
    )

    df = pd.DataFrame([{"true_family": "44", "predicted_family": "51"}])

    with pytest.raises(RuntimeError):
        resolver._apply_family_name_projection(df, model_output=None)  # pylint: disable=protected-access
