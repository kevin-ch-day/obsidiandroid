"""Bounded batch behavior over the real V1 composer and temporary SQLite history."""

from copy import deepcopy

import pytest
from test_assessment_mariadb import DB, factory as factory, ev as ev
from obsidiandroid.assessment_batch.repository import ReviewedMariaDBRepository
from obsidiandroid.assessment.composition import compose_assessment
from obsidiandroid.assessment import AssessmentStore
from obsidiandroid.assessment.composition import digest
from obsidiandroid.assessment_batch import BatchAssessmentService, BatchConflict
from obsidiandroid.cli.assessment_batch import main
from test_operational_assessment import evidence, mapping

CUTOFF = "2026-09-21T00:00:00+00:00"


class Repo:
    def __init__(self, path):
        self.store = AssessmentStore(path)
        self.writes = 0
        self.fail = False

    def current(self, sha):
        return self.store.current(sha)

    def by_id(self, aid):
        return self.store.by_id(aid)

    def append_reviewed(self, result, *, expected_id, assessed_at_utc):
        if self.fail:
            raise RuntimeError("injected rollback")
        current = self.current(result["artifact"]["sha256"])
        if (current["assessment_id"] if current else None) != expected_id:
            raise BatchConflict("changed")
        self.writes += 1
        return self.store.append(result, assessed_at_utc=assessed_at_utc)


def inputs(count=1):
    packets = []
    for i in range(count):
        sha = f"{i + 1:064x}"
        e = evidence()
        e["sha256"] = sha
        e["catalog"][0]["sha256"] = sha
        packets.append(
            {
                "sha256": sha,
                "evidence_cutoff_at": CUTOFF,
                "engine_evidence": e,
                "context": {
                    "artifact_classification": "ANDROID_APK",
                    "artifact_identity_basis": "CATALOG_ASSERTION",
                    "permission_coverage": {
                        "projection_state": "UNKNOWN_NO_DECLARATIONS"
                    },
                    "static_baseline": None,
                    "malwarebazaar_claim": {"signature": "UncorroboratedFamily"},
                },
            }
        )
    return manifest(packets), snapshot(packets)


def snapshot(packets):
    return {
        "contract": "obsidiandroid.batch-evidence.v1",
        "entries": packets,
        "content_sha256": digest(packets),
    }


def manifest(packets):
    return {
        "contract": "obsidiandroid.batch-manifest.v1",
        "hashes": [r["sha256"] for r in packets],
        "evidence_cutoff_at": CUTOFF,
        "snapshot_reference": "frozen.json",
        "snapshot_digest": digest(packets),
        "pinned_revisions": {},
    }


def test_dry_run_and_idempotency(tmp_path):
    m, s = inputs()
    repo = Repo(tmp_path / "db")
    svc = BatchAssessmentService(m, s, repo)
    plan = svc.plan()
    assert repo.writes == 0 and plan["clean"]
    row = plan["rows"][0]
    assert row["change_state"] == "NO_ASSESSMENT"
    assert row["proposed_body"]["assessment"]["family"]["state"] == "unresolved"
    assert row["proposed_body"]["assessment"]["type"]["state"] == "supported"
    assert row["proposed_body"]["assessment"]["variant"]["value"] is None
    assert (
        row["proposed_body"]["provenance"]["batch_context"]["evidence_cutoff_at"]
        == CUTOFF
    )
    receipt = svc.apply(plan, expected_plan_digest=plan["plan_digest"])
    assert receipt["status"] == "complete" and repo.writes == 1
    again = svc.plan()
    assert again["rows"][0]["change_state"] == "CURRENT_ASSESSMENT_STILL_VALID"
    svc.apply(again, expected_plan_digest=again["plan_digest"])
    assert repo.writes == 1
    assert len(repo.store.history(m["hashes"][0])) == 1


def test_source_claim_is_attributed_not_promoted_and_context_changes_append(tmp_path):
    m, s = inputs()
    repo = Repo(tmp_path / "db")
    svc = BatchAssessmentService(m, s, repo)
    p = svc.plan()
    svc.apply(p, expected_plan_digest=p["plan_digest"])
    original = repo.current(m["hashes"][0])
    s["entries"][0]["context"]["malwarebazaar_claim"]["signature"] = "AnotherFamily"
    s = snapshot(s["entries"])
    m = manifest(s["entries"])
    svc = BatchAssessmentService(m, s, repo)
    p = svc.plan()
    assert p["rows"][0]["change_state"] == "EVIDENCE_ADDED_NO_CONCLUSION_CHANGE"
    result = svc.apply(p, expected_plan_digest=p["plan_digest"])
    assert result["rows"][0]["revision"] == 2
    assert repo.by_id(original["assessment_id"]) == original
    assert repo.current(m["hashes"][0])["assessment"]["family"]["value"] is None


def test_material_change_keeps_type_and_family_separate(tmp_path):
    m, s = inputs()
    repo = Repo(tmp_path / "db")
    svc = BatchAssessmentService(m, s, repo)
    p = svc.plan()
    svc.apply(p, expected_plan_digest=p["plan_digest"])
    s["entries"][0]["engine_evidence"]["mappings"] = [mapping()]
    s = snapshot(s["entries"])
    m = manifest(s["entries"])
    p = BatchAssessmentService(m, s, repo).plan()
    assert p["rows"][0]["change_state"] == "MATERIAL_ASSESSMENT_CHANGE"
    assert p["rows"][0]["proposed_body"]["assessment"]["family"]["state"] == "supported"


def test_new_cutoff_alone_does_not_append(tmp_path):
    m, s = inputs()
    repo = Repo(tmp_path / "db")
    svc = BatchAssessmentService(m, s, repo)
    p = svc.plan()
    svc.apply(p, expected_plan_digest=p["plan_digest"])
    s["entries"][0]["evidence_cutoff_at"] = "2026-09-21T00:01:00+00:00"
    s = snapshot(s["entries"])
    m = manifest(s["entries"])
    m["evidence_cutoff_at"] = s["entries"][0]["evidence_cutoff_at"]
    p = BatchAssessmentService(m, s, repo).plan()
    assert not p["rows"][0]["new_revision_needed"]


def test_pinned_baseline_and_runtime_guard(tmp_path):
    m, s = inputs()
    repo = Repo(tmp_path / "db")
    svc = BatchAssessmentService(m, s, repo)
    p = svc.plan()
    svc.apply(p, expected_plan_digest=p["plan_digest"])
    old = repo.current(m["hashes"][0])
    m["pinned_revisions"] = {m["hashes"][0]: old["assessment_id"]}
    p = BatchAssessmentService(m, s, repo).plan()
    assert p["rows"][0]["action"] == "RETAIN_PINNED"
    s["entries"][0]["engine_evidence"]["scytale"]["dynamic"] = [
        {"future_runtime": True}
    ]
    s = snapshot(s["entries"])
    m["snapshot_digest"] = s["content_sha256"]
    with pytest.raises(ValueError, match="runtime"):
        BatchAssessmentService(m, s, repo)


@pytest.mark.parametrize(
    "case",
    [
        "duplicate",
        "limit",
        "digest",
        "cutoff",
        "identity",
        "partial_error",
        "unbound_static",
    ],
)
def test_fail_closed_inputs_before_repository_access(tmp_path, case):
    m, s = inputs()
    repo = Repo(tmp_path / "db")
    maximum = 250
    if case == "duplicate":
        m["hashes"] *= 2
    elif case == "limit":
        maximum = 251
    elif case == "digest":
        m["snapshot_digest"] = "0" * 64
    elif case == "cutoff":
        m["evidence_cutoff_at"] = "2026-09-21T00:00:00"
    else:
        p = s["entries"][0]
        if case == "identity":
            p["engine_evidence"]["catalog"][0]["sha256"] = "f" * 64
        elif case == "partial_error":
            p["engine_evidence"]["errors"] = ["PI:Timeout"]
        else:
            p["context"]["static_baseline"] = {"exact_bytes_verified": False}
        s = snapshot(s["entries"])
        m["snapshot_digest"] = s["content_sha256"]
    with pytest.raises(ValueError):
        BatchAssessmentService(m, s, repo, maximum=maximum)
    assert repo.writes == 0


def test_batch_bound_250_and_dedup_case(tmp_path):
    m, s = inputs(251)
    with pytest.raises(ValueError, match="limit"):
        BatchAssessmentService(m, s, Repo(tmp_path / "db"))


def test_stale_or_tampered_plan_refused(tmp_path):
    m, s = inputs()
    repo = Repo(tmp_path / "db")
    svc = BatchAssessmentService(m, s, repo)
    p = svc.plan()
    bad = deepcopy(p)
    bad["rows"][0]["reason"] = "changed"
    with pytest.raises(BatchConflict):
        svc.apply(bad, expected_plan_digest=p["plan_digest"])
    svc.apply(p, expected_plan_digest=p["plan_digest"])
    with pytest.raises(BatchConflict):
        svc.apply(p, expected_plan_digest=p["plan_digest"])


def test_transaction_failure_accounts_for_remaining_rows(tmp_path):
    m, s = inputs(3)
    repo = Repo(tmp_path / "db")
    svc = BatchAssessmentService(m, s, repo)
    p = svc.plan()
    repo.fail = True
    events = []
    result = svc.apply(p, expected_plan_digest=p["plan_digest"], emit=events.append)
    assert result["status"] == "stopped" and len(events) == 3 and repo.writes == 0
    assert result["rows"][0]["persistence"] == "unchanged_after_failure"
    assert [r["evaluation_state"] for r in result["rows"]] == [
        "FAILED_ASSESSMENT",
        "NOT_ATTEMPTED_AFTER_FAILURE",
        "NOT_ATTEMPTED_AFTER_FAILURE",
    ]


def test_insufficient_evidence_and_conflicts_are_preserved(tmp_path):
    m, s = inputs(2)
    s["entries"][0]["engine_evidence"]["catalog"][0].update(
        platform="unknown", artifact_type=None
    )
    s["entries"][1]["engine_evidence"]["mappings"] = [mapping(1), mapping(2)]
    s = snapshot(s["entries"])
    m = manifest(s["entries"])
    p = BatchAssessmentService(m, s, Repo(tmp_path / "db")).plan()
    assert p["rows"][0]["evaluation_state"] == "ASSESSED_INSUFFICIENT_EVIDENCE"
    assert p["rows"][1]["evaluation_state"] == "ASSESSED_CONFLICTING"


def test_help_does_not_connect(monkeypatch, capsys):
    import mysql.connector

    monkeypatch.setattr(
        mysql.connector, "connect", lambda **kw: pytest.fail("connected")
    )
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0 and "dry-run" in capsys.readouterr().out


def test_failure_after_one_completed_preserves_it(tmp_path):
    m, s = inputs(3)
    repo = Repo(tmp_path / "db")
    svc = BatchAssessmentService(m, s, repo)
    p = svc.plan()
    append = repo.append_reviewed

    def fail_second(*args, **kwargs):
        if repo.writes == 1:
            raise RuntimeError("transaction failed")
        return append(*args, **kwargs)

    repo.append_reviewed = fail_second
    r = svc.apply(p, expected_plan_digest=p["plan_digest"])
    assert r["rows"][0]["persistence"] == "written"
    assert r["rows"][1]["persistence"] == "unchanged_after_failure"
    assert r["rows"][2]["evaluation_state"] == "NOT_ATTEMPTED_AFTER_FAILURE"
    assert repo.current(m["hashes"][0]) and repo.current(m["hashes"][1]) is None


def test_live_reviewed_head_guard_rolls_back_stale_append(factory, ev):
    repository = ReviewedMariaDBRepository(factory, database=DB)
    b = compose_assessment(ev["sha256"], ev, code_version="batch-fixture")
    first = repository.append_reviewed(b, expected_id=None, assessed_at_utc=CUTOFF)
    changed = deepcopy(b)
    changed["provenance"]["code_version"] = "fixture-v2"
    with pytest.raises(BatchConflict):
        repository.append_reviewed(changed, expected_id=None, assessed_at_utc=CUTOFF)
    assert repository.history(ev["sha256"]) == [first]
    second = repository.append_reviewed(
        changed, expected_id=first["assessment_id"], assessed_at_utc=CUTOFF
    )
    assert (
        second["revision"] == 2
        and second["previous_assessment_id"] == first["assessment_id"]
    )
    assert repository.by_id(first["assessment_id"]) == first


def test_live_batch_reuse_and_dry_run_no_writes(factory, ev):
    repository = ReviewedMariaDBRepository(factory, database=DB)
    m, s = inputs()
    p = s["entries"][0]
    p["sha256"] = ev["sha256"]
    p["engine_evidence"] = ev
    s = snapshot([p])
    m = manifest([p])
    svc = BatchAssessmentService(m, s, repository)
    plan = svc.plan()
    assert repository.current(ev["sha256"]) is None
    r = svc.apply(plan, expected_plan_digest=plan["plan_digest"])
    assert r["status"] == "complete"
    repeat = svc.plan()
    r2 = svc.apply(repeat, expected_plan_digest=repeat["plan_digest"])
    assert (
        r2["rows"][0]["persistence"] == "retained"
        and len(repository.history(ev["sha256"])) == 1
    )
