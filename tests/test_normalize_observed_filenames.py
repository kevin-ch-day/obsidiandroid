from __future__ import annotations

from scripts.diagnostics import normalize_observed_filenames as mod


def test_normalize_observed_filename_decodes_safe_transport_artifacts() -> None:
    assert mod.normalize_observed_filename("Numbers%20Fake.apk") == "Numbers Fake.apk"
    assert mod.normalize_observed_filename("1004&igrave;슂&ecirc;&deg;_.apk-") == "1004ì슂ê°_.apk"
    assert mod.normalize_observed_filename("file.apk.apk") == "file.apk"
    assert mod.normalize_observed_filename("Ai_Account_protect .apk") == "Ai_Account_protect.apk"
    assert mod.normalize_observed_filename("line\\nwrap.apk") == "line wrap.apk"


def test_is_suspicious_filename_ignores_legitimate_unicode_names() -> None:
    assert mod.is_suspicious_filename("章鱼 RAT.apk") is False
    assert mod.is_suspicious_filename("تطبيق اختراق.apk") is False
    assert mod.is_suspicious_filename("İNATTV.apk") is False
    assert mod.is_suspicious_filename("Numbers%20Fake.apk") is True


def test_is_legitimate_multilingual_filename_accepts_real_unicode_titles() -> None:
    assert mod.is_legitimate_multilingual_filename("تطبيق اختراق.apk") is True
    assert mod.is_legitimate_multilingual_filename("章鱼 RAT.apk") is True
    assert mod.is_legitimate_multilingual_filename("SİBER ANDROİD RAT_1.3.apk") is True
    assert mod.is_legitimate_multilingual_filename("Numbers%20Fake.apk") is False
    assert mod.is_legitimate_multilingual_filename("file.apk.apk") is False


def test_load_candidates_filters_non_suspicious_rows(monkeypatch) -> None:
    rows = [
        (1, "章鱼 RAT.apk", "Zimperium IOC"),
        (2, "Numbers%20Fake.apk", "Zimperium IOC"),
        (3, "file.apk.apk", None),
    ]

    def _fake_execute_query(query, params=(), fetch=True, return_columns=True):  # noqa: ANN001
        assert "malware_sample_catalog" in query
        return (["sample_id", "observed_filename", "source_batch_label"], rows)

    monkeypatch.setattr(mod.db_engine, "execute_query", _fake_execute_query)

    candidates = mod.load_candidates()

    assert [candidate.sample_id for candidate in candidates] == [2, 3]
    assert candidates[0].normalized_filename == "Numbers Fake.apk"
    assert candidates[1].normalized_filename == "file.apk"


def test_apply_candidates_updates_each_row(monkeypatch) -> None:
    candidates = [
        mod.FilenameFixCandidate(
            sample_id=2,
            observed_filename="Numbers%20Fake.apk",
            normalized_filename="Numbers Fake.apk",
            source_batch_label="Zimperium IOC",
        ),
        mod.FilenameFixCandidate(
            sample_id=3,
            observed_filename="file.apk.apk",
            normalized_filename="file.apk",
            source_batch_label=None,
        ),
    ]

    class _Cursor:
        def __init__(self) -> None:
            self.calls: list[tuple[object, object]] = []
            self.rowcount = 1
            self.closed = False

        def execute(self, query, params=()):  # noqa: ANN001
            self.calls.append((query, params))

        def close(self) -> None:
            self.closed = True

    class _Conn:
        def __init__(self) -> None:
            self.cursor_obj = _Cursor()

        def cursor(self):  # noqa: ANN001
            return self.cursor_obj

    conn = _Conn()

    class _ConnectionCtx:
        def __enter__(self):  # noqa: ANN001
            return conn

        def __exit__(self, exc_type, exc, tb):  # noqa: ANN001
            return False

    monkeypatch.setattr(mod.db_engine, "database_connection", lambda: _ConnectionCtx())

    updated_rows = mod.apply_candidates(candidates)

    assert updated_rows == 2
    assert conn.cursor_obj.closed is True
    assert conn.cursor_obj.calls[0][1] == ("Numbers Fake.apk", 2)
    assert conn.cursor_obj.calls[1][1] == ("file.apk", 3)
