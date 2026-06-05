from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from obsidiandroid.diagnostics import v3_label_contract

pytestmark = pytest.mark.contract


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sample_id": [1, 2, 3, 4, 5],
            "family_id": [10, 10, 11, 12, 12],
            "family_canonical": ["Gigabud", "Gigabud", "SpyNote", "DoNot", "DoNot"],
            "type_slug": ["banker", "banker", "rat", "spyware", "spyware"],
            "category_primary": ["trojan", "trojan", "rat", "trojan", "trojan"],
            "category_subtype": ["banker", "banker", "rat", "spyware", "spyware"],
            "sample_label_kind": ["family_or_common_name"] * 5,
        }
    )


def test_build_v3_label_contract_distinguishes_canonical_profiles() -> None:
    df = _sample_df()
    major = v3_label_contract.build_v3_label_contract(
        profile={
            "profile_id": "android_malware_major_families",
            "cohort_gates": {"support_floor_mode": "benchmark_eligibility", "min_samples_per_family": 3},
            "profile_status": {"support_tier": "final"},
        },
        samples_df=df,
        run_id="run_major",
    )
    all_current = v3_label_contract.build_v3_label_contract(
        profile={
            "profile_id": "android_malware_all_current",
            "cohort_gates": {"support_floor_mode": "diagnostic_only"},
            "profile_status": {"support_tier": "final"},
        },
        samples_df=df,
        run_id="run_all",
    )

    assert major["profile_role"] == "support-gated major-family benchmark surface"
    assert all_current["profile_role"] == "current-state census / exploratory surface"
    assert major["claim_surface_label"] == "Support-gated benchmark cohort"
    assert all_current["claim_surface_label"] == "Current-corpus diagnostic surface"
    assert major["claim_readiness_wording"] != all_current["claim_readiness_wording"]
    assert major["run_mode"] == "benchmark"
    assert all_current["run_mode"] == "diagnostic"


def test_build_v3_label_contract_uses_type_namespace_for_type_taxonomy_profile() -> None:
    payload = v3_label_contract.build_v3_label_contract(
        profile={
            "profile_id": "android_malware_type_taxonomy",
            "training_label_field": "type_slug",
            "cohort_gates": {"min_samples_per_family": 1},
            "profile_status": {"support_tier": "final"},
        },
        samples_df=_sample_df(),
        run_id="run_type",
    )
    assert payload["target_label_namespace"] == "malware_type_slug"
    assert payload["training_label_field"] == "type_slug"
    assert payload["type_label_summary"]
    assert payload["family_label_summary"]


def test_export_v3_label_contract_writes_json_and_markdown(tmp_path: Path) -> None:
    paths = v3_label_contract.export_v3_label_contract(
        diagnostics_dir=tmp_path,
        run_id="runx",
        profile={
            "profile_id": "android_malware_expanded_families",
            "cohort_gates": {"support_floor_mode": "benchmark_eligibility", "min_samples_per_family": 2},
            "profile_status": {"support_tier": "final"},
        },
        samples_df=_sample_df(),
        min_support=2,
    )
    assert len(paths) == 2
    md_text = (tmp_path / "v3_label_contract_runx.md").read_text(encoding="utf-8")
    assert "Expanded-family exploratory cohort" in md_text or "broader family expansion" in md_text
    assert "Permission patterns describe structural" in md_text
    assert "dynamic_analysis_execution" in md_text
