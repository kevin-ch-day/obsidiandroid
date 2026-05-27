from __future__ import annotations

import pandas as pd

import scripts.diagnostics.label_authority_schema_readiness as readiness


def test_main_reports_live_authority_view_when_found(monkeypatch, capsys) -> None:
    monkeypatch.setattr(readiness, "_fetch_columns", lambda: pd.DataFrame())
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
            ]
        ),
    )
    monkeypatch.setattr(readiness, "_missing_columns", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        readiness,
        "_estimate_seedable_vendor_rows",
        lambda: pd.DataFrame([{"vendor_key": "kaspersky", "nonempty_rows": 10}]),
    )

    rc = readiness.main()
    out = capsys.readouterr().out

    assert rc == 0
    assert "Current live authority objects" in out
    assert "v_android_sample_family_type_authority: view" in out
    assert "current live authority coverage view is already present" in out
