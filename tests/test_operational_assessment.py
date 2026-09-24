"""Operational assessment composition and disposable SQLite contract tests."""

from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3

import pytest

from obsidiandroid.assessment import (
    AssessmentService,
    AssessmentStore,
    FrozenEvidenceSource,
    compose_assessment,
    validate_sha256,
)
from obsidiandroid.assessment.composition import digest, ordered
from obsidiandroid.assessment.source import (
    ReadOnlyEvidenceReader,
    retained_permission_tokens,
)
from obsidiandroid.cli.assessment import main, format_assessment

SHA = "a" * 64
OTHER = "b" * 64


def evidence():
    return {
        "sha256": SHA,
        "catalog": [
            {
                "sample_id": 1,
                "sha256": SHA,
                "platform": "android",
                "artifact_type": "apk",
                "classification_primary": "banker",
            }
        ],
        "taxonomy": [
            {"type_id": 1, "type_slug": "banker", "type_name": "Banker", "is_active": 1}
        ],
        "permissions": {"availability": "unavailable"},
        "scytale": {"availability": "unavailable"},
    }


def mapping(fid=1, active=True):
    return {
        "mapping_id": fid,
        "sample_id": 1,
        "family_id": fid,
        "review_status": "accepted",
        "family": {
            "family_id": fid,
            "family_slug": f"family-{fid}",
            "family_name": f"Family {fid}",
            "is_active": int(active),
            "family_status": "active" if active else "needs_review",
            "primary_type_id": 1,
        },
    }


def bundle(e):
    artifacts = {e["sha256"]: e}
    return {
        "contract_version": "obsidiandroid.assessment-evidence.v1",
        "artifacts": artifacts,
        "content_sha256": digest(ordered(artifacts)),
    }


def permission_evidence():
    e = evidence()
    e["permissions"] = {
        "availability": "available",
        "observations": [
            {
                "obs_id": 1,
                "sample_id": 1,
                "source": "virustotal",
                "permission_string": "android.permission.INTERNET",
            }
        ],
        "releases": [
            {
                "catalog_release_id": "release-1",
                "release_status": "ACCEPTED",
                "is_current_accepted": 1,
            }
        ],
        "semantics": [
            {
                "canonical_permission": "android.permission.INTERNET",
                "catalog_release_id": "release-1",
                "declaration_revision_id": 1,
                "identity_status": "ACCEPTED",
                "acceptance_status": "ACCEPTED",
                "source_status": "AVAILABLE",
                "authority_class": "AOSP_PUBLIC",
                "compatibility_protection_expression": "normal",
                "unresolved_conflict_count": 0,
            }
        ],
    }
    return e


@pytest.mark.parametrize(
    "bad", ["", "abc", "g" * 64, SHA + "\n", "/tmp/sample.apk", None]
)
def test_malformed_sha(bad):
    with pytest.raises(ValueError):
        validate_sha256(bad)


def test_known_unknown_and_snapshot_scope():
    source = FrozenEvidenceSource(bundle(evidence()))
    assert source.lookup(SHA.upper())["catalog"][0]["sample_id"] == 1
    outside = compose_assessment(OTHER, source.lookup(OTHER))
    assert outside["processing"]["status"] == "insufficient_evidence"
    assert outside["processing"]["reasons"] == ["not_in_snapshot"]
    absent = compose_assessment(
        OTHER, {"sha256": OTHER, "catalog": [], "lookup_status": "not_found"}
    )
    assert absent["processing"]["reasons"] == ["not_found"]


@pytest.mark.parametrize(
    "mappings,state",
    [
        ([], "unresolved"),
        ([mapping()], "supported"),
        ([mapping(active=False)], "unresolved"),
        ([mapping(), mapping(2)], "conflict"),
    ],
)
def test_family_mapping_states(mappings, state):
    e = evidence()
    e["mappings"] = mappings
    result = compose_assessment(SHA, e)
    family = result["assessment"]["family"]
    assert family["state"] == state
    assert result["assessment"]["type"]["value"]["slug"] == "banker"
    if state != "supported":
        assert family["value"] is None
    if state == "conflict":
        assert len(family["candidates"]) == 2
        assert result["processing"]["status"] == "complete_with_conflict"


def test_open_governance_conflict_blocks_single_mapping():
    e = evidence()
    e["mappings"] = [mapping()]
    e["family_conflicts"] = [{"conflict_case_id": 1, "conflict_state": "open"}]
    assert compose_assessment(SHA, e)["assessment"]["family"]["state"] == "conflict"


def test_reviewed_authority_requires_active_dimension():
    e = evidence()
    e["authority"] = [
        {
            "authority_id": 1,
            "sample_id": 1,
            "is_active": 1,
            "review_status": "reviewed",
            "governed_family_id": 1,
            "governed_family_name": "Family 1",
            "governed_family_slug": "family-1",
        }
    ]
    assert compose_assessment(SHA, e)["assessment"]["family"]["state"] == "unresolved"
    e["families"] = [mapping()["family"]]
    assert compose_assessment(SHA, e)["assessment"]["family"]["state"] == "supported"
    e["authority"][0]["review_status"] = "auto"
    assert compose_assessment(SHA, e)["assessment"]["family"]["state"] == "unresolved"


def av_evidence():
    e = evidence()
    row = {
        "sample_id": 1,
        "sha256": SHA,
        "vt_last_analysis_date": "2026-09-19",
        "vt_malicious_count": 60,
        "vt_suspicious_count": 0,
        "vt_harmless_count": 0,
        "vt_undetected_count": 2,
    }
    e["av_scan"] = [row]
    e["av_verdict"] = [
        {
            **row,
            "score_version": "vt_confidence_v1",
            "recommended_action": "promote",
            "confidence_bucket": "high",
        }
    ]
    return e


def test_av_source_policy_not_benign_or_model_prediction():
    assert (
        compose_assessment(SHA, evidence())["assessment"]["artifact_label"]["value"]
        == "ANDROID_APPLICATION"
    )
    e = av_evidence()
    result = compose_assessment(SHA, e)
    assert result["assessment"]["artifact_label"]["value"] == "ANDROID_MALWARE"
    assert result["confidence"]["model_probability"] is None
    e["av_scan"][0]["vt_last_analysis_date"] = "old"
    assert (
        compose_assessment(SHA, e)["assessment"]["artifact_label"]["value"]
        == "ANDROID_APPLICATION"
    )


def test_false_positive_review_preserves_conflict():
    e = av_evidence()
    e["av_review"] = [{"sample_id": 1, "sha256": SHA, "review_reason": "review"}]
    result = compose_assessment(SHA, e)
    assert result["assessment"]["artifact_label"]["state"] == "conflict"
    assert result["assessment"]["artifact_label"]["value"] is None


def test_permission_release_and_unavailability():
    result = compose_assessment(SHA, permission_evidence())
    p = result["evidence"]["permissions"]
    assert p["resolved_count"] == 1 and p["tokens"][0]["protection"] == "normal"
    assert p["semantic_release"]["catalog_release_id"] == "release-1"
    unavailable = compose_assessment(SHA, evidence())["evidence"]["permissions"]
    assert unavailable["observed_token_count"] is None
    assert unavailable["resolved_count"] is None


@pytest.mark.parametrize(
    "change", ["case", "conflict", "release", "source", "declaration"]
)
def test_permission_semantics_fail_closed(change):
    e = permission_evidence()
    p = e["permissions"]
    if change == "case":
        p["observations"][0]["permission_string"] = "android.permission.internet"
    if change == "conflict":
        p["semantics"][0]["unresolved_conflict_count"] = 1
    if change == "release":
        p["releases"][0]["release_status"] = "DRAFT"
    if change == "source":
        p["semantics"][0]["source_status"] = "MISSING"
    if change == "declaration":
        p["semantics"][0]["declaration_revision_id"] = None
    assert (
        compose_assessment(SHA, e)["evidence"]["permissions"]["unresolved_count"] == 1
    )


def test_permission_historical_and_conditioned_interpretation():
    e = permission_evidence()
    e["permissions"]["semantics"][0]["lifecycle"] = "historical"
    p = compose_assessment(SHA, e)["evidence"]["permissions"]["tokens"][0]
    assert p["protection"] is None
    assert p["interpretation"]["authority_scope"] == "HISTORICAL_PLATFORM"
    e["permissions"]["semantics"][0].update(
        lifecycle="current", feature_dependency="telephony"
    )
    p = compose_assessment(SHA, e)["evidence"]["permissions"]["tokens"][0]
    assert p["feature_dependency"] == "telephony"
    assert p["interpretation"]["declaration_state"] == "CONDITIONED"


def test_retained_gaps_are_not_observations():
    e = evidence()
    e["permissions"]["retained"] = [
        {
            "bounded_result_id": 1,
            "sample_id": 1,
            "sha256": SHA,
            "report_sha256": SHA,
            "tokens": ["android.permission.INTERNET"],
        }
    ]
    p = compose_assessment(SHA, e)["evidence"]["permissions"]
    assert p["retained_tokens_missing_downstream"] == ["android.permission.INTERNET"]
    assert p["observed_token_count"] is None
    e["permissions"]["retained"][0]["report_sha256"] = OTHER
    with pytest.raises(ValueError):
        compose_assessment(SHA, e)


def test_scytale_exact_hash_version_and_provenance():
    e = evidence()
    assert (
        compose_assessment(SHA, e)["evidence"]["scytale"]["availability"]
        == "unavailable"
    )
    e["scytale"] = {
        "availability": "available",
        "registry": [
            {"apk_id": 1, "sha256": SHA, "version_code": 3, "version_name": "3.0"}
        ],
    }
    result = compose_assessment(SHA, e)
    assert result["artifact"]["version"]["value"]["code"] == 3
    assert result["evidence"]["scytale"]["evidence_refs"]
    e["scytale"]["registry"][0]["sha256"] = OTHER
    with pytest.raises(ValueError):
        compose_assessment(SHA, e)


def test_foreign_sample_rejected():
    e = evidence()
    e["mappings"] = [mapping()]
    e["mappings"][0]["sample_id"] = 9
    with pytest.raises(ValueError):
        compose_assessment(SHA, e)
    e["catalog"] = []
    with pytest.raises(ValueError):
        compose_assessment(SHA, e)


def test_error_unsupported_and_duplicate_identity_outcomes():
    e = evidence()
    e["errors"] = ["av_scan:OperationalError"]
    assert compose_assessment(SHA, e)["processing"]["status"] == "error"
    e = evidence()
    e["catalog"][0]["platform"] = "windows"
    assert compose_assessment(SHA, e)["processing"]["status"] == "unsupported_artifact"
    e = evidence()
    e["catalog"].append({**e["catalog"][0], "sample_id": 2})
    assert (
        compose_assessment(SHA, e)["processing"]["status"] == "complete_with_conflict"
    )


def test_provenance_and_order_determinism():
    e = permission_evidence()
    e["mappings"] = [mapping(), mapping(2)]
    result = compose_assessment(SHA, e)
    e["mappings"].reverse()
    assert result == compose_assessment(SHA, e)
    refs = result["provenance"]["references"]
    for f in list(result["assessment"].values()) + [
        result["artifact"][k] for k in ("platform", "format", "package_name", "version")
    ]:
        if f["value"] is not None:
            assert f["evidence_refs"]
        assert set(f["evidence_refs"]) <= refs.keys()
    assert result["provenance"]["evidence_digest"] == digest(ordered(e))
    assert result["provenance"]["code_version"].startswith("source-sha256:")
    assert json.loads(json.dumps(result)) == result


def test_frozen_checksum_and_copy_isolation():
    b = bundle(evidence())
    source = FrozenEvidenceSource(b)
    b["artifacts"][SHA]["catalog"] = []
    assert source.lookup(SHA)["catalog"]
    source.lookup(SHA)["catalog"].clear()
    assert source.lookup(SHA)["catalog"]
    with pytest.raises(ValueError):
        FrozenEvidenceSource(b)


def test_revision_replay_evidence_engine_and_reversion(tmp_path):
    store = AssessmentStore(tmp_path / "assessment.sqlite")
    e = evidence()
    service = AssessmentService(FrozenEvidenceSource(bundle(e)), store)
    first = service.assess(SHA, assessed_at_utc="2026-09-19T00:00:00+00:00")
    assert service.assess(SHA, assessed_at_utc="2026-09-20T00:00:00+00:00") == first
    e["mappings"] = [mapping()]
    second = AssessmentService(FrozenEvidenceSource(bundle(e)), store).assess(SHA)
    assert (
        second["revision"] == 2
        and second["previous_assessment_id"] == first["assessment_id"]
    )
    third = AssessmentService(
        FrozenEvidenceSource(bundle(e)), store, engine_version="v2"
    ).assess(SHA)
    assert third["revision"] == 3 and third["provenance"]["rule_id"] == "v2"
    fourth = service.assess(SHA)
    assert fourth["revision"] == 4 and fourth["assessment_id"] != first["assessment_id"]
    assert service.current(SHA) == fourth
    assert service.history(SHA)[0] == first
    assert service.history(OTHER) == [] and service.current(OTHER) is None


def test_store_constraints_indexes_and_immutability(tmp_path):
    store = AssessmentStore(tmp_path / "assessment.sqlite")
    first = store.append(
        compose_assessment(SHA, evidence()), assessed_at_utc="2026-09-19T00:00:00+00:00"
    )
    with store.connect() as conn:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert "assessment_sha_latest" in {
            r[1] for r in conn.execute("PRAGMA index_list(assessment_revision)")
        }
        assert conn.execute("PRAGMA foreign_key_list(assessment_revision)").fetchall()
        for sql in (
            "UPDATE assessment_revision SET revision=4",
            "DELETE FROM assessment_revision",
            "INSERT INTO assessment_revision SELECT * FROM assessment_revision",
        ):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(sql)
        for sha, rev, parent, payload in (
            (SHA, 3, first["assessment_id"], first),
            (OTHER, 1, None, {}),
            (OTHER, 2, first["assessment_id"], first),
        ):
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO assessment_revision VALUES (?,?,?,?,?,?,?)",
                    ("c" * 64, sha, rev, parent, "d" * 64, "time", json.dumps(payload)),
                )
    assert store.current(SHA) == first


def test_concurrent_identical_requests_create_one_revision(tmp_path):
    store = AssessmentStore(tmp_path / "assessment.sqlite")
    service = AssessmentService(FrozenEvidenceSource(bundle(evidence())), store)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.assess(SHA), range(8)))
    assert all(r == results[0] for r in results)
    assert len(service.history(SHA)) == 1


def test_cli_json_current_history_and_formatting(tmp_path, capsys):
    snapshot = tmp_path / "evidence.json"
    snapshot.write_text(json.dumps(bundle(evidence())))
    store = tmp_path / "assessment.sqlite"
    args = [SHA, "--store", str(store), "--json"]
    assert main(["assess", *args, "--snapshot", str(snapshot)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert main(["current", *args]) == 0
    assert json.loads(capsys.readouterr().out) == result
    assert main(["history", *args]) == 0
    assert json.loads(capsys.readouterr().out) == [result]
    display = format_assessment(result)
    assert "Family: Unknown [unresolved]" in display
    assert "Evidence / scytale: unavailable" in display
    assert "no ML" in display
    assert main(["current", OTHER, "--store", str(store), "--json"]) == 3
    assert json.loads(capsys.readouterr().out)["status"] == "not_assessed"
    assert main(["assess", "bad", "--store", str(store)]) == 2


def test_reader_requires_server_read_only_and_rejects_mutations():
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql):
            assert sql == "SELECT @@tx_read_only AS read_only"

        def fetchone(self):
            return {"read_only": connection.read_only}

    class Connection:
        read_only = 0

        def cursor(self):
            return Cursor()

    connection = Connection()
    with pytest.raises(ValueError):
        ReadOnlyEvidenceReader(connection)
    connection.read_only = 1
    reader = ReadOnlyEvidenceReader(connection)
    for sql in (
        "UPDATE x SET y=1",
        "SELECT 1; DELETE FROM x",
        "SELECT 1 INTO OUTFILE '/tmp/x'",
        "SELECT * FROM x FOR UPDATE",
        "SELECT SLEEP(10)",
    ):
        with pytest.raises(ValueError):
            reader.read("rejected", sql)


def test_retained_permission_extraction():
    assert retained_permission_tokens(
        '[{"android.permission.INTERNET": {"description":"ignored"}}, ["android.permission.CAMERA"]]'
    ) == ["android.permission.CAMERA", "android.permission.INTERNET"]
    assert retained_permission_tokens("malformed") == []


@pytest.mark.parametrize(
    "change", ["missing", "dangling", "probability", "selected_conflict", "timestamp"]
)
def test_store_rejects_invalid_contract(tmp_path, change):
    store = AssessmentStore(tmp_path / "assessment.sqlite")
    body = compose_assessment(SHA, evidence())
    timestamp = "2026-09-19T00:00:00Z"
    if change == "missing":
        body.pop("processing")
    if change == "dangling":
        body["assessment"]["type"]["evidence_refs"] = ["missing"]
    if change == "probability":
        body["confidence"]["model_probability"] = 0.9
    if change == "selected_conflict":
        body["assessment"]["type"]["state"] = "conflict"
    if change == "timestamp":
        timestamp = "2026-09-19T00:00:00"
    with pytest.raises(ValueError):
        store.append(body, assessed_at_utc=timestamp)
    assert store.current(SHA) is None


def test_cli_help_is_side_effect_free(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("Help must not initialize persistence")

    monkeypatch.setattr(AssessmentStore, "__init__", forbidden)
    with pytest.raises(SystemExit) as stopped:
        main(["--help"])
    assert stopped.value.code == 0
    assert "--snapshot" in capsys.readouterr().out


def test_foreign_key_independently_enforced(tmp_path):
    store = AssessmentStore(tmp_path / "assessment.sqlite")
    result = store.append(
        compose_assessment(SHA, evidence()), assessed_at_utc="2026-09-19T00:00:00Z"
    )
    # Bypass only the sequencing trigger in this disposable test to isolate the FK.
    with store.connect() as conn:
        conn.execute("DROP TRIGGER assessment_append_only")
        fake = {
            **result,
            "artifact": {**result["artifact"], "sha256": OTHER},
            "assessment_id": "c" * 64,
            "revision": 2,
            "previous_assessment_id": result["assessment_id"],
        }
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
            conn.execute(
                "INSERT INTO assessment_revision VALUES (?,?,?,?,?,?,?)",
                (
                    fake["assessment_id"],
                    OTHER,
                    2,
                    result["assessment_id"],
                    "d" * 64,
                    result["assessed_at_utc"],
                    json.dumps(fake),
                ),
            )


def test_av_missing_analysis_date_cannot_support_malware_rule():
    e = av_evidence()
    for group in ("av_scan", "av_verdict"):
        e[group][0]["vt_last_analysis_date"] = None
    assert (
        compose_assessment(SHA, e)["assessment"]["artifact_label"]["value"]
        == "ANDROID_APPLICATION"
    )


def test_family_dimension_identity_mismatch_rejected():
    e = evidence()
    e["mappings"] = [mapping()]
    e["mappings"][0]["family"]["family_id"] = 99
    with pytest.raises(ValueError, match="dimension"):
        compose_assessment(SHA, e)


@pytest.mark.parametrize(
    "kind,reviewed,expected",
    [
        (None, True, "supported"),
        ("legacy_single_source_capability", True, "conflict"),
        ("legacy_missing_alias_surface", True, "conflict"),
        ("family_identity_normalization", True, "conflict"),
        ("legacy_missing_alias_surface", False, "conflict"),
    ],
)
def test_v1_family_conflict_scope_preserves_explicit_contract(kind, reviewed, expected):
    """V1 blocks all open family cases; kind is not an adjudicated scope override."""
    e = evidence()
    e["mappings"] = [mapping()]
    e["families"] = [mapping()["family"]]
    if reviewed:
        e["authority"] = [{
            "authority_id": 10, "sample_id": 1, "is_active": 1,
            "review_status": "reviewed", "governed_family_id": 1,
            "governed_family_name": "Family 1", "governed_family_slug": "family-1",
        }]
    if kind:
        e["family_conflicts"] = [{
            "conflict_case_id": 20, "family_entity_id": 30, "legacy_family_id": 1,
            "conflict_kind": kind, "conflict_state": "open",
        }]
    body = compose_assessment(SHA, e)
    family = body["assessment"]["family"]
    assert family["state"] == expected
    if kind:
        assert family["value"] is None
        assert any("conflict_case_id" in r for r in family["evidence_refs"])
    if reviewed:
        assert any("authority_id" in r for r in family["evidence_refs"])


def test_reviewed_authority_does_not_hide_competing_exact_mappings():
    e = evidence()
    e["mappings"] = [mapping(1), mapping(2)]
    e["families"] = [m["family"] for m in e["mappings"]]
    e["authority"] = [{
        "authority_id": 10, "sample_id": 1, "is_active": 1,
        "review_status": "reviewed", "governed_family_id": 1,
        "governed_family_name": "Family 1", "governed_family_slug": "family-1",
    }]
    result = compose_assessment(SHA, e)
    assert result["assessment"]["family"]["state"] == "conflict"
    assert len(result["assessment"]["family"]["candidates"]) == 2


def test_static_context_and_future_pi_evidence_change_revision_without_rewriting(tmp_path):
    store = AssessmentStore(tmp_path / "lineage.sqlite")
    e = evidence()
    e["catalog"][0].update(platform="unknown", artifact_type=None)
    first = AssessmentService(FrozenEvidenceSource(bundle(e)), store).assess(SHA)
    e["catalog"][0].update(platform="android", artifact_type="apk")
    e["source_snapshots"] = {"static_baseline": {"sha256": SHA, "declared_count": 8}}
    service = AssessmentService(FrozenEvidenceSource(bundle(e)), store)
    second = service.assess(SHA)
    assert first["processing"]["status"] == "unsupported_artifact"
    assert second["revision"] == 2
    assert second["evidence"]["permissions"]["observed_token_count"] is None
    assert service.assess(SHA) == second
    e["permissions"] = permission_evidence()["permissions"]
    third = AssessmentService(FrozenEvidenceSource(bundle(e)), store).assess(SHA)
    assert third["revision"] == 3
    assert third["provenance"]["evidence_digest"] != second["provenance"]["evidence_digest"]
    assert service.history(SHA)[:2] == [first, second]
