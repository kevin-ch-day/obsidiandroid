"""Tests for manifest runtime support verdict policy."""

from __future__ import annotations

import pytest

from obsidiandroid.pipeline.manifest.runtime_support import derive_aggregate_pipeline_verdict

pytestmark = pytest.mark.contract


def test_canonical_v3_research_validity_error_fails_verdict() -> None:
    verdict = derive_aggregate_pipeline_verdict(
        run_status_raw="complete",
        result_code=0,
        rv_err="bundle export failed",
        canonical_v3=True,
    )
    assert verdict == "FAILED"


def test_canonical_v3_hostile_audit_partial_fails_verdict() -> None:
    verdict = derive_aggregate_pipeline_verdict(
        run_status_raw="complete",
        result_code=0,
        hostile_failed=True,
        canonical_v3=True,
    )
    assert verdict == "FAILED"


def test_non_canonical_research_validity_error_warns() -> None:
    verdict = derive_aggregate_pipeline_verdict(
        run_status_raw="complete",
        result_code=0,
        rv_err="bundle export failed",
        canonical_v3=False,
    )
    assert verdict == "PASS_WITH_WARNINGS"
