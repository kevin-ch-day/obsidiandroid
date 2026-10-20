from __future__ import annotations

import pandas as pd
import pytest
import sqlite3

import scripts.diagnostics.label_authority_schema_readiness as readiness


@pytest.fixture
def ready_schema(monkeypatch) -> None:
    monkeypatch.setattr(
        readiness,
        "_fetch_columns",
        lambda: pd.DataFrame(
            [
                {"table_name": "malware_sample_catalog", "column_name": "sample_id"},
                {"table_name": "malware_sample_catalog", "column_name": "sha256"},
                {"table_name": "malware_sample_catalog", "column_name": "sample_label"},
                {"table_name": "malware_sample_catalog", "column_name": "family_label"},
                {"table_name": "malware_sample_catalog", "column_name": "classification_primary"},
                {"table_name": "malware_sample_catalog", "column_name": "classification_subtype"},
                {"table_name": "malware_sample_catalog", "column_name": "vt_first_seen_itw_date"},
                {"table_name": "malware_sample_catalog", "column_name": "vt_first_submission_at_utc"},
                {"table_name": "android_malware_family", "column_name": "family_id"},
                {"table_name": "android_malware_family", "column_name": "family_slug"},
                {"table_name": "android_malware_family", "column_name": "family_name"},
                {"table_name": "android_malware_family", "column_name": "primary_type_id"},
                {"table_name": "android_malware_family", "column_name": "is_active"},
                {"table_name": "android_malware_type", "column_name": "type_id"},
                {"table_name": "android_malware_type", "column_name": "type_slug"},
                {"table_name": "v_android_apk_family_resolved", "column_name": "sample_id"},
                {"table_name": "v_android_apk_family_resolved", "column_name": "resolved_family_lc"},
                {
                    "table_name": "virustotal_sample_vendor_engine_verdicts",
                    "column_name": "sample_id",
                },
                {
                    "table_name": "virustotal_sample_vendor_engine_verdicts",
                    "column_name": "updated_at",
                },
                *[
                    {
                        "table_name": "virustotal_sample_vendor_engine_verdicts",
                        "column_name": column_name,
                    }
                    for column_name in readiness.CORE_VENDOR_COLUMNS
                ],
                {"table_name": "virustotal_vendor_engines", "column_name": "vendor_key"},
                {"table_name": "virustotal_vendor_engines", "column_name": "is_engine_active"},
                {"table_name": "virustotal_vendor_engines", "column_name": "is_trusted_vendor"},
                {
                    "table_name": "v_android_sample_family_type_authority",
                    "column_name": "sample_id",
                },
                {
                    "table_name": "v_android_sample_family_type_authority",
                    "column_name": "resolved_family_lc",
                },
                {
                    "table_name": "v_android_sample_family_type_authority",
                    "column_name": "family_slug",
                },
                {
                    "table_name": "v_android_sample_family_type_authority",
                    "column_name": "type_slug",
                },
                {
                    "table_name": "v_android_sample_family_type_authority",
                    "column_name": "authority_bucket",
                },
                {
                    "table_name": "v_android_sample_family_type_authority",
                    "column_name": "authority_gap_reason",
                },
                {
                    "table_name": "v_android_sample_family_type_authority",
                    "column_name": "raw_vs_authority_status",
                },
                {
                    "table_name": "v_android_missing_resolution_triage",
                    "column_name": "sample_id",
                },
                {
                    "table_name": "v_android_missing_resolution_triage",
                    "column_name": "authority_bucket",
                },
                {
                    "table_name": "v_android_missing_resolution_triage",
                    "column_name": "package_cluster_key",
                },
                {
                    "table_name": "v_android_missing_resolution_triage",
                    "column_name": "package_cluster_size",
                },
                {
                    "table_name": "v_android_missing_resolution_triage",
                    "column_name": "review_lane",
                },
                {
                    "table_name": "v_android_missing_resolution_triage",
                    "column_name": "recommended_action",
                },
                {
                    "table_name": "v_vt_false_positive_review_candidates_effective",
                    "column_name": "sample_id",
                },
                {
                    "table_name": "v_vt_false_positive_review_candidates_effective",
                    "column_name": "sample_label",
                },
                {
                    "table_name": "v_vt_false_positive_review_candidates_triage",
                    "column_name": "sample_id",
                },
                {
                    "table_name": "v_vt_false_positive_review_candidates_triage",
                    "column_name": "sample_label",
                },
                {
                    "table_name": "v_vt_false_positive_review_candidates_triage",
                    "column_name": "global_policy_bucket",
                },
                {
                    "table_name": "v_vt_false_positive_review_candidates_triage",
                    "column_name": "review_lane",
                },
                {
                    "table_name": "v_vt_false_positive_review_candidates_triage",
                    "column_name": "recommended_triage_action",
                },
                {
                    "table_name": "vendor_label_generic_token_fact",
                    "column_name": "normalized_token",
                },
                {
                    "table_name": "vendor_label_generic_token_fact",
                    "column_name": "token_kind",
                },
                {
                    "table_name": "vendor_label_generic_token_fact",
                    "column_name": "is_active",
                },
            ]
        ),
    )
    monkeypatch.setattr(
        readiness,
        "_fetch_objects",
        lambda: pd.DataFrame(
            [
                {"table_name": "malware_sample_catalog", "table_type": "BASE TABLE"},
                {"table_name": "android_malware_family", "table_type": "BASE TABLE"},
                {"table_name": "android_malware_type", "table_type": "BASE TABLE"},
                {"table_name": "v_android_apk_family_resolved", "table_type": "VIEW"},
                {"table_name": "virustotal_sample_vendor_engine_verdicts", "table_type": "BASE TABLE"},
                {"table_name": "virustotal_vendor_engines", "table_type": "BASE TABLE"},
                {"table_name": "v_android_sample_family_type_authority", "table_type": "VIEW"},
                {"table_name": "v_android_missing_resolution_triage", "table_type": "VIEW"},
                {
                    "table_name": "v_vt_false_positive_review_candidates_effective",
                    "table_type": "VIEW",
                },
                {
                    "table_name": "v_vt_false_positive_review_candidates_triage",
                    "table_type": "VIEW",
                },
                {"table_name": "vendor_label_generic_token_fact", "table_type": "BASE TABLE"},
            ]
        ),
    )
    monkeypatch.setattr(
        readiness,
        "_estimate_seedable_vendor_rows",
        lambda: pd.DataFrame([{"vendor_key": "kaspersky", "nonempty_rows": 10}]),
    )



def test_main_reports_live_authority_view_when_found(ready_schema, capsys) -> None:
    rc = readiness.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert "Current live authority objects" in out
    assert "v_android_sample_family_type_authority: view" in out
    assert "current live authority coverage view is already present" in out
    assert "Current policy tables" in out
    assert "vendor_label_generic_token_fact: table" in out
    assert "active-column contract: canonical:is_active" in out
    assert "current generic-token policy table satisfies the expected live contract" in out


@pytest.mark.parametrize(
    ("object_name", "column"),
    [
        ("v_android_sample_family_type_authority", "authority_bucket"),
        ("v_android_missing_resolution_triage", "review_lane"),
        ("vendor_label_generic_token_fact", "normalized_token"),
        ("vendor_label_generic_token_fact", "is_active"),
    ],
)
def test_incomplete_live_contract_exits_nonzero(
    ready_schema, monkeypatch, capsys, object_name, column
) -> None:
    columns = readiness._fetch_columns()
    columns = columns[
        ~((columns["table_name"] == object_name) & (columns["column_name"] == column))
    ]
    monkeypatch.setattr(readiness, "_fetch_columns", lambda: columns)
    assert readiness.main() == 1
    assert "missing or incomplete" in capsys.readouterr().out


@pytest.mark.parametrize(
    "object_name",
    ["v_android_sample_family_type_authority", "v_android_missing_resolution_triage"],
)
def test_table_cannot_satisfy_live_view_contract(
    ready_schema, monkeypatch, object_name
) -> None:
    objects = readiness._fetch_objects()
    objects.loc[objects["table_name"] == object_name, "table_type"] = "BASE TABLE"
    monkeypatch.setattr(readiness, "_fetch_objects", lambda: objects)
    assert readiness.main() == 1


@pytest.mark.parametrize("missing_table", [False, True])
def test_missing_verdict_surface_skips_seed_query(
    ready_schema, monkeypatch, capsys, missing_table
) -> None:
    name = readiness.table("vendor_verdicts")
    if missing_table:
        objects = readiness._fetch_objects()
        monkeypatch.setattr(
            readiness, "_fetch_objects",
            lambda: objects[objects["table_name"] != name],
        )
    else:
        columns = readiness._fetch_columns()
        monkeypatch.setattr(
            readiness, "_fetch_columns",
            lambda: columns[
                ~((columns["table_name"] == name)
                  & (columns["column_name"] == readiness.CORE_VENDOR_COLUMNS[0]))
            ],
        )

    def unexpected_query():
        pytest.fail("Must not run vendor-count SQL against an incomplete schema")

    monkeypatch.setattr(readiness, "_estimate_seedable_vendor_rows", unexpected_query)
    assert readiness.main() == 1
    assert "unavailable:" in capsys.readouterr().out


def test_predeployment_mode_reports_prerequisites_without_requiring_live_view(
    ready_schema, monkeypatch, capsys
) -> None:
    objects = readiness._fetch_objects()
    monkeypatch.setattr(
        readiness, "_fetch_objects",
        lambda: objects[~objects["table_name"].isin(readiness.LIVE_AUTHORITY_OBJECTS)],
    )
    assert readiness.main() == 0
    assert "base schema looks ready" in capsys.readouterr().out


@pytest.mark.parametrize("empty", [False, True])
def test_vendor_seed_counts_preserve_token_semantics_in_one_scan(monkeypatch, empty) -> None:
    vendors = readiness.CORE_VENDOR_COLUMNS
    labels = [
        None, "", "  ", "NONE", "null", " n/A ", "undetected", "CLEAN",
        "benign", "harmless", "safe", "approved", "verified", "type-unsupported",
        "type_unsupported", "timeout", "failure", "Trojan.X", "generic", "0", "\t",
    ]
    excluded = {
        "", "none", "null", "n/a", "undetected", "clean", "benign", "harmless",
        "safe", "approved", "verified", "type-unsupported", "type_unsupported",
        "timeout", "failure",
    }
    rows = [] if empty else [
        [labels[(index + vendor_index) % len(labels)] for vendor_index in range(len(vendors))]
        for index in range(len(labels) + 3)
    ]
    with sqlite3.connect(":memory:") as conn:
        conn.execute(
            "CREATE TABLE virustotal_sample_vendor_engine_verdicts ("
            + ", ".join(f"{vendor} TEXT" for vendor in vendors) + ")"
        )
        conn.executemany(
            "INSERT INTO virustotal_sample_vendor_engine_verdicts VALUES ("
            + ",".join("?" for _ in vendors) + ")", rows,
        )
        calls = []

        def execute(query, **kwargs):
            calls.append(query)
            plan = conn.execute("EXPLAIN QUERY PLAN " + query).fetchall()
            assert sum("SCAN " in row[-1] for row in plan) == 1
            return pd.read_sql_query(query, conn)

        monkeypatch.setattr(readiness.db_engine, "execute_query", execute)
        actual = readiness._estimate_seedable_vendor_rows()
        expected = [
            {
                "vendor_key": vendor,
                "nonempty_rows": sum(
                    row[i] is not None and row[i].strip(" ").lower() not in excluded
                    for row in rows
                ),
            }
            for i, vendor in enumerate(vendors)
        ]
        expected.sort(key=lambda row: (-row["nonempty_rows"], row["vendor_key"]))
        assert actual.to_dict(orient="records") == expected
        assert len(calls) == 1


@pytest.mark.parametrize(
    "aggregate",
    [
        pd.DataFrame(),
        pd.DataFrame([{"wrong_column": 0}]),
        pd.DataFrame([{column: None for column in readiness.CORE_VENDOR_COLUMNS}]),
    ],
)
def test_missing_aggregate_is_not_reported_as_zero(monkeypatch, aggregate) -> None:
    monkeypatch.setattr(
        readiness.db_engine, "execute_query", lambda *args, **kwargs: aggregate
    )
    with pytest.raises(RuntimeError, match="unavailable or incomplete"):
        readiness._estimate_seedable_vendor_rows()
