"""Tests for paper-safe status semantics in output inventory."""

from analysis.diagnostics.output_inventory import evaluate_paper_safe_status


def test_paper_safe_status_not_applicable_when_paper_mode_off() -> None:
    status, reasons = evaluate_paper_safe_status(
        paper_mode=False,
        manifest={},
        compliance_report=None,
    )
    assert status == "NOT_APPLICABLE"
    assert reasons == []


def test_paper_safe_status_pass_when_compliance_passes() -> None:
    status, reasons = evaluate_paper_safe_status(
        paper_mode=True,
        manifest={},
        compliance_report={"overall_status": "pass"},
    )
    assert status == "PASS"
    assert reasons == []


def test_paper_safe_status_fail_when_compliance_fails() -> None:
    status, reasons = evaluate_paper_safe_status(
        paper_mode=True,
        manifest={},
        compliance_report={"overall_status": "fail"},
    )
    assert status == "FAIL"
    assert "paper_compliance_not_pass" in reasons
