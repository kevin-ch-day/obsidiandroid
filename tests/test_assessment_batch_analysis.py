"""Denominators and attribution for descriptive evidence-layer comparisons."""

from copy import deepcopy
import pytest
from obsidiandroid.assessment_batch.analysis import summarize
from obsidiandroid.assessment_batch import BatchAssessmentService
from obsidiandroid.diagnostics.assessment_gaps import explain_assessment
from test_assessment_batch import Repo, inputs


def cohort(tmp_path):
    m, s = inputs()
    p = s["entries"][0]
    p["context"]["source_evidence"] = []
    p["engine_evidence"]["scytale"].setdefault("dynamic", [])
    p["engine_evidence"]["permissions"].setdefault("observations", [])
    p["context"]["malwarebazaar_receipt"] = {"raw_sha256": "f" * 64}
    # Enrich only the analysis fixture; service hashes the original input below.
    m, clean = inputs()
    repo = Repo(tmp_path / "db")
    svc = BatchAssessmentService(m, clean, repo)
    plan = svc.plan()
    svc.apply(plan, expected_plan_digest=plan["plan_digest"])
    return p, repo.current(m["hashes"][0])


def test_unresolved_is_not_signature_disagreement_or_absent_permissions(tmp_path):
    p, r = cohort(tmp_path)
    result = summarize([p], [r])
    assert result["summary"]["mb_direct_agreement"]["denominator"] == 0
    assert result["summary"]["mb_direct_agreement"]["rate"] is None
    assert result["summary"]["source_lexical_disagreement"]["rate"] is None
    assert result["evidence_matrix"][0]["source_independence_established"] is False
    assert result["evidence_matrix"][0]["static_attempt_status"] == "NOT_AVAILABLE"


def test_alias_aware_comparison_and_independence_not_inferred(tmp_path):
    p, r = cohort(tmp_path)
    r["assessment"]["family"].update(
        state="supported", value={"name": "Canonical", "slug": "canonical"}
    )
    p["context"]["malwarebazaar_claim"]["signature"] = "Alias"
    p["engine_evidence"]["aliases"] = [
        {"is_active": 1, "alias_token": "Alias", "canonical_family_slug": "canonical"}
    ]
    p["engine_evidence"]["av_labels"] = [
        {"vendor_key": "vendor1", "parsed_family_token": "different", "evidence_id": 1}
    ]
    result = summarize([p], [r])
    assert result["summary"]["mb_direct_agreement"]["numerator"] == 0
    assert result["summary"]["mb_alias_aware_agreement"]["numerator"] == 1
    assert result["summary"]["source_lexical_disagreement"] == {
        "numerator": 1,
        "denominator": 1,
        "rate": 1.0,
    }
    assert result["evidence_matrix"][0]["source_independence_established"] is False


def test_static_bytes_are_not_successful_static_validation(tmp_path):
    p, r = cohort(tmp_path)
    p["context"]["static_baseline"] = {
        "status": "STATIC_PARSE_UNRESOLVED",
        "exact_bytes_verified": True,
        "compatibility": "UNKNOWN",
    }
    s = summarize([p], [r])["summary"]
    assert s["exact_bytes_verified"] == 1 and s["exact_apk_static_validated"] == 0
    p["context"]["static_baseline"]["status"] = "VALID_APK"
    assert summarize([p], [r])["summary"]["exact_apk_static_validated"] == 1


def test_scope_mismatch_and_duplicate_records_fail(tmp_path):
    p, r = cohort(tmp_path)
    with pytest.raises(ValueError):
        summarize([p], [])
    with pytest.raises(ValueError):
        summarize([p], [r, deepcopy(r)])


def test_operator_cutoff_is_stored_value_and_legacy_is_unknown(tmp_path):
    _, r = cohort(tmp_path)
    assert explain_assessment(r)["evidence_cutoff_at"] == "2026-09-21T00:00:00+00:00"
    del r["provenance"]["batch_context"]
    assert explain_assessment(r)["evidence_cutoff_at"] is None
