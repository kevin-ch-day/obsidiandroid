"""Tests for locked benchmark paper constants export."""

from __future__ import annotations

from pathlib import Path

import json
import pandas as pd
import pytest

from obsidiandroid.governance.paper_constants import (
    build_paper_constants_payload,
    write_paper_constants,
)


def _matched_contract() -> dict:
    return {
        "paper_locked": True,
        "profile_id": "malicious_temporal_stability_locked",
        "contract_id": "malicious_temporal_stability_locked_contract",
        "expected": {
            "sample_count": 3,
            "family_count": 2,
            "type_count": 1,
            "time_window_start_utc": "2020-01-01T00:00:00Z",
            "time_window_end_utc": "2026-01-01T00:00:00Z",
            "time_window_semantics": "start_inclusive_end_exclusive",
        },
        "sample_id_lock": {
            "cohort_hash": "cohort123",
            "taxonomy_hash": "tax123",
        },
        "validation": {"status": "match"},
    }


def test_build_paper_constants_requires_split_and_cohort_hash() -> None:
    contract = _matched_contract()
    contract["sample_id_lock"]["cohort_hash"] = ""
    with pytest.raises(ValueError, match="cohort_hash"):
        build_paper_constants_payload(
            run_id="r1",
            profile_id="malicious_temporal_stability_locked",
            cohort_contract=contract,
            split_hash="split123",
            samples_df=pd.DataFrame({"sample_id": [1], "family_canonical": ["FamA"]}),
        )


def test_write_paper_constants_rejects_count_mismatch(tmp_path: Path) -> None:
    out_root = tmp_path
    contract = _matched_contract()
    paper_dir = out_root / "artifacts" / "paper"
    paper_dir.mkdir(parents=True)
    existing = {
        "sample_count": 99,
        "family_count": 2,
        "malware_type_count": 1,
        "cohort_hash": "cohort123",
    }
    (paper_dir / "paper_constants.json").write_text(json.dumps(existing), encoding="utf-8")
    with pytest.raises(ValueError, match="sample_count"):
        write_paper_constants(
            run_id="r1",
            profile_id="malicious_temporal_stability_locked",
            cohort_contract=contract,
            split_hash="split123",
            samples_df=pd.DataFrame(
                {
                    "sample_id": [1, 2, 3],
                    "family_canonical": ["FamA", "FamA", "FamB"],
                }
            ),
            output_root=out_root,
        )

