"""Read-only explanations preserve labels, immutable records and error privacy."""

import hashlib
import json
from copy import deepcopy

import mysql.connector
import pytest
from obsidiandroid.assessment import AssessmentStore, compose_assessment
from obsidiandroid.assessment.service import AssessmentService
from obsidiandroid.cli.assessment import format_assessment, main
from obsidiandroid.diagnostics.assessment_gaps import explain_assessment
from test_operational_assessment import SHA, evidence


def record(tmp_path, *, unsupported=False):
    e = evidence()
    if unsupported:
        e["catalog"][0].update(platform="unknown", artifact_type=None)
    store = AssessmentStore(tmp_path / "assessment.sqlite")
    r = store.append(
        compose_assessment(SHA, e, code_version="fixture"),
        assessed_at_utc="2026-09-21T00:00:00+00:00",
    )
    return store, r


def test_unknown_catalog_is_explained_without_changing_assessment(tmp_path):
    _, r = record(tmp_path, unsupported=True)
    before = deepcopy(r)
    report = explain_assessment(r)
    gap = next(g for g in report["gaps"] if g["code"] == "CATALOG_ARTIFACT_UNSUPPORTED")
    assert gap["facts"] == {"platform": "unknown", "format": None}
    assert r == before and not report["mutations_performed"]
    assert "invalid APK bytes" in gap["next_step"]
    assert "platform=unknown; format=Unknown" in format_assessment(r)


def test_explain_cli_never_assesses_and_preserves_sqlite(tmp_path, monkeypatch, capsys):
    store, r = record(tmp_path)
    before = hashlib.sha256(store.path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        AssessmentService, "assess", lambda *a, **kw: pytest.fail("write attempted")
    )
    assert main(["explain", SHA, "--store", str(store.path), "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["assessment_id"] == r["assessment_id"] and output["revision"] == 1
    assert hashlib.sha256(store.path.read_bytes()).hexdigest() == before
    assert store.history(SHA) == [r]


def test_missing_explain_store_not_created(tmp_path, capsys):
    path = tmp_path / "absent" / "missing.sqlite"
    assert main(["explain", SHA, "--store", str(path), "--json"]) == 2
    assert not path.parent.exists()
    assert json.loads(capsys.readouterr().err)["status"] == "error"


def test_observation_absence_is_not_permission_absence(tmp_path):
    _, r = record(tmp_path)
    report = explain_assessment(r)
    gap = next(g for g in report["gaps"] if g["code"] == "PERMISSION_EVIDENCE_UNAVAILABLE")
    assert "do not establish permission absence" in gap["reason"]
    assert "CATALOG_ARTIFACT_UNSUPPORTED" not in {g["code"] for g in report["gaps"]}


def test_projection_and_governance_gaps_remain_separate(tmp_path):
    _, r = record(tmp_path)
    r["evidence"]["permissions"].update(
        retained_tokens_missing_downstream=["android.permission.INTERNET"], unresolved_count=2
    )
    r["assessment"]["family"]["state"] = "conflict"
    report = explain_assessment(r)
    codes = {g["code"] for g in report["gaps"]}
    assert {
        "RETAINED_PERMISSION_PROJECTION_GAP",
        "PERMISSION_SEMANTICS_UNRESOLVED",
        "FAMILY_CONFLICT",
    } <= codes
    assert "no live upstream refresh" in report["scope"]


@pytest.mark.parametrize("as_json", [False, True])
@pytest.mark.parametrize(
    "error",
    [
        ValueError("SECRET malformed option line"),
        mysql.connector.OperationalError(errno=1045, msg="SECRET credential"),
    ],
)
def test_cli_does_not_echo_connection_or_config_secrets(monkeypatch, capsys, error, as_json):
    def fail(**kwargs):
        raise error

    monkeypatch.setattr(mysql.connector, "connect", fail)
    args = [
        "explain",
        SHA,
        "--database",
        "obsidiandroid_core_prod",
        "--allow-production",
        "--db-option-file",
        "unused",
    ]
    assert main(args + (["--json"] if as_json else [])) == 2
    output = capsys.readouterr()
    assert "SECRET" not in output.out + output.err
    if as_json:
        result = json.loads(output.err)
        assert result["status"] == "error"
        if isinstance(error, mysql.connector.Error):
            assert result["errno"] == 1045
