"""Tests for AV keyword extraction query hygiene."""

from __future__ import annotations

from obsidiandroid.database import db_extract_av_label_keywords as keywords


def test_collect_raw_engine_labels_query_excludes_non_detection_tokens(monkeypatch) -> None:
    seen: dict[str, str] = {}

    def fake_execute_query(query, **_kwargs):
        seen["query"] = query
        return ["result"], [("Detected",), ("Trojan.Android",)]

    monkeypatch.setattr(keywords.db_engine, "execute_query", fake_execute_query)

    labels = keywords.collect_raw_engine_labels("google", sample_limit=10)

    assert labels == ["Detected", "Trojan.Android"]
    assert "type-unsupported" in seen["query"]
    assert "undetected" in seen["query"]
    assert "WHERE NOT (" in seen["query"]

