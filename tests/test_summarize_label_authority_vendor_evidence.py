from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import scripts.diagnostics.summarize_label_authority_vendor_evidence as summary_report


def test_load_known_tokens_falls_back_to_legacy_alias_table(monkeypatch) -> None:
    queries: list[str] = []

    def _fake_query(query: str, **_kwargs):
        queries.append(query)
        if "FROM android_malware_family\n" in query and "UNION" in query:
            return pd.DataFrame([{"token": "bankbot"}])
        if "table_name = 'malware_family_alias_fact'" in query:
            return pd.DataFrame([{"n": 0}])
        if "table_name = 'android_malware_family_alias'" in query:
            return pd.DataFrame([{"n": 1}])
        if "FROM android_malware_family_alias" in query:
            return pd.DataFrame([{"token": "monocle"}, {"token": "spymax"}])
        raise AssertionError(query)

    monkeypatch.setattr(summary_report.db_engine, "execute_query", _fake_query)

    known_families, known_aliases = summary_report._load_known_tokens()

    assert "bankbot" in known_families
    assert "monocle" in known_aliases
    assert "spymax" in known_aliases


def test_main_bootstraps_missing_input(monkeypatch, tmp_path: Path) -> None:
    input_path = tmp_path / "missing.csv"
    summary_out = tmp_path / "summary.md"
    alias_out = tmp_path / "alias.csv"

    monkeypatch.setattr(
        summary_report,
        "parse_args",
        lambda: SimpleNamespace(input=input_path, summary_out=summary_out, alias_out=alias_out),
    )

    def _bootstrap(target: Path) -> bool:
        pd.DataFrame(
            [
                {
                    "sample_id": 1,
                    "vendor_key": "kaspersky",
                    "raw_vendor_label": "Trojan.AndroidOS.Blankbot",
                    "parsed_family_token": "blankbot",
                    "generic_token_flag": 0,
                }
            ]
        ).to_csv(target, index=False)
        return True

    monkeypatch.setattr(summary_report, "_bootstrap_input", _bootstrap)
    monkeypatch.setattr(summary_report, "_safe_load_alias_tokens", lambda: ({"bankbot"}, set()))

    rc = summary_report.main()

    assert rc == 0
    assert summary_out.exists()
    assert alias_out.exists()


def test_build_alias_candidates_excludes_obvious_non_family_tokens() -> None:
    df = pd.DataFrame(
        [
            {"sample_id": 1, "vendor_key": "a", "parsed_family_token": "banker", "generic_token_flag": 0, "raw_vendor_label": "TrojanBanker:Android/Banker.x"},
            {"sample_id": 2, "vendor_key": "b", "parsed_family_token": "win32", "generic_token_flag": 0, "raw_vendor_label": "Trojan.Win32.Agent"},
            {"sample_id": 3, "vendor_key": "c", "parsed_family_token": "unknown_malformed", "generic_token_flag": 0, "raw_vendor_label": "Trojan ( 0001 )"},
            {"sample_id": 4, "vendor_key": "d", "parsed_family_token": "blankbot", "generic_token_flag": 0, "raw_vendor_label": "Trojan.AndroidOS.Blankbot"},
        ]
    )

    out = summary_report._build_alias_candidates(df, known_families=set(), known_aliases=set())

    assert out["parsed_family_token"].tolist() == ["blankbot"]
