"""Explicit opt-in MariaDB contract tests; retain disposable evidence for inspection."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
from threading import Barrier, local
import uuid

import mysql.connector
import pytest

from obsidiandroid.assessment import (
    AssessmentService,
    FrozenEvidenceSource,
    compose_assessment,
)
from obsidiandroid.assessment.composition import canonical_json, digest
from obsidiandroid.assessment.mariadb_store import (
    MariaDBAssessmentStore,
    AssessmentPersistenceError,
)
from obsidiandroid.assessment.migration import migrate, validate_schema
from obsidiandroid.cli.assessment import main
from obsidiandroid.core_migration.executor import (
    CoreMigrationError,
    apply_migrations,
    split_sql_statements,
    validate_target_name,
)
from test_operational_assessment import mapping, permission_evidence, bundle

DB = os.environ.get(
    "OBSIDIAN_ASSESSMENT_TEST_DATABASE", "obsidiandroid_core_persistence_test_20260919"
)
TIME = "2026-09-20T00:00:00+00:00"


def test_production_rejected_before_connect():
    with pytest.raises(ValueError):
        MariaDBAssessmentStore(
            lambda: pytest.fail("connected"), database="obsidiandroid_core_prod"
        )


def test_explicit_migration_selection_and_trigger_parser(tmp_path):
    receipt = apply_migrations(
        target_database=DB,
        migrations_dir=Path("database/core_migrations"),
        selected_versions=("0006",),
    )
    assert [m["version"] for m in receipt["migrations"]] == ["0006"]
    statements = split_sql_statements(
        Path("database/core_migrations/0006_operational_assessment_v1.sql").read_text()
    )
    assert len(statements) == 6
    assert "DECLARE last_revision" in statements[-1]
    assert (
        len(
            split_sql_statements(
                "DELIMITER $$\nSELECT 'x$$y';$$\nDELIMITER ;\nSELECT 2;"
            )
        )
        == 2
    )
    with pytest.raises(CoreMigrationError):
        apply_migrations(
            target_database=DB,
            migrations_dir=Path("database/core_migrations"),
            selected_versions=("0099",),
        )


@pytest.fixture
def factory():
    option = os.environ.get("OBSIDIAN_ASSESSMENT_TEST_OPTION_FILE")
    if not option:
        pytest.skip("explicit disposable MariaDB option file required")
    validate_target_name(DB)

    def connect():
        return mysql.connector.connect(
            option_files=option, database=DB, autocommit=False
        )

    return connect


@pytest.fixture
def store(factory):
    return MariaDBAssessmentStore(factory, database=DB)


@pytest.fixture
def ev():
    value = permission_evidence()
    sha = digest({"test_uuid": str(uuid.uuid4())})
    value["sha256"] = value["catalog"][0]["sha256"] = sha
    return value


def body(ev, **kw):
    return compose_assessment(
        ev["sha256"], ev, code_version="disposable-fixture-v1", **kw
    )


@pytest.mark.parametrize(
    "state,mappings",
    [
        ("supported", [mapping()]),
        ("unresolved", []),
        ("conflict", [mapping(), mapping(2)]),
    ],
)
def test_states_provenance_service_json(store, ev, state, mappings):
    ev["mappings"] = mappings
    service = AssessmentService(
        FrozenEvidenceSource(bundle(ev)), store, code_version="fixture-v1"
    )
    r = service.assess(ev["sha256"], assessed_at_utc=TIME)
    assert r["assessment"]["family"]["state"] == state
    assert r["assessment"]["artifact_label"]["state"] == "supported"
    assert r["assessment"]["type"]["state"] == "supported"
    assert r == service.current(ev["sha256"]) == store.by_id(r["assessment_id"])
    assert service.history(ev["sha256"]) == [r]
    assert json.loads(canonical_json(r)) == r
    assert r["provenance"]["references"]


def test_idempotency_and_real_revision_inputs(store, ev):
    b = body(ev)
    first = store.append(b, assessed_at_utc=TIME)
    assert store.append(b, assessed_at_utc="2027-01-01T00:00:00+00:00") == first
    variants = []
    ev["catalog"][0]["package_name"] = "fixture.changed"
    variants.append(body(ev))
    ev["permissions"]["releases"][0]["catalog_release_id"] = "disposable-release-2"
    ev["permissions"]["semantics"][0]["catalog_release_id"] = "disposable-release-2"
    variants.append(body(ev))
    ev["mappings"] = [mapping()]
    variants.append(body(ev))
    variants.append(body(ev, engine_version="disposable-engine-v2"))
    variants.append(b)  # Returning to earlier evidence is a new event in history.
    previous = first
    for i, candidate in enumerate(variants, 2):
        current = store.append(candidate, assessed_at_utc=TIME)
        assert (
            current["revision"] == i
            and current["previous_assessment_id"] == previous["assessment_id"]
        )
        previous = current
    history = store.history(ev["sha256"])
    assert len(history) == 6 and history[0] == first


@pytest.mark.parametrize("fresh", [True, False])
@pytest.mark.parametrize(
    "stage",
    [
        "after_artifact_lock",
        "after_fields_and_provenance_serialized",
        "after_revision_insert",
        "before_commit",
    ],
)
def test_rollback_every_stage(factory, store, ev, stage, fresh):
    sha = ev["sha256"]
    old = None if fresh else store.append(body(ev), assessed_at_utc=TIME)

    def fail(at):
        if at == stage:
            raise RuntimeError("injected " + stage)

    failing = MariaDBAssessmentStore(factory, database=DB, failure_hook=fail)
    with pytest.raises(RuntimeError, match="injected"):
        failing.append(body(ev, engine_version="changed"), assessed_at_utc=TIME)
    assert store.current(sha) == old
    assert len(store.history(sha)) == (0 if fresh else 1)
    with factory() as c, c.cursor() as q:
        q.execute(
            "SELECT COUNT(*) FROM core_assessment_artifact WHERE artifact_sha256=%s",
            (sha,),
        )
        assert q.fetchone()[0] == (0 if fresh else 1)


@pytest.mark.parametrize("different", [False, True])
@pytest.mark.parametrize("existing", [False, True])
def test_concurrent_same_sha(store, ev, different, existing):
    if existing:
        store.append(body(ev), assessed_at_utc=TIME)
    gate = Barrier(8)

    def work(i):
        b = body(ev, engine_version=f"candidate-{i}" if different else "identical")
        gate.wait(timeout=10)
        return store.append(b, assessed_at_utc=TIME)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(work, range(8)))
    history = store.history(ev["sha256"])
    expected = (8 if different else 1) + int(existing)
    assert len(history) == expected
    assert len({r["assessment_id"] for r in results}) == (8 if different else 1)
    assert [r["revision"] for r in history] == list(range(1, expected + 1))
    assert all(
        r["previous_assessment_id"] == history[i - 1]["assessment_id"]
        for i, r in enumerate(history)
        if i
    )
    assert store.current(ev["sha256"]) == history[-1]


def test_real_deadlock_retries_fresh_transaction(factory, ev):
    # Two transactions hold opposite artifact locks. Both request the other;
    # MariaDB chooses a real deadlock victim. The adapter retries that victim.
    other = deepcopy(ev)
    other["sha256"] = other["catalog"][0]["sha256"] = digest(str(uuid.uuid4()))
    pair = [ev, other]
    shas = [e["sha256"] for e in pair]
    with factory() as c, c.cursor() as q:
        for sha in shas:
            q.execute("INSERT INTO core_assessment_artifact VALUES (%s)", (sha,))
        c.commit()
    gate = Barrier(2)
    tls = local()
    attempts = [0, 0]

    def work(i):
        def connect():
            tls.conn = factory()
            attempts[i] += 1
            return tls.conn

        def hook(stage):
            if stage == "after_artifact_lock" and attempts[i] == 1:
                gate.wait(timeout=10)
                with tls.conn.cursor() as q:
                    q.execute(
                        "SELECT artifact_sha256 FROM core_assessment_artifact WHERE artifact_sha256=%s FOR UPDATE",
                        (shas[1 - i],),
                    )
                    q.fetchone()

        s = MariaDBAssessmentStore(connect, database=DB, failure_hook=hook)
        return s.append(body(pair[i]), assessed_at_utc=TIME)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(work, range(2)))
    assert sorted(attempts) == [1, 2]
    assert [r["revision"] for r in results] == [1, 1]


@pytest.mark.parametrize("errno", [1205, 1213])
def test_retry_exhaustion_rolls_back(factory, store, ev, errno):
    hits = []

    def hook(stage):
        if stage == "after_revision_insert":
            hits.append(stage)
            raise mysql.connector.OperationalError(
                errno=errno, msg="controlled transaction error"
            )

    bad = MariaDBAssessmentStore(factory, database=DB, max_retries=2, failure_hook=hook)
    with pytest.raises(AssessmentPersistenceError):
        bad.append(body(ev), assessed_at_utc=TIME)
    assert len(hits) == 3 and store.current(ev["sha256"]) is None


def test_invalid_unknown_and_wrong_connection(factory, store, ev):
    for sha in ["a", "g" * 64, "a" * 64 + "\n"]:
        with pytest.raises(ValueError):
            store.current(sha)
    assert store.current(ev["sha256"]) is None
    ev["catalog"] = []
    ev["permissions"] = {"availability": "unavailable"}
    ev["lookup_status"] = "not_found"
    r = store.append(body(ev), assessed_at_utc=TIME)
    assert r["processing"]["status"] == "insufficient_evidence"
    wrong = MariaDBAssessmentStore(
        factory, database="obsidiandroid_core_persistence_test_20000101"
    )
    with pytest.raises(ValueError, match="unexpected database"):
        wrong.current(ev["sha256"])


def test_cli_assess_current_history(factory, store, ev, tmp_path, capsys):
    snapshot = tmp_path / "evidence.json"
    snapshot.write_text(json.dumps(bundle(ev)))
    opts = [
        "--database",
        DB,
        "--db-option-file",
        os.environ["OBSIDIAN_ASSESSMENT_TEST_OPTION_FILE"],
        "--json",
    ]
    assert (
        main(
            [
                "assess",
                ev["sha256"],
                *opts,
                "--snapshot",
                str(snapshot),
                "--code-version",
                "fixture-cli",
            ]
        )
        == 0
    )
    generated = json.loads(capsys.readouterr().out)
    assert main(["current", ev["sha256"], *opts]) == 0
    assert json.loads(capsys.readouterr().out) == generated
    assert main(["history", ev["sha256"], *opts]) == 0
    assert json.loads(capsys.readouterr().out) == [generated]


def test_runtime_grants_no_history_mutation_or_ddl(factory, store, ev):
    r = store.append(body(ev), assessed_at_utc=TIME)
    with factory() as c, c.cursor() as q:
        for sql in [
            "UPDATE core_assessment_revision SET revision=99 WHERE assessment_id=%s",
            "DELETE FROM core_assessment_revision WHERE assessment_id=%s",
        ]:
            with pytest.raises(mysql.connector.Error) as error:
                q.execute(sql, (r["assessment_id"],))
            assert error.value.errno == 1142
        with pytest.raises(mysql.connector.Error):
            q.execute("CREATE TABLE forbidden_assessment_table (id INT)")
        q.execute(
            "SELECT COUNT(*) FROM information_schema.SCHEMA_PRIVILEGES WHERE TABLE_SCHEMA='obsidiandroid_core_prod'"
        )
        assert q.fetchone()[0] == 0


def test_no_retry_unknown_commit_outcome(factory, store, ev):
    hits = []

    def hook(stage):
        if stage == "before_commit":
            hits.append(stage)
            raise mysql.connector.OperationalError(
                errno=2013, msg="simulated disconnect"
            )

    with pytest.raises(AssessmentPersistenceError):
        MariaDBAssessmentStore(factory, database=DB, failure_hook=hook).append(
            body(ev), assessed_at_utc=TIME
        )
    assert len(hits) == 1 and store.current(ev["sha256"]) is None


@pytest.fixture
def admin_factory():
    option = os.environ.get("OBSIDIAN_ASSESSMENT_TEST_ADMIN_OPTION_FILE")
    if not option:
        pytest.skip("explicit disposable admin option file required")
    validate_target_name(DB)
    return lambda database=DB: mysql.connector.connect(
        option_files=option, database=database, autocommit=False
    )


def test_migration_rerun_and_schema(admin_factory, tmp_path):
    result = migrate(
        database=DB,
        connection_factory=admin_factory,
        migrations_dir=Path("database/core_migrations"),
        receipt_path=tmp_path / "rerun.json",
        apply=True,
    )
    assert result["applied"] == [] and result["skipped"] == ["0006"]
    with admin_factory() as c:
        validate_schema(c)
        with c.cursor() as q:
            q.execute(
                "SELECT migration_version FROM core_schema_migration ORDER BY migration_version"
            )
            assert [r[0] for r in q.fetchall()] == ["0001", "0002", "0003", "0006"]


@pytest.mark.parametrize(
    "mutation",
    [
        "update",
        "delete",
        "gap",
        "wrong_parent",
        "json_identity",
        "missing_identity",
        "invalid_sha",
    ],
)
def test_database_enforces_history_and_identity(admin_factory, store, ev, mutation):
    first = store.append(body(ev), assessed_at_utc=TIME)
    sha = ev["sha256"]
    with admin_factory() as c, c.cursor() as q:
        with pytest.raises(mysql.connector.Error):
            if mutation == "update":
                q.execute(
                    "UPDATE core_assessment_revision SET revision=99 WHERE artifact_sha256=%s",
                    (sha,),
                )
            elif mutation == "delete":
                q.execute(
                    "DELETE FROM core_assessment_revision WHERE artifact_sha256=%s",
                    (sha,),
                )
            elif mutation == "invalid_sha":
                q.execute(
                    "INSERT INTO core_assessment_artifact VALUES (%s)", ("G" * 64,)
                )
            else:
                result = dict(
                    first,
                    assessment_id=digest(str(uuid.uuid4())),
                    revision=2,
                    previous_assessment_id=first["assessment_id"],
                )
                rev = 2
                previous = first["assessment_id"]
                if mutation == "gap":
                    rev = result["revision"] = 4
                if mutation == "wrong_parent":
                    previous = result["previous_assessment_id"] = "0" * 64
                if mutation == "json_identity":
                    result["artifact"] = dict(result["artifact"], sha256="0" * 64)
                if mutation == "missing_identity":
                    result.pop("assessment_id")
                q.execute(
                    "INSERT INTO core_assessment_revision (assessment_id,artifact_sha256,revision,previous_assessment_id,input_digest,assessed_at_utc,result_json) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (
                        digest(str(uuid.uuid4()))
                        if mutation == "missing_identity"
                        else result["assessment_id"],
                        sha,
                        rev,
                        previous,
                        digest(body(ev)),
                        TIME,
                        canonical_json(result),
                    ),
                )
        c.rollback()
    assert store.history(sha) == [first]


@pytest.mark.parametrize(
    "versions,valid",
    [
        (["0001", "0002", "0003", "0006"], True),
        (["0001", "0002", "0003", "0004", "0005", "0006"], True),
        (["0001", "0002", "0006"], False),
        (["0001", "0002", "0003", "0005", "0006"], False),
        (["0001", "0002", "0003", "0007"], False),
    ],
)
def test_independent_assessment_migration_keeps_upgrade_contract(versions, valid):
    from obsidiandroid.core_migration.migration_checksums import (
        validate_applied_version_order,
    )

    if valid:
        validate_applied_version_order(versions)
    else:
        with pytest.raises(ValueError):
            validate_applied_version_order(versions)


def test_current_is_latest_attempt_even_error(store, ev):
    old = store.append(body(ev), assessed_at_utc=TIME)
    ev["errors"] = [{"source": "fixture", "error": "unavailable"}]
    result = store.append(body(ev), assessed_at_utc=TIME)
    assert result["processing"]["status"] == "error"
    assert store.current(ev["sha256"]) == result
    assert store.history(ev["sha256"])[0] == old
