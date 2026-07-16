import pandas as pd
import pytest

from obsidiandroid.features.av_detection_contract import (
    fit_av_detection_contract,
    select_coherent_report_snapshot,
    transform_av_detection_features,
)


def _rows():
    return pd.DataFrame(
        [
            {"sample_id": 1, "engine_name": "Alpha", "result": "undetected", "report_id": "old", "updated_at": "2026-01-01"},
            {"sample_id": 1, "engine_name": "Alpha", "result": "Trojan.X", "report_id": "new", "updated_at": "2026-02-01"},
            {"sample_id": 1, "engine_name": "Beta", "result": "timeout", "report_id": "new", "updated_at": "2026-02-01"},
            {"sample_id": 2, "engine_name": "Alpha", "result": "benign", "report_id": "r2", "updated_at": "2026-02-01"},
            {"sample_id": 2, "engine_name": "Beta", "result": "failure", "report_id": "r2", "updated_at": "2026-02-01"},
        ]
    )


def test_contract_uses_one_latest_report_per_sample_and_train_observation_only():
    contract = fit_av_detection_contract(_rows(), [1], scope="all_observed")
    assert contract.engine_columns == ("alpha",)
    assert contract.report_selection.iloc[0]["selected_snapshot_id"] == "new"
    features = transform_av_detection_features(_rows(), contract, [1, 2]).set_index("sample_id")
    assert features.loc[1, "avdet__alpha"] == 1
    assert features.loc[2, "avobs__alpha"] == 1


def test_timeout_failure_and_unsupported_do_not_make_an_engine_observed():
    contract = fit_av_detection_contract(_rows(), [1, 2], scope="all_observed")
    assert contract.engine_columns == ("alpha",)


def test_readiness_scope_intersects_train_observed_schema():
    contract = fit_av_detection_contract(_rows(), [1], scope="readiness_eligible", readiness_eligible_engines=["Beta"])
    assert contract.engine_columns == ()


def test_unknown_structured_status_fails_closed():
    rows = _rows().iloc[:1].copy()
    rows["status"] = "novel"
    with pytest.raises(ValueError, match="Unknown structured"):
        fit_av_detection_contract(rows, [1], scope="all_observed")


def test_ambiguous_missing_snapshot_identity_fails_closed():
    rows = pd.DataFrame([{"sample_id": 1, "engine_name": "a", "result": "x"}, {"sample_id": 1, "engine_name": "b", "result": "y", "report_id": "known"}])
    with pytest.raises(ValueError, match="LIVE_REPORT_IDENTITY_UNVERIFIED"):
        select_coherent_report_snapshot(rows)


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ("malicious", (1, 1)), ("Trojan.FreeText", (1, 1)), ("suspicious", (1, 1)),
        ("harmless", (0, 1)), ("undetected", (0, 1)), ("timeout", (0, 0)),
        ("confirmed_timeout", (0, 0)), ("failure", (0, 0)), ("type_unsupported", (0, 0)),
        (None, (0, 0)), ("", (0, 0)), ("none", (0, 0)), ("n/a", (0, 0)),
    ],
)
def test_av_status_truth_table(result, expected):
    rows = pd.DataFrame([{"sample_id": 1, "engine_name": "alpha", "result": result, "report_id": "r"}])
    contract = fit_av_detection_contract(rows, [1], scope="all_observed")
    out = transform_av_detection_features(rows, contract, [1]).set_index("sample_id")
    if expected == (0, 0):
        assert contract.engine_columns == ()
    else:
        assert (out.loc[1, "avdet__alpha"], out.loc[1, "avobs__alpha"]) == expected


@pytest.mark.parametrize("status", ["malformed", "unknown"])
def test_structured_malformed_status_never_becomes_train_observed(status):
    rows = pd.DataFrame([{"sample_id": 1, "engine_name": "alpha", "status": status, "report_id": "r"}])
    with pytest.raises(ValueError, match="Unknown structured"):
        fit_av_detection_contract(rows, [1], scope="all_observed")
