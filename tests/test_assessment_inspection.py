"""Doctor distinguishes inspection limits from physical CHECK/trigger defects."""

from copy import deepcopy
from importlib.resources import files
import json
from unittest.mock import MagicMock

import mysql.connector
import pytest
from obsidiandroid.assessment import inspection, schema

REFERENCE = json.loads(
    files("obsidiandroid.assessment").joinpath("schema_contract_v1.json").read_text()
)["schema"]


def inspect(monkeypatch, actual, ddl_checks=None, trigger_error=None):
    monkeypatch.setattr(schema, "schema_snapshot", lambda _: actual)
    cur = MagicMock()
    cur.__enter__.return_value = cur
    state = {}

    def execute(sql):
        state["sql"] = sql
        if sql.startswith("SHOW CREATE TRIGGER") and trigger_error:
            raise mysql.connector.ProgrammingError(errno=trigger_error, msg="fixture")

    def fetchone():
        if state["sql"] == "SELECT DATABASE()":
            return ("fixture",)
        table = state["sql"].split("`")[1]
        checks = ddl_checks if ddl_checks is not None else REFERENCE["checks"]
        ddl = "\n".join(
            f"  CONSTRAINT `{r['CONSTRAINT_NAME']}` CHECK ({r['CHECK_CLAUSE']})"
            for r in checks
            if r["TABLE_NAME"] == table
        )
        return (table, ddl)

    cur.execute.side_effect = execute
    cur.fetchone.side_effect = fetchone
    conn = MagicMock()
    conn.cursor.return_value = cur
    return inspection.inspect_schema(conn)


def test_full_visibility_ready(monkeypatch):
    assert inspect(monkeypatch, deepcopy(REFERENCE))["status"] == "ready"


def test_hidden_checks_are_partial_not_invalid(monkeypatch):
    actual = deepcopy(REFERENCE)
    actual["checks"] = []
    result = inspect(monkeypatch, actual)
    assert result["status"] == "partial" and result["differences"] == []
    assert result["unverified"][0]["show_create_confirmed"]


@pytest.mark.parametrize("change", ["altered", "missing"])
@pytest.mark.parametrize("hidden", [True, False])
def test_real_check_defect_fails_even_with_hidden_metadata(monkeypatch, change, hidden):
    actual = deepcopy(REFERENCE)
    checks = deepcopy(REFERENCE["checks"])
    if change == "missing":
        checks.pop(0)
    else:
        checks[0]["CHECK_CLAUSE"] = "1 = 1"
    actual["checks"] = [] if hidden else checks
    result = inspect(monkeypatch, actual, checks)
    assert result["status"] == "drift"
    assert result["differences"][0]["section"] == "checks"


def test_other_defect_dominates_partial(monkeypatch):
    actual = deepcopy(REFERENCE)
    actual["checks"] = []
    actual["indexes"] = []
    assert inspect(monkeypatch, actual)["status"] == "drift"


def test_denied_trigger_metadata_is_partial(monkeypatch):
    actual = deepcopy(REFERENCE)
    actual["triggers"] = []
    assert inspect(monkeypatch, actual, trigger_error=1142)["status"] == "partial"


def test_absent_trigger_is_defect(monkeypatch):
    actual = deepcopy(REFERENCE)
    actual["triggers"] = []
    assert inspect(monkeypatch, actual, trigger_error=1360)["status"] == "drift"


def test_hidden_extra_check_is_not_accepted(monkeypatch):
    actual = deepcopy(REFERENCE)
    actual["checks"] = []
    checks = deepcopy(REFERENCE["checks"])
    checks.append(dict(checks[0], CONSTRAINT_NAME="unexpected_check"))
    assert inspect(monkeypatch, actual, checks)["status"] == "drift"


def test_fk_ddl_keeps_rules_and_cross_schema_identity():
    ddl = "  CONSTRAINT `fk` FOREIGN KEY (`a`,`b`) REFERENCES `other`.`parent` (`x`,`y`) ON DELETE CASCADE ON UPDATE SET NULL,"
    rows = inspection._foreign_keys(ddl, "child", "fixture")
    assert len(rows) == 2
    assert rows[0]["DELETE_RULE"] == "CASCADE" and rows[1]["UPDATE_RULE"] == "SET NULL"
    assert rows[0]["REFERENCED_TABLE_SCHEMA"] == "other"
    assert rows[1]["COLUMN_NAME"] == "b" and rows[1]["REFERENCED_COLUMN_NAME"] == "y"


def test_partial_cli_exit_code(monkeypatch, capsys):
    from obsidiandroid.assessment import doctor

    monkeypatch.setattr(
        doctor,
        "inspect_database",
        lambda *a, **k: {"status": "partial", "read_only": True},
    )
    assert (
        doctor.main(
            [
                "--database",
                "obsidiandroid_core_persistence_test_20260920",
                "--option-file",
                "unused",
                "--json",
            ]
        )
        == 3
    )
    assert json.loads(capsys.readouterr().out)["status"] == "partial"
