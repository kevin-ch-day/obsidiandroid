#!/usr/bin/env python3
"""Build checked-in V3 canonical slot fixtures for CI offline validation."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from obsidiandroid.common.run_slots import CANONICAL_V3_PROFILES, _SLOT_BY_PROFILE  # noqa: E402
from obsidiandroid.diagnostics import ml_seed_exports  # noqa: E402
from obsidiandroid.diagnostics.v3_dl_handoff import (  # noqa: E402
    build_v3_dl_handoff_observability_block,
    export_v3_dl_handoff_summary,
)

FIXTURE_ROOT = REPO_ROOT / "artifacts" / "baselines" / "v3_canonical_slots"

PROFILE_CONTRACTS: dict[str, dict[str, str]] = {
    "android_malware_major_families": {
        "profile_role": "support-gated major-family benchmark surface",
        "target_label_namespace": "malware_family",
        "claim_surface_label": "Support-gated benchmark cohort",
        "training_label_field": "family_id",
    },
    "android_malware_type_taxonomy": {
        "profile_role": "malware type/category taxonomy surface",
        "target_label_namespace": "malware_type_slug",
        "claim_surface_label": "Type taxonomy benchmark",
        "training_label_field": "type_slug",
    },
    "android_malware_expanded_families": {
        "profile_role": "broader family expansion / stress surface",
        "target_label_namespace": "malware_family",
        "claim_surface_label": "Expanded-family exploratory cohort",
        "training_label_field": "family_id",
    },
    "android_malware_all_current": {
        "profile_role": "current-state census / exploratory surface",
        "target_label_namespace": "malware_family",
        "claim_surface_label": "Current-corpus diagnostic surface",
        "training_label_field": "family_id",
    },
}

PERMISSION_ROWS_BY_PROFILE: dict[str, list[str]] = {
    "android_malware_major_families": [
        "banker,android.permission.internet,10,8,80.0",
        "banker,android.permission.read_sms,10,3,30.0",
    ],
    "android_malware_type_taxonomy": [
        "rat,android.permission.camera,8,4,50.0",
        "spyware,android.permission.record_audio,6,2,33.3",
        "banker,android.permission.internet,10,9,90.0",
    ],
    "android_malware_expanded_families": [
        "banker,android.permission.send_sms,12,5,41.6",
        "rat,android.permission.access_fine_location,7,1,14.2",
    ],
    "android_malware_all_current": [
        "adware,android.permission.internet,20,18,90.0",
        "banker,android.permission.read_contacts,15,4,26.6",
        "rat,android.permission.system_alert_window,9,2,22.2",
    ],
}


def _write_slot(*, profile_id: str, idx: int) -> None:
    run_slot = _SLOT_BY_PROFILE[profile_id]
    run_id = f"20260606T9{idx:05d}Z__fixture{idx}"
    slot_root = FIXTURE_ROOT / run_slot
    diagnostics_dir = slot_root / "diagnostics"
    tables_dir = slot_root / "bundles" / "permission_trends" / "tables"
    contracts_dir = slot_root / "bundles" / "permission_trends" / "contracts"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    contracts_dir.mkdir(parents=True, exist_ok=True)

    contract = PROFILE_CONTRACTS[profile_id]
    (diagnostics_dir / f"v3_label_contract_{run_id}.json").write_text(
        json.dumps({"contract_version": "v3_label_contract_v1", "run_id": run_id, "profile_id": profile_id, **contract}),
        encoding="utf-8",
    )
    (diagnostics_dir / f"permission_pattern_contract_{run_id}.json").write_text(
        json.dumps({"pattern_scale": {"levels": [{"level": i} for i in range(10)]}}),
        encoding="utf-8",
    )
    (diagnostics_dir / f"ml_sample_label_fact_{run_id}.csv").write_text(
        "sample_id,supervised_label,supervised_label_namespace\n1,alpha,malware_family\n",
        encoding="utf-8",
    )
    (contracts_dir / f"permission_alias_map_{run_id}.json").write_text(
        json.dumps(
            {
                "permission_alias_map_version": "perm_alias_v1",
                "alias_map": {
                    "android.permission.install_packages": "android.permission.request_install_packages",
                },
            }
        ),
        encoding="utf-8",
    )
    rows = PERMISSION_ROWS_BY_PROFILE[profile_id]
    (tables_dir / f"permission_prevalence_by_type_{run_id}.csv").write_text(
        "type_slug,permission,n_samples,permission_positive_count,prevalence_pct\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    (tables_dir / f"permission_prevalence_by_family_{run_id}.csv").write_text(
        "family_canonical,permission,n_samples,permission_positive_count,prevalence_pct\n"
        "Alpha,android.permission.internet,4,4,100.0\n",
        encoding="utf-8",
    )
    dataset_hash = f"fixture_dataset_hash_{idx:02d}"
    (slot_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "profile_id": profile_id,
                "dataset_hash": dataset_hash,
                "cohort_size": 1,
            }
        ),
        encoding="utf-8",
    )

    vocab_path = ml_seed_exports.refresh_persisted_permission_vocabulary(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
    )
    vocab_payload = json.loads(vocab_path.read_text(encoding="utf-8"))
    ml_manifest = {
        "export_version": "ml_run_manifest_v1",
        "run_id": run_id,
        "profile_id": profile_id,
        "dataset_hash": dataset_hash,
        "cohort_size": 1,
        "sample_label_rows": 1,
        "vocabulary_entry_count": int(vocab_payload.get("entry_count", 0) or 0),
        "seed_artifact_refs": {
            "v3_label_contract": f"v3_label_contract_{run_id}.json",
            "permission_pattern_contract": f"permission_pattern_contract_{run_id}.json",
            "ml_sample_label_fact": f"ml_sample_label_fact_{run_id}.csv",
            "ml_permission_vocabulary": f"ml_permission_vocabulary_{run_id}.json",
        },
        "optional_seed_artifact_refs": {},
    }
    (diagnostics_dir / f"ml_run_manifest_{run_id}.json").write_text(
        json.dumps(ml_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    export_v3_dl_handoff_summary(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        profile={"profile_id": profile_id},
        manifest={"profile_id": profile_id, "cohort_size": 1, "dataset_hash": dataset_hash},
        manifest_context={"cohort_persistence_source": "diagnostics_export", "dataset_hash": dataset_hash},
    )
    handoff_block = build_v3_dl_handoff_observability_block(
        diagnostics_dir=diagnostics_dir,
        run_id=run_id,
        manifest={"profile_id": profile_id, "cohort_size": 1, "dataset_hash": dataset_hash},
        manifest_context={"cohort_persistence_source": "diagnostics_export", "dataset_hash": dataset_hash},
    )
    (diagnostics_dir / "run_observability_summary.json").write_text(
        json.dumps(
            {
                "pipeline_status": "PASS",
                "research_validity_status": "PASS",
                "cohort_persistence_source": "diagnostics_export",
                "dataset_hash": dataset_hash,
                "v3_dl_handoff": handoff_block,
            }
        ),
        encoding="utf-8",
    )


def main() -> int:
    if FIXTURE_ROOT.exists():
        shutil.rmtree(FIXTURE_ROOT)
    FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)
    for idx, profile_id in enumerate(CANONICAL_V3_PROFILES):
        _write_slot(profile_id=profile_id, idx=idx)
    print(f"Wrote V3 canonical slot fixtures under {FIXTURE_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
