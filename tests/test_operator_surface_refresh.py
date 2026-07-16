"""Tests for offline operator-surface refresh on completed runs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidiandroid.observability.pipeline_observability.finalize import (
    patch_observability_post_operator_artifacts,
)
from obsidiandroid.reporting import operator_surface_refresh as osr

pytestmark = pytest.mark.integration


def _write_minimal_refresh_tree(
    tmp_path: Path,
    *,
    top_family_share_pct: float = 30.0,
    top5_share_pct: float = 65.0,
) -> tuple[Path, Path, str]:
    run_id = "run_refresh"
    profile_id = "android_malware_all_current"
    run_root = tmp_path / "runs" / "allcurrent_diagnostic"
    diagnostics_dir = run_root / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    (run_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "profile_id": profile_id,
                "run_mode": "full",
                "evidence_mode": False,
                "paper_mode": {
                    "resolved_value": False,
                    "source": "profile",
                },
                "cohort_size": 1000,
                "aligned_supervised_rows": 1000,
                "post_low_support_training_rows": 980,
                "model_summary": {
                    "top_model": "logistic_regression",
                    "top_macro_f1": 0.684,
                    "top_weighted_f1": 0.79,
                    "top_accuracy": 0.81,
                },
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / "run_observability_summary.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "profile_id": profile_id,
                "run_mode": "full",
                "evidence_mode": True,
                "paper_mode": True,
                "claim_surface_label": "Locked publication cohort",
                "model": {"top_macro_f1": 0.684, "top_model": "logistic_regression"},
                "scientific_adequacy": {
                    "posture": "Strong",
                    "blockers": [],
                    "supervised_family_claims_suitable": True,
                    "temporal_future_only_rows_dropped": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / "cohort_foundation.json").write_text(
        json.dumps(
            {
                "cohort_prepared_row_count": 1000,
                "family_type_summary": {
                    "family_count": 40,
                    "type_count": 6,
                    "top_family": "SpyNote",
                    "top_family_count": 300,
                    "top_family_share_pct": top_family_share_pct,
                    "top3_share_pct": 55.0,
                    "top5_share_pct": top5_share_pct,
                    "family_distribution": {"SpyNote": 300},
                    "type_distribution": {"banker": 400},
                },
                "gate_stats": {"excluded_unmapped_family": 0, "excluded_missing_sha256": 0},
            }
        ),
        encoding="utf-8",
    )
    (diagnostics_dir / f"taxonomy_target_surfaces_{run_id}.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / f"feature_modality_coverage_summary_{run_id}.json").write_text(
        json.dumps({"permission_pi_signal_positive_n": 900, "vendor_merge_n": 1000}),
        encoding="utf-8",
    )
    (diagnostics_dir / "feature_contract.json").write_text("{}", encoding="utf-8")
    (diagnostics_dir / "cohort_membership.csv").write_text(
        "sample_id,family_canonical,type_slug\n1,SpyNote,banker\n",
        encoding="utf-8",
    )
    return run_root, diagnostics_dir, run_id


def test_refresh_operator_surfaces_from_disk_rewrites_claim_and_foundation(tmp_path: Path) -> None:
    run_root, diagnostics_dir, run_id = _write_minimal_refresh_tree(tmp_path)

    result = osr.refresh_operator_surfaces_from_disk(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="android_malware_all_current",
    )

    assert result["ok"] is True
    assert result["publication_ready"] is False
    assert result["supervised_family_claims_suitable"] is False
    assert result["claim_surface"] == "Current-corpus diagnostic surface"

    foundation = json.loads((diagnostics_dir / "dataset_foundation_summary.json").read_text(encoding="utf-8"))
    assert foundation["supervised_family_claims_suitable"] is False
    assert foundation["concentration_warning"] is True

    claim = json.loads((diagnostics_dir / f"claim_readiness_summary_{run_id}.json").read_text(encoding="utf-8"))
    assert claim["publication_ready"] is False
    assert claim["primary_surface"] == "broad_current_corpus"
    assert claim["supervised_family_claims_suitable"] is False
    assert claim["modeled_family_classes"] == claim["claim_eligible_family_classes"]


def test_patch_observability_post_operator_artifacts_syncs_claim_surface(tmp_path: Path) -> None:
    run_root, diagnostics_dir, run_id = _write_minimal_refresh_tree(tmp_path)
    manifest = json.loads((run_root / "run_manifest.json").read_text(encoding="utf-8"))
    (diagnostics_dir / "dataset_foundation_summary.json").write_text(
        json.dumps({"supervised_family_claims_suitable": False}),
        encoding="utf-8",
    )

    assert patch_observability_post_operator_artifacts(
        diagnostics_dir=diagnostics_dir,
        manifest=manifest,
    ) is True

    obs = json.loads((diagnostics_dir / "run_observability_summary.json").read_text(encoding="utf-8"))
    assert obs["evidence_mode"] is False
    assert obs["paper_mode"] is False
    assert obs["claim_surface_label"] == "Current-corpus diagnostic surface"
    assert obs["scientific_adequacy"]["supervised_family_claims_suitable"] is False


def test_refresh_operator_surfaces_rewrites_stale_cohort_funnel_plain(tmp_path: Path) -> None:
    run_root, diagnostics_dir, run_id = _write_minimal_refresh_tree(tmp_path)
    obs_path = diagnostics_dir / "run_observability_summary.json"
    obs = json.loads(obs_path.read_text(encoding="utf-8"))
    obs.update(
        {
            "feature_matrix_rows": 1000,
            "aligned_supervised_rows": 1000,
            "post_low_support_training_rows": 980,
            "cohort_funnel_plain": (
                "1000 prepared-cohort rows → 1000 feature_matrix_rows (fused) → "
                "1000 aligned supervised → 980 post-family-support trainable rows"
            ),
        }
    )
    obs_path.write_text(json.dumps(obs), encoding="utf-8")

    result = osr.refresh_operator_surfaces_from_disk(
        run_root=run_root,
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile_id="android_malware_all_current",
    )

    assert result["ok"] is True
    assert result.get("funnel_patched") is True
    refreshed = json.loads(obs_path.read_text(encoding="utf-8"))
    assert "post-alignment trainable rows" in refreshed["cohort_funnel_plain"]
    assert "post-family-support" not in refreshed["cohort_funnel_plain"]


def test_build_manifest_context_from_run_artifacts_preserves_metadata_dicts(tmp_path: Path) -> None:
    manifest = {
        "paper_mode": {"resolved_value": False, "source": "profile"},
        "evidence_mode": {"resolved_value": False, "source": "profile"},
        "aligned_supervised_rows": 4563,
    }
    ctx = osr.build_manifest_context_from_run_artifacts(manifest=manifest, observability={})
    assert ctx["paper_mode"]["resolved_value"] is False
    assert ctx["evidence_mode"]["resolved_value"] is False
    assert ctx["aligned_supervised_rows"] == 4563
