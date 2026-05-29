from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd

import scripts.diagnostics.report_label_noise_candidates as noise_report
import scripts.diagnostics.summarize_label_authority_vendor_evidence as summary_report


def test_build_sample_candidates_respects_authority_family_name_match() -> None:
    evidence_df = pd.DataFrame(
        [
            {
                "sample_id": 10,
                "parsed_family_token": "bank bot",
                "generic_token_flag": 0,
            },
            {
                "sample_id": 10,
                "parsed_family_token": "bank bot",
                "generic_token_flag": 0,
            },
        ]
    )
    authority_df = pd.DataFrame(
        [
            {
                "sample_id": 10,
                "authority_family_slug": "bankbot",
                "authority_family_name": "bank bot",
                "authority_type_slug": "banker",
            }
        ]
    )

    out = noise_report._build_sample_candidates(evidence_df, authority_df, alias_map={})

    assert len(out) == 1
    row = out.iloc[0]
    assert int(row["authority_matches_top_vendor_family"]) == 1
    assert int(row["authority_conflict_flag"]) == 0


def test_build_sample_candidates_flags_generic_dominance_and_missing_authority() -> None:
    evidence_df = pd.DataFrame(
        [
            {"sample_id": 22, "parsed_family_token": "trojan", "generic_token_flag": 1},
            {"sample_id": 22, "parsed_family_token": "generic", "generic_token_flag": 1},
            {"sample_id": 22, "parsed_family_token": "unknown", "generic_token_flag": 1},
            {"sample_id": 22, "parsed_family_token": "agent", "generic_token_flag": 1},
        ]
    )

    out = noise_report._build_sample_candidates(
        evidence_df,
        authority_df=pd.DataFrame(),
        alias_map={},
    )

    assert len(out) == 1
    row = out.iloc[0]
    assert int(row["authority_missing_flag"]) == 1
    assert int(row["generic_dominance_flag"]) == 1
    assert row["risk_reasons"] == "authority_missing|generic_dominance"


def test_write_summary_counts_pipe_separated_reasons(tmp_path: Path) -> None:
    candidates_df = pd.DataFrame(
        [
            {
                "sample_id": 1,
                "authority_family_slug": "fam_a",
                "top_vendor_family": "fam_b",
                "generic_pct": 75.0,
                "top_vendor_family_pct": 100.0,
                "authority_conflict_flag": 1,
                "authority_missing_flag": 0,
                "label_noise_risk_score": 0.60,
                "risk_reasons": "authority_conflict|generic_dominance",
            },
            {
                "sample_id": 2,
                "authority_family_slug": None,
                "top_vendor_family": None,
                "generic_pct": 100.0,
                "top_vendor_family_pct": 0.0,
                "authority_conflict_flag": 0,
                "authority_missing_flag": 1,
                "label_noise_risk_score": 0.45,
                "risk_reasons": "authority_missing",
            },
        ]
    )

    out_path = tmp_path / "label_noise_summary.md"
    noise_report._write_summary(candidates_df, out_path)

    text = out_path.read_text(encoding="utf-8")
    assert "| `authority_conflict` | 1 |" in text
    assert "| `generic_dominance` | 1 |" in text
    assert "| `authority_missing` | 1 |" in text
    assert "| `|` |" not in text


def test_label_noise_report_main_bootstraps_missing_input(monkeypatch, tmp_path: Path) -> None:
    input_path = tmp_path / "missing.csv"
    csv_out = tmp_path / "out.csv"
    md_out = tmp_path / "out.md"

    monkeypatch.setattr(
        noise_report,
        "parse_args",
        lambda: SimpleNamespace(input=input_path, csv_out=csv_out, md_out=md_out),
    )

    def _bootstrap(target: Path) -> bool:
        pd.DataFrame(
            [
                {"sample_id": 7, "parsed_family_token": "blankbot", "generic_token_flag": 0},
                {"sample_id": 7, "parsed_family_token": "blankbot", "generic_token_flag": 0},
            ]
        ).to_csv(target, index=False)
        return True

    monkeypatch.setattr(noise_report, "_bootstrap_input", _bootstrap)
    monkeypatch.setattr(
        noise_report,
        "_fetch_authority_map",
        lambda sample_ids: pd.DataFrame(
            [
                {
                    "sample_id": 7,
                    "authority_family_slug": "blankbot",
                    "authority_family_name": "BlankBot",
                    "authority_type_slug": "banker",
                }
            ]
        ),
    )
    monkeypatch.setattr(noise_report, "_load_alias_map", lambda: {})

    rc = noise_report.main()

    assert rc == 0
    assert csv_out.exists()
    assert md_out.exists()


def test_load_alias_map_falls_back_to_legacy_alias_table(monkeypatch) -> None:
    monkeypatch.setattr(noise_report.authority_contracts, "authority_alias_fact_present", lambda: False)
    monkeypatch.setattr(noise_report.authority_contracts, "legacy_android_family_alias_present", lambda: True)

    def _fake_query(query: str, **_kwargs):
        if "FROM android_malware_family_alias AS a" in query:
            return pd.DataFrame(
                [
                    {"alias_token": "monocle", "canonical_family_slug": "monokle"},
                    {"alias_token": "spymax", "canonical_family_slug": "spynote"},
                    {"alias_token": "goodnews", "canonical_family_slug": "smsworm"},
                ]
            )
        raise AssertionError(query)

    monkeypatch.setattr(noise_report.authority_contracts.db_engine, "execute_query", _fake_query)

    alias_map = noise_report._load_alias_map()

    assert alias_map["monocle"] == "monokle"
    assert alias_map["spymax"] == "spynote"
    assert alias_map["goodnews"] == "smsworm"


def test_fetch_authority_map_prefers_live_authority_view(monkeypatch) -> None:
    monkeypatch.setattr(noise_report.authority_contracts, "authority_view_present", lambda **_kwargs: True)

    queries: list[str] = []

    def _fake_query(query: str, params=None, **_kwargs):
        queries.append(query)
        return pd.DataFrame(
            [
                {
                    "sample_id": 99,
                    "authority_family_slug": "blankbot",
                    "authority_family_name": "BlankBot",
                    "authority_type_slug": "banker",
                }
            ]
        )

    monkeypatch.setattr(noise_report.authority_contracts.db_engine, "execute_query", _fake_query)

    out = noise_report._fetch_authority_map([99])

    assert len(out) == 1
    assert "FROM v_android_sample_family_type_authority" in queries[0]
    assert "FROM malware_sample_catalog AS msc" not in queries[0]


def test_load_known_tokens_falls_back_to_legacy_alias_table(monkeypatch) -> None:
    queries: list[str] = []

    def _fake_query(query: str, **_kwargs):
        queries.append(query)
        if "FROM android_malware_family\n" in query and "UNION" in query:
            return pd.DataFrame([{"token": "bankbot"}])
        if "FROM android_malware_family_alias AS a" in query:
            return pd.DataFrame(
                [
                    {"alias_token": "monocle", "canonical_family_slug": "monokle"},
                    {"alias_token": "spymax", "canonical_family_slug": "spynote"},
                ]
            )
        raise AssertionError(query)

    monkeypatch.setattr(summary_report.authority_contracts, "table_has_column", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(summary_report.authority_contracts, "authority_alias_fact_present", lambda: False)
    monkeypatch.setattr(summary_report.authority_contracts, "legacy_android_family_alias_present", lambda: True)
    monkeypatch.setattr(summary_report.authority_contracts.db_engine, "execute_query", _fake_query)

    known_families, known_aliases = summary_report._load_known_tokens()

    assert "bankbot" in known_families
    assert "monocle" in known_aliases
    assert "spymax" in known_aliases
    assert queries, "expected alias discovery SQL queries"


def test_vendor_summary_report_main_bootstraps_missing_input(monkeypatch, tmp_path: Path) -> None:
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
