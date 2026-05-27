"""Smoke tests for headline score scope and split contamination helpers."""

import json
from pathlib import Path

import pandas as pd

from config import app_config
from obsidiandroid.reporting import high_score_skeptic_audits as hssa
from obsidiandroid.reporting import high_score_skeptic_helpers as helpers


def test_write_headline_score_scope(tmp_path: Path) -> None:
    q1 = {
        "governed_samples": 100,
        "aligned_supervised_samples": 100,
        "trainable_after_support_filter": 80,
        "families_represented": 10,
        "malware_types_represented": 3,
    }
    drop = [{"family": "A", "aligned_support": 1}, {"family": "B", "aligned_support": 2}]
    out = hssa.write_headline_score_scope(
        diagnostics_dir=tmp_path,
        run_id="r1",
        q1=q1,
        manifest_context={},
        drop_detail=drop,
    )
    assert out["governed_cohort"]["samples"] == 100
    assert (tmp_path / "headline_score_scope.json").is_file()
    assert (tmp_path / "headline_score_scope.md").is_file()


def test_split_contamination_package_overlap(tmp_path: Path) -> None:
    df = pd.DataFrame(
        [
            {"sample_id": 1, "sha256": "aa", "split_role": "train", "package_name": "com.foo.app", "family_canonical": "F1", "year": 2023},
            {"sample_id": 2, "sha256": "bb", "split_role": "test", "package_name": "com.foo.app", "family_canonical": "F2", "year": 2024},
            {"sample_id": 3, "sha256": "cc", "split_role": "train", "package_name": "com.other", "family_canonical": "F1", "year": 2023},
        ]
    )
    p = tmp_path / "split_freeze_headline_r2.csv"
    df.to_csv(p, index=False)
    payload = hssa.write_split_contamination_audit(
        diagnostics_dir=tmp_path,
        run_id="r2",
        samples_df=None,
    )
    assert payload["sha_overlap_train_test"] == 0
    assert payload["package_names_in_both_splits"] == 1
    assert (tmp_path / "train_test_package_overlap.csv").is_file()


def test_split_contamination_can_use_global_latest_split_ledger(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_root = tmp_path / "output"
    diagnostics_dir = output_root / "runs" / "rid" / "diagnostics"
    global_diag = output_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    global_diag.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)

    df = pd.DataFrame(
        [
            {"sample_id": 1, "sha256": "aa", "split_role": "train", "package_name": "com.foo.app", "family_canonical": "F1", "year": 2023},
            {"sample_id": 2, "sha256": "bb", "split_role": "test", "package_name": "com.foo.app", "family_canonical": "F2", "year": 2024},
        ]
    )
    df.to_csv(global_diag / "split_freeze_headline.latest.csv", index=False)

    payload = hssa.write_split_contamination_audit(
        diagnostics_dir=diagnostics_dir,
        run_id="rid",
        samples_df=None,
    )
    assert payload["package_names_in_both_splits"] == 1
    assert payload["split_audit_path"].endswith("split_freeze_headline.latest.csv")


def test_package_prefix_two_segments() -> None:
    assert hssa._package_prefix_two_segments("com.bad.app") == "com.bad"
    assert hssa._package_prefix_two_segments("single") == "single"


def test_build_label_map_falls_back_to_global_latest(tmp_path: Path, monkeypatch) -> None:
    output_root = tmp_path / "output"
    diagnostics_dir = output_root / "runs" / "rid" / "diagnostics"
    global_diag = output_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True)
    global_diag.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(helpers.oh.app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    (global_diag / "label_name_map.latest.json").write_text(
        json.dumps({"label_name_map": {"1": "Irata"}}),
        encoding="utf-8",
    )

    out = helpers.build_label_map({}, "random_forest", diagnostics_dir, "rid")
    assert out == {"1": "Irata"}


def test_top_feature_modality_audit_falls_back_to_rf_importance_csv(
    make_run_diagnostics_layout,
    monkeypatch,
) -> None:
    output_root, diagnostics_dir, _global_diag = make_run_diagnostics_layout("rid")
    monkeypatch.setattr(app_config, "RUNTIME_OUTPUT_ROOT_BASE", str(output_root), raising=False)
    monkeypatch.setattr(app_config, "RUNTIME_RUN_ID", "rid", raising=False)
    (diagnostics_dir / "rf_impurity_importance_rid.csv").write_text(
        "\n".join(
            [
                "feature_name,modality_guess,impurity_importance,rank",
                "parsed_family_kaspersky,vendor_parsed_label,0.6,1",
                "perm__android_permission_receive_sms,permission,0.4,2",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = hssa.write_top_feature_modality_audit(
        diagnostics_dir=diagnostics_dir,
        model_results={"random_forest": {"metadata": {}}},
    )

    assert payload["importance_mass_by_modality"]["suspicious_label_like"] == 0.6
    assert payload["importance_mass_by_modality"]["permission"] == 0.4
    assert len(payload["top_25"]) == 2


def test_write_smote_effect_check_mentions_evidence_mode_toggle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        app_config,
        "RUNTIME_TRAINING_PROVENANCE_SUMMARY",
        {"holdout_train_smote_effective_last_fit": True},
        raising=False,
    )
    monkeypatch.setattr(
        app_config,
        "RUNTIME_SMOTE_AUDIT_LAST",
        {"original_train_n": 723, "post_resample_train_n": 2664, "method": "SMOTE"},
        raising=False,
    )

    payload = hssa.write_smote_effect_check(diagnostics_dir=tmp_path, run_id="rid")

    assert payload["smote_snapshot"]["method"] == "SMOTE"
    md = (tmp_path / "smote_effect_check.md").read_text(encoding="utf-8")
    assert "OBSIDIAN_DISABLE_SMOTE_IN_EVIDENCE_MODE=1" in md
