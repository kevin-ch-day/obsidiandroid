"""Synthetic tests for live-corpus family context composers."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from obsidiandroid.reporting.live_corpus_family_context import (
    EVIDENCE_STATES,
    build_external_context_matrix,
    build_family_context_inventory,
    build_family_type_assignment_audit,
    compose_live_corpus_family_context,
    validate_hypotheses,
    verify_source_identity,
)


def _mini_snapshot() -> pd.DataFrame:
    rows = []
    # ClayRat rat
    for i in range(40):
        rows.append(
            {
                "sample_id": i,
                "sha256": f"a{i:064d}"[:64],
                "family_id": 185,
                "family_canonical": "ClayRat",
                "type_slug": "rat",
                "family_label_raw": "ClayRat",
                "source_batch_label": "batch_a",
                "effective_first_seen_year": 2025,
            }
        )
    # Other RAT
    for i in range(40, 70):
        rows.append(
            {
                "sample_id": i,
                "sha256": f"b{i:064d}"[:64],
                "family_id": 184,
                "family_canonical": "ArsinkRAT",
                "type_slug": "rat",
                "family_label_raw": "Arsink RAT",
                "source_batch_label": "batch_b",
                "effective_first_seen_year": 2025,
            }
        )
    # Godfather banker
    for i in range(70, 100):
        rows.append(
            {
                "sample_id": i,
                "sha256": f"c{i:064d}"[:64],
                "family_id": 9,
                "family_canonical": "Godfather",
                "type_slug": "banker",
                "family_label_raw": "Godfather",
                "source_batch_label": "batch_c",
                "effective_first_seen_year": 2022,
            }
        )
    # Second banker
    for i in range(100, 120):
        rows.append(
            {
                "sample_id": i,
                "sha256": f"d{i:064d}"[:64],
                "family_id": 42,
                "family_canonical": "Devixor",
                "type_slug": "banker",
                "family_label_raw": "Devixor",
                "source_batch_label": "batch_d",
                "effective_first_seen_year": 2025,
            }
        )
    # Applite identity-uncertain
    for i in range(120, 130):
        rows.append(
            {
                "sample_id": i,
                "sha256": f"e{i:064d}"[:64],
                "family_id": 51,
                "family_canonical": "Applite",
                "type_slug": "banker",
                "family_label_raw": "Applite",
                "source_batch_label": "batch_e",
                "effective_first_seen_year": 2024,
            }
        )
    # Multi-type synthetic family
    for i in range(130, 140):
        rows.append(
            {
                "sample_id": i,
                "sha256": f"f{i:064d}"[:64],
                "family_id": 999,
                "family_canonical": "DualRoleFam",
                "type_slug": "banker" if i < 135 else "rat",
                "family_label_raw": "DualRoleFam",
                "source_batch_label": "batch_f",
                "effective_first_seen_year": 2023,
            }
        )
    return pd.DataFrame(rows)


def _mini_fam_prev() -> pd.DataFrame:
    rows = []
    specs = [
        ("ClayRat", "rat", 40, "android.permission.send_sms", 95.0, 38),
        ("ClayRat", "rat", 40, "android.permission.read_contacts", 90.0, 36),
        ("ClayRat", "rat", 40, "android.permission.internet", 100.0, 40),
        ("ArsinkRAT", "rat", 30, "android.permission.send_sms", 20.0, 6),
        ("ArsinkRAT", "rat", 30, "android.permission.read_contacts", 25.0, 8),
        ("ArsinkRAT", "rat", 30, "android.permission.internet", 100.0, 30),
        ("Godfather", "banker", 30, "android.permission.bind_accessibility_service", 80.0, 24),
        ("Godfather", "banker", 30, "android.permission.internet", 100.0, 30),
        ("Devixor", "banker", 20, "android.permission.bind_accessibility_service", 10.0, 2),
        ("Devixor", "banker", 20, "android.permission.internet", 100.0, 20),
        ("Devixor", "banker", 20, "android.permission.send_sms", 70.0, 14),
        ("Applite", "banker", 10, "android.permission.internet", 100.0, 10),
    ]
    for fam, typ, support, perm, prev, pos in specs:
        rows.append(
            {
                "family_canonical": fam,
                "type_slug": typ,
                "family_support": support,
                "permission": perm,
                "prevalence_pct": prev,
                "positive_count": pos,
            }
        )
    return pd.DataFrame(rows)


def _mini_type_prev() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"type_slug": "rat", "permission": "android.permission.send_sms", "prevalence_pct": 60.0},
            {
                "type_slug": "rat",
                "permission": "android.permission.read_contacts",
                "prevalence_pct": 55.0,
            },
            {"type_slug": "rat", "permission": "android.permission.internet", "prevalence_pct": 100.0},
            {
                "type_slug": "banker",
                "permission": "android.permission.bind_accessibility_service",
                "prevalence_pct": 40.0,
            },
            {"type_slug": "banker", "permission": "android.permission.internet", "prevalence_pct": 100.0},
            {"type_slug": "banker", "permission": "android.permission.send_sms", "prevalence_pct": 30.0},
        ]
    )


def test_evidence_states_are_complete() -> None:
    assert "LOCAL_OBSERVED" in EVIDENCE_STATES
    assert "EXTERNAL_REPORTED" in EVIDENCE_STATES
    assert "IDENTITY_UNCERTAIN" in EVIDENCE_STATES
    assert "NOT_TESTABLE_STATICALLY" in EVIDENCE_STATES


def test_identity_uncertain_family_in_external_matrix() -> None:
    snap = _mini_snapshot()
    inv = pd.DataFrame(
        [
            {
                "family_canonical": "Applite",
                "first_observed_year": 2024,
                "last_observed_year": 2024,
            }
        ]
    )
    matrix = build_external_context_matrix(snapshot=snap, inventory=inv)
    applite = matrix[matrix.family_slug == "Applite"].iloc[0]
    assert applite.evidence_independence == "IDENTITY_UNCERTAIN"
    assert applite.local_validation_status == "IDENTITY_UNCERTAIN"


def test_multi_type_family_handling() -> None:
    snap = _mini_snapshot()
    audit = build_family_type_assignment_audit(
        snapshot=snap,
        families=("DualRoleFam", "ClayRat", "Applite"),
    )
    dual = audit[audit.family_canonical == "DualRoleFam"].iloc[0]
    assert bool(dual.multi_type_family) is True
    clay = audit[audit.family_canonical == "ClayRat"].iloc[0]
    assert clay.public_role_agreement_status == "LOCALLY_SUPPORTED"
    app = audit[audit.family_canonical == "Applite"].iloc[0]
    assert app.public_role_agreement_status == "IDENTITY_UNCERTAIN"




def test_static_vs_non_testable_hypotheses() -> None:
    hypo = validate_hypotheses(
        fam_prev=_mini_fam_prev(),
        type_prev=_mini_type_prev(),
        snapshot=_mini_snapshot(),
    )
    clay = hypo[hypo.hypothesis_id == "clayrat_sms_contact_phone"].iloc[0]
    assert clay.testable_statically == "yes"
    assert clay.status in {"LOCALLY_SUPPORTED", "LOCALLY_MIXED"}
    runtime = hypo[hypo.hypothesis_id == "godfather_virtualization_runtime"].iloc[0]
    assert runtime.testable_statically == "no"
    assert runtime.status == "NOT_TESTABLE_STATICALLY"


def test_inventory_deterministic_and_no_hashes_in_headline_fields() -> None:
    snap = _mini_snapshot()
    mem = snap.rename(columns={"sha256": "sha256"}).copy()
    mem["android_package_name"] = ["pkg." + str(i % 7) for i in range(len(mem))]
    inv1 = build_family_context_inventory(
        snapshot=snap,
        membership=mem,
        fam_prev=_mini_fam_prev(),
        type_prev=_mini_type_prev(),
        pairwise_headline=pd.DataFrame(),
        top_n=5,
    )
    inv2 = build_family_context_inventory(
        snapshot=snap,
        membership=mem,
        fam_prev=_mini_fam_prev(),
        type_prev=_mini_type_prev(),
        pairwise_headline=pd.DataFrame(),
        top_n=5,
    )
    assert inv1.to_csv(index=False) == inv2.to_csv(index=False)
    joined = " ".join(inv1.astype(str).fillna("").to_numpy().ravel().tolist())
    assert "a000" not in joined  # sample hash prefixes should not appear in cells


def test_compose_offline_no_db_no_mutation(tmp_path: Path) -> None:
    run_id = "20260721T000000Z__testrun"
    run_root = tmp_path / "run"
    diag = run_root / "diagnostics"
    tables = run_root / "bundles" / "permission_trends" / "tables"
    diag.mkdir(parents=True)
    tables.mkdir(parents=True)
    (run_root / ".COMPLETE").write_text("{}", encoding="utf-8")

    snap = _mini_snapshot()
    snap_path = diag / f"analysis_snapshot_{run_id}.csv"
    snap.to_csv(snap_path, index=False)
    fam = _mini_fam_prev()
    fam.to_csv(tables / f"permission_prevalence_by_family_{run_id}.csv", index=False)
    _mini_type_prev().to_csv(tables / f"permission_prevalence_by_type_{run_id}.csv", index=False)
    pd.DataFrame(
        [
            {
                "run_id": run_id,
                "profile_id": "android_malware_all_current",
                "sample_count": len(snap),
                "samples_with_permission_rows": len(snap),
            }
        ]
    ).to_csv(tables / f"permission_coverage_report_{run_id}.csv", index=False)

    manifest = {
        "run_id": run_id,
        "profile_id": "android_malware_all_current",
        "git_commit": "deadbeef",
        "cohort_prepared_row_count": len(snap),
        "dataset_hash": "abc",
        "config_hash": "def",
        "analysis_snapshot": {"snapshot_sha256_hash": "ghi"},
    }
    man_path = run_root / "run_manifest.json"
    man_path.write_text(json.dumps(manifest), encoding="utf-8")
    before = snap_path.read_bytes()

    out = compose_live_corpus_family_context(
        run_root=run_root,
        run_id=run_id,
        output_dir=diag / "live_corpus_family_context",
        repo_root=tmp_path,
        top_n=5,
    )
    assert out["boundaries"]["database_access"] is False
    assert out["boundaries"]["core_access"] is False
    assert out["boundaries"]["source_artifact_mutation"] is False
    assert snap_path.read_bytes() == before
    assert (diag / "live_corpus_family_context" / "manifest.json").is_file()
    assert (diag / "live_corpus_family_context" / "family_context_inventory.csv").is_file()
    assert (diag / "live_corpus_family_context" / "dominant_family_robustness.csv").is_file()

    with pytest.raises(ValueError, match="run identity mismatch"):
        verify_source_identity(run_root, expected_run_id="wrong_id")
