"""Regression coverage for bounded review, drift checks and failure diagnostics."""

from copy import deepcopy
from importlib.resources import files
import json
from pathlib import Path
import shutil

import mysql.connector
import pytest

from obsidiandroid.assessment import (
    AssessmentService,
    AssessmentStore,
    compose_assessment,
)
from obsidiandroid.assessment.mariadb_store import (
    MariaDBAssessmentStore,
)
from obsidiandroid.assessment import schema
from obsidiandroid.assessment.doctor import inspect_database, main as doctor_main
from obsidiandroid.assessment.migration import migrate
from obsidiandroid.assessment.revisions import compare_revisions
from obsidiandroid.cli.assessment import main
from obsidiandroid.core_migration.executor import (
    CoreMigrationError,
    split_sql_statements,
)
from test_operational_assessment import evidence, mapping, SHA
from test_assessment_mariadb import (
    DB,
    TIME,
    body,
    factory as factory,
    admin_factory as admin_factory,
    store as store,
    ev as ev,
)


def local_chain(tmp_path):
    store = AssessmentStore(tmp_path / "sidecar.sqlite")
    rows = []
    for i in range(4):
        e = evidence()
        e["mappings"] = [mapping(i + 1)]
        rows.append(
            store.append(
                compose_assessment(SHA, e, code_version="fixture"), assessed_at_utc=TIME
            )
        )
    return store, rows


def test_local_paging_by_id_and_read_only_cli(tmp_path, capsys):
    store, rows = local_chain(tmp_path)
    service = AssessmentService(None, store)
    first = service.history_page(SHA, limit=2)
    second = service.history_page(
        SHA, limit=2, after_revision=first["next_after_revision"]
    )
    assert first["records"] + second["records"] == rows
    assert second["next_after_revision"] is None
    assert service.by_id(rows[0]["assessment_id"]) == rows[0]
    assert service.history_page(SHA, after_revision=4)["records"] == []
    assert (
        main(["history", SHA, "--store", str(store.path), "--limit", "2", "--json"])
        == 0
    )
    assert json.loads(capsys.readouterr().out) == first
    assert (
        main(["by-id", rows[0]["assessment_id"], "--store", str(store.path), "--json"])
        == 0
    )
    assert json.loads(capsys.readouterr().out) == rows[0]
    assert (
        main(
            [
                "compare",
                rows[0]["assessment_id"],
                "--against",
                rows[1]["assessment_id"],
                "--store",
                str(store.path),
                "--json",
            ]
        )
        == 0
    )
    diff = json.loads(capsys.readouterr().out)
    assert diff["conclusions_changed"]
    assert "/assessment/family/value/name" in [c["path"] for c in diff["changes"]]
    assert any(
        c["path"] == "/assessment/family/value/name" and c["category"] == "assessment"
        for c in diff["changes"]
    )
    with pytest.raises(ValueError, match="evidence source"):
        service.assess(SHA)


def test_read_only_sqlite_never_creates_or_migrates(tmp_path, capsys):
    path = tmp_path / "missing" / "not-created.sqlite"
    assert main(["current", SHA, "--store", str(path)]) == 2
    capsys.readouterr()
    assert not path.parent.exists()
    writable, rows = local_chain(tmp_path)
    ro = AssessmentStore(writable.path, read_only=True)
    assert ro.current(SHA) == rows[-1]
    with pytest.raises(ValueError, match="Read-only"):
        ro.append({}, assessed_at_utc=TIME)


@pytest.mark.parametrize(
    "limit,cursor", [(0, 0), (201, 0), (True, 0), (1, -1), (1, True), (1, 2**63)]
)
def test_invalid_page_rejected_without_connection(limit, cursor):
    s = MariaDBAssessmentStore(
        lambda: pytest.fail("unexpected connection"), database=DB
    )
    with pytest.raises(ValueError):
        s.history_page(SHA, limit=limit, after_revision=cursor)


@pytest.mark.parametrize("action", ["current", "history", "by_id", "history_page"])
def test_invalid_identity_rejected_before_connection(action):
    s = MariaDBAssessmentStore(
        lambda: pytest.fail("unexpected connection"), database=DB
    )
    with pytest.raises(ValueError):
        getattr(s, action)("invalid")


def test_revision_diff_distinguishes_provenance_and_persistence(tmp_path):
    _, rows = local_chain(tmp_path)
    before = rows[0]
    after = deepcopy(before)
    after["revision"] = 2
    after["assessment_id"] = "f" * 64
    after["provenance"]["code_version"] = "reviewed-new-code"
    report = compare_revisions(before, after)
    assert not report["conclusions_changed"] and not report["same_record"]
    assert {c["category"] for c in report["changes"]} == {
        "revision_metadata",
        "engine_and_code",
    }
    assert compare_revisions(before, before)["same_record"]
    after["artifact"]["sha256"] = "b" * 64
    with pytest.raises(ValueError, match="same artifact"):
        compare_revisions(before, after)


def test_revision_diff_missing_null_and_escaped_paths(tmp_path):
    _, rows = local_chain(tmp_path)
    before = rows[0]
    after = deepcopy(before)
    after["evidence"]["fixture/path~"] = None
    report = compare_revisions(before, after)
    change = next(
        c for c in report["changes"] if c["path"].endswith("/fixture~1path~0")
    )
    assert not change["before_present"] and change["after_present"]
    assert change["before"] is None and change["after"] is None


class FakeCursor:
    def __init__(self):
        self.sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, sql, params=None):
        self.sql = sql

    def fetchone(self):
        if self.sql == "SELECT DATABASE()":
            return (DB,)
        if self.sql.startswith("SELECT artifact_sha256"):
            return (SHA,)
        return None


class BadCleanupConnection:
    autocommit = False

    def __init__(self, commit_error=None):
        self.commit_error = commit_error
        self.closed = False

    def cursor(self):
        return FakeCursor()

    def commit(self):
        if self.commit_error:
            raise self.commit_error

    def rollback(self):
        raise mysql.connector.OperationalError(errno=2013, msg="SECRET cleanup detail")

    def close(self):
        self.closed = True
        raise mysql.connector.OperationalError(errno=2013, msg="SECRET close detail")


def test_cleanup_does_not_mask_primary_error_or_expose_details(caplog):
    conn = BadCleanupConnection()
    s = MariaDBAssessmentStore(lambda: conn, database=DB)
    with pytest.raises(ValueError, match="primary failure"):
        with s.connect():
            raise ValueError("primary failure")
    assert conn.closed and "SECRET" not in caplog.text


def test_cleanup_does_not_turn_acknowledged_commit_into_failure(caplog):
    s = MariaDBAssessmentStore(BadCleanupConnection, database=DB)
    result = s.append(
        compose_assessment(SHA, evidence(), code_version="fixture"),
        assessed_at_utc=TIME,
    )
    assert result["revision"] == 1 and "SECRET" not in caplog.text


def test_cleanup_error_does_not_hide_deadlock_retry():
    first = BadCleanupConnection(
        mysql.connector.OperationalError(errno=1213, msg="deadlock")
    )
    second = BadCleanupConnection()
    connections = iter([first, second])
    s = MariaDBAssessmentStore(lambda: next(connections), database=DB)
    assert (
        s.append(
            compose_assessment(SHA, evidence(), code_version="fixture"),
            assessed_at_utc=TIME,
        )["revision"]
        == 1
    )
    assert first.closed and second.closed


@pytest.mark.parametrize(
    "section",
    ["objects", "columns", "indexes", "checks", "foreign_keys", "triggers", "views"],
)
def test_schema_checks_definitions_not_just_names(monkeypatch, section):
    reference = json.loads(
        files("obsidiandroid.assessment")
        .joinpath("schema_contract_v1.json")
        .read_text()
    )["schema"]
    observed = deepcopy(reference)
    observed[section][0]["synthetic_definition_change"] = "wrong"
    monkeypatch.setattr(schema, "schema_snapshot", lambda _: observed)
    report = schema.schema_report(None)
    assert report["status"] == "drift" and [
        d["section"] for d in report["differences"]
    ] == [section]
    with pytest.raises(CoreMigrationError, match=section):
        schema.validate_schema(None)


def test_sql_normalization_preserves_evidence_literals():
    assert schema.normalize_sql(
        "SELECT `one`.`x` FROM `one`.`t` WHERE x='one.X'", "one"
    ) == schema.normalize_sql("select `two`.`x` from `two`.`t` where x='one.X'", "two")
    assert schema.normalize_sql("x='Family A'", "one") != schema.normalize_sql(
        "x='family a'", "one"
    )


def test_migration_checksum_and_receipt_fail_before_connect(tmp_path):
    migrations = tmp_path / "migrations"
    shutil.copytree("database/core_migrations", migrations)
    altered = next(migrations.glob("0006*"))
    altered.write_text(altered.read_text() + "-- changed\n")
    with pytest.raises(ValueError, match="checksum mismatch"):
        migrate(
            database=DB,
            connection_factory=lambda _: pytest.fail("connected"),
            migrations_dir=migrations,
            receipt_path=tmp_path / "receipt.json",
            apply=True,
        )
    receipt = tmp_path / "already.json"
    receipt.write_text("preserved")
    with pytest.raises(CoreMigrationError, match="already exists"):
        migrate(
            database=DB,
            connection_factory=lambda _: pytest.fail("connected"),
            migrations_dir=Path("database/core_migrations"),
            receipt_path=receipt,
        )
    assert receipt.read_text() == "preserved"


def test_live_paging_and_doctor(admin_factory, store, ev):
    rows = [
        store.append(body(ev, engine_version=f"page-{i}"), assessed_at_utc=TIME)
        for i in range(5)
    ]
    first = store.history_page(ev["sha256"], limit=2)
    second = store.history_page(
        ev["sha256"], limit=2, after_revision=first["next_after_revision"]
    )
    third = store.history_page(
        ev["sha256"], limit=2, after_revision=second["next_after_revision"]
    )
    assert first["records"] + second["records"] + third["records"] == rows
    assert third["next_after_revision"] is None
    reader = MariaDBAssessmentStore(admin_factory, database=DB)
    report = inspect_database(reader, sha256=ev["sha256"])
    assert report["status"] == "ready" and report["read_only"]
    assert (
        report["artifact"]["checked_revisions"] == 5 and report["artifact"]["complete"]
    )
    limited = inspect_database(reader, sha256=ev["sha256"], max_revisions=2)
    assert limited["status"] == "partial" and not limited["artifact"]["complete"]
    assert store.history(ev["sha256"]) == rows


def test_live_doctor_uses_read_only_and_sanitizes_errors(
    admin_factory, ev, capsys, monkeypatch
):
    from obsidiandroid.assessment import doctor

    original = doctor.schema_report

    def assert_read_only(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT @@tx_read_only")
            assert cur.fetchone()[0] == 1
            with pytest.raises(mysql.connector.Error) as error:
                cur.execute(
                    "INSERT INTO core_assessment_artifact VALUES (%s)", (ev["sha256"],)
                )
            assert error.value.errno == 1792
        return original(conn)

    monkeypatch.setattr(doctor, "schema_report", assert_read_only)
    report = inspect_database(
        MariaDBAssessmentStore(admin_factory, database=DB), sha256=ev["sha256"]
    )
    assert (
        report["status"] == "ready" and report["artifact"]["status"] == "not_assessed"
    )
    monkeypatch.setattr(
        doctor,
        "inspect_database",
        lambda *a, **kw: (_ for _ in ()).throw(
            mysql.connector.ProgrammingError(errno=1045, msg="SECRET password")
        ),
    )
    assert doctor_main(["--database", DB, "--option-file", "unused", "--json"]) == 2
    result = capsys.readouterr().out
    assert "SECRET" not in result and json.loads(result)["errno"] == 1045


@pytest.mark.parametrize("case", ["trigger", "index", "check", "view", "collation"])
def test_live_same_name_drift_rejected_without_repair(admin_factory, tmp_path, case):
    statements = split_sql_statements(
        Path("database/core_migrations/0006_operational_assessment_v1.sql").read_text()
    )
    if case == "trigger":
        change = "CREATE OR REPLACE TRIGGER core_assessment_no_delete BEFORE DELETE ON core_assessment_revision FOR EACH ROW SET @assessment_fixture=1"
        restore = next(
            s
            for s in statements
            if s.startswith("CREATE TRIGGER core_assessment_no_delete")
        ).replace("CREATE TRIGGER", "CREATE OR REPLACE TRIGGER", 1)
    elif case == "index":
        change = "ALTER TABLE core_assessment_revision DROP INDEX ix_assessment_family, ADD INDEX ix_assessment_family (type_id)"
        restore = "ALTER TABLE core_assessment_revision DROP INDEX ix_assessment_family, ADD INDEX ix_assessment_family (family_id)"
    elif case == "check":
        change = "ALTER TABLE core_assessment_revision DROP CONSTRAINT chk_assessment_id, ADD CONSTRAINT chk_assessment_id CHECK (assessment_id IS NOT NULL)"
        restore = "ALTER TABLE core_assessment_revision DROP CONSTRAINT chk_assessment_id, ADD CONSTRAINT chk_assessment_id CHECK (assessment_id REGEXP BINARY '^[0-9a-f]{64}$')"
    elif case == "collation":
        change = "ALTER TABLE core_assessment_revision MODIFY processing_status VARCHAR(40) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci GENERATED ALWAYS AS (JSON_UNQUOTE(JSON_EXTRACT(result_json,'$.processing.status'))) STORED"
        restore = change
    else:
        change = "CREATE OR REPLACE SQL SECURITY INVOKER VIEW v_core_assessment_current AS SELECT * FROM core_assessment_revision"
        restore = next(
            s for s in statements if s.startswith("CREATE SQL SECURITY INVOKER VIEW")
        ).replace("CREATE SQL", "CREATE OR REPLACE SQL", 1)
    with admin_factory() as conn, conn.cursor() as cur:
        if case == "collation":
            cur.execute(
                "SELECT DEFAULT_COLLATION_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=DATABASE()"
            )
            collation = cur.fetchone()[0]
            assert collation in {"utf8mb4_bin", "utf8mb4_uca1400_ai_ci"}
            restore = change.replace("utf8mb4_unicode_ci", collation)
        try:
            cur.execute(change)
            with pytest.raises(CoreMigrationError, match="drift"):
                migrate(
                    database=DB,
                    connection_factory=admin_factory,
                    migrations_dir=Path("database/core_migrations"),
                    receipt_path=tmp_path / "drift.json",
                )
            # Detection must leave the mismatched definition in place, not repair it.
            assert schema.schema_report(conn)["status"] == "drift"
        finally:
            cur.execute(restore)
        assert schema.schema_report(conn)["status"] == "ready"


def test_failed_postmigration_validation_is_recorded(tmp_path, monkeypatch):
    from obsidiandroid.assessment import migration
    from obsidiandroid.core_migration.migration_checksums import MIGRATION_CHECKSUMS

    class Cursor(FakeCursor):
        def fetchall(self):
            return [
                (v, MIGRATION_CHECKSUMS[v], "applied") for v in ("0001", "0002", "0003")
            ]

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    receipt = tmp_path / "receipt.json"

    def apply(**kw):
        result = {"status": "applied", "applied": ["0006"], "skipped": []}
        receipt.write_text(json.dumps(result))
        return result

    monkeypatch.setattr(migration, "apply_migrations", apply)
    monkeypatch.setattr(
        migration,
        "validate_schema",
        lambda _: (_ for _ in ()).throw(CoreMigrationError("drift")),
    )
    with pytest.raises(CoreMigrationError, match="drift"):
        migrate(
            database=DB,
            connection_factory=lambda _: Connection(),
            migrations_dir=Path("database/core_migrations"),
            receipt_path=receipt,
            apply=True,
        )
    result = json.loads(receipt.read_text())
    assert (
        result["status"] == "validation_failed"
        and result["partial_ddl_review_required"]
    )
    assert result["applied"] == ["0006"]


def test_migration_cli_does_not_echo_connector_secret(monkeypatch, capsys):
    from obsidiandroid.assessment import migration

    monkeypatch.setattr(
        migration,
        "migrate",
        lambda **kw: (_ for _ in ()).throw(
            mysql.connector.OperationalError(errno=1045, msg="SECRET password")
        ),
    )
    assert (
        migration.main(
            ["--database", DB, "--option-file", "unused", "--receipt", "unused"]
        )
        == 2
    )
    output = capsys.readouterr().err
    assert "SECRET" not in output and "1045" in output


def test_schema_normalization_does_not_hide_case_sensitive_table_drift():
    assert schema.normalize_sql(
        "SELECT * FROM `Current`", "db"
    ) != schema.normalize_sql("SELECT * FROM `current`", "db")
    assert schema.normalize_sql("SELECT * FROM Current", "db") != schema.normalize_sql(
        "SELECT * FROM current", "db"
    )


@pytest.mark.parametrize(
    "suffix,valid",
    [("_collation", True), ("_run2", True), ("_bad;sql", False), ("_../prod", False)],
)
def test_named_disposable_variants_remain_bounded(suffix, valid):
    def factory():
        pytest.fail("constructor must not connect")

    name = "obsidiandroid_core_persistence_test_20260920" + suffix
    if valid:
        MariaDBAssessmentStore(factory, database=name)
    else:
        with pytest.raises(ValueError):
            MariaDBAssessmentStore(factory, database=name)


@pytest.mark.parametrize("fixture_name", ["factory", "admin_factory"])
def test_live_fixture_connection_rejects_production_before_connect(
    monkeypatch, fixture_name
):
    import test_assessment_mariadb as fixtures

    monkeypatch.setenv("OBSIDIAN_ASSESSMENT_TEST_OPTION_FILE", "unused")
    monkeypatch.setenv("OBSIDIAN_ASSESSMENT_TEST_ADMIN_OPTION_FILE", "unused")
    monkeypatch.setattr(fixtures, "DB", "obsidiandroid_core_prod")
    monkeypatch.setattr(
        mysql.connector, "connect", lambda **kw: pytest.fail("unsafe connection")
    )
    with pytest.raises(CoreMigrationError):
        getattr(fixtures, fixture_name).__wrapped__()


def test_doctor_detects_empty_artifact_without_repair(admin_factory, ev):
    sha = ev["sha256"]
    with admin_factory() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO core_assessment_artifact VALUES (%s)", (sha,))
        conn.commit()
        try:
            result = inspect_database(
                MariaDBAssessmentStore(admin_factory, database=DB), sha256=sha
            )
            assert result["status"] == "failed"
            assert {"reason": "artifact/revision mismatch"} in result["artifact"][
                "problems"
            ]
            cur.execute(
                "SELECT COUNT(*) FROM core_assessment_artifact WHERE artifact_sha256=%s",
                (sha,),
            )
            assert cur.fetchone()[0] == 1  # doctor reported; did not repair
        finally:
            cur.execute(
                "DELETE FROM core_assessment_artifact WHERE artifact_sha256=%s", (sha,)
            )
            conn.commit()
