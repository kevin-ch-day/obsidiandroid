from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import scripts.diagnostics.report_zimperium_ioc_repo_coverage as coverage
import scripts.diagnostics.generate_zimperium_ingest_tranche as tranche


class _FakeCursor:
    def __init__(self) -> None:
        self._rows: list[tuple[str, ...]] = []
        self.queries: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
        self.queries.append((sql, params))
        lowered = sql.lower()
        params_lc = tuple(str(p).lower() for p in params)

        if "malware_sample_catalog" in lowered and "lower(sha256)" in lowered:
            known_catalog = {"c" * 64}
            if "mapped_sha256" in lowered:
                known_catalog = {"c" * 64}
            self._rows = [(value,) for value in params_lc if value in known_catalog]
            return

        if "malware_artifact_ingest_queue" in lowered and "artifact_hash_norm" in lowered:
            known_queue = {"f" * 64}
            self._rows = [(value,) for value in params_lc if value in known_queue]
            return

        if "malware_artifact_hash_registry" in lowered and "md5" in lowered:
            registry_map = {
                "a" * 32: "c" * 64,
                "b" * 40: "f" * 64,
                "d" * 32: "z" * 64,
                "e" * 40: "y" * 64,
            }
            self._rows = [
                (token, sha256)
                for token in params_lc
                if (sha256 := registry_map.get(token)) is not None
            ]
            return

        if "malware_artifact_hash_registry" in lowered and "sha1" in lowered:
            registry_map = {
                "a" * 32: "c" * 64,
                "b" * 40: "f" * 64,
                "d" * 32: "z" * 64,
                "e" * 40: "y" * 64,
            }
            self._rows = [
                (token, sha256)
                for token in params_lc
                if (sha256 := registry_map.get(token)) is not None
            ]
            return

        self._rows = []

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self) -> None:
        pass


class _FakeConnection:
    def __init__(self) -> None:
        self.cursor_obj = _FakeCursor()

    def cursor(self):
        return self.cursor_obj

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_report_treats_registry_mapped_md5_and_sha1_as_known(
    monkeypatch, tmp_path: Path
) -> None:
    class _CoverageCursor:
        def __init__(self) -> None:
            self._rows: list[tuple[str, ...]] = []
            self.queries: list[tuple[str, tuple[object, ...]]] = []

        def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
            self.queries.append((sql, params))
            lowered = sql.lower()
            if "from malware_sample_catalog" in lowered:
                if "lower(sha256)" in lowered:
                    requested = {str(v).lower() for v in params} or {"c" * 64}
                    self._rows = [
                        (
                            token,
                            "FakeFam" if token == "c" * 64 else "",
                            "Trojan" if token == "c" * 64 else "",
                            "com.example" if token == "c" * 64 else "",
                        )
                        for token in requested
                        if token == "c" * 64
                    ]
                else:
                    self._rows = []
                return

            if "from malware_artifact_ingest_queue" in lowered:
                if "artifact_hash_norm" in lowered:
                    self._rows = [("d" * 64, "sha256")]
                else:
                    self._rows = []
                return

            if "from malware_artifact_hash_registry" in lowered:
                self._rows = [
                    ("a" * 32, "", "c" * 64),
                    ("", "b" * 40, "d" * 64),
                ]
                return

            self._rows = []

        def fetchall(self):
            return list(self._rows)

        def close(self) -> None:
            pass

    class _CoverageConnection:
        def __init__(self) -> None:
            self.cursor_obj = _CoverageCursor()

        def cursor(self):
            return self.cursor_obj

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    fake_conn = _CoverageConnection()
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    sample_file = repo_root / "feed.csv"
    sample_file.write_text("\n".join(["a" * 32, "b" * 40, "c" * 64]), encoding="utf-8")

    output_dir = tmp_path / "out"
    monkeypatch.setattr(coverage, "REPO_ROOT", repo_root)
    monkeypatch.setattr(coverage, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(coverage, "SUMMARY_CSV", output_dir / "summary.csv")
    monkeypatch.setattr(coverage, "NEW_HASHES_CSV", output_dir / "new_hashes.csv")
    monkeypatch.setattr(coverage, "database_connection", lambda: fake_conn)

    coverage.main()

    summary = (output_dir / "summary.csv").read_text(encoding="utf-8").splitlines()
    new_hashes = (output_dir / "new_hashes.csv").read_text(encoding="utf-8").splitlines()

    assert summary[0].startswith("repo_file,source_label")
    assert "feed.csv" in summary[1]
    assert ",0," in summary[1] or summary[1].endswith(",0,,")
    assert new_hashes == ["repo_file,source_label,hash_type,hash_value"]
    queue_queries = [
        (sql, params)
        for sql, params in fake_conn.cursor_obj.queries
        if "from malware_artifact_ingest_queue" in sql.lower()
    ]
    assert queue_queries
    assert "queue_status in (%s,%s)" in queue_queries[0][0].lower()
    assert queue_queries[0][1] == coverage.ACTIVE_QUEUE_STATUSES


def test_filter_new_hashes_skips_registry_mapped_hint_hashes(monkeypatch) -> None:
    fake_conn = _FakeConnection()
    monkeypatch.setattr(tranche, "database_connection", lambda: fake_conn)

    hashes = [
        "a" * 32,
        "b" * 40,
        "c" * 64,
        "d" * 32,
        "e" * 40,
        "f" * 64,
    ]

    result = tranche.filter_new_hashes(hashes)

    assert result == ["d" * 32, "e" * 40]
    queue_queries = [
        (sql, params)
        for sql, params in fake_conn.cursor_obj.queries
        if "malware_artifact_ingest_queue" in sql.lower()
    ]
    assert queue_queries
    assert all("queue_status in (%s,%s)" in sql.lower() for sql, _params in queue_queries)
    assert queue_queries[0][1][:2] == tranche.ACTIVE_QUEUE_STATUSES


def test_build_sql_only_blocks_active_queue_rows() -> None:
    sql = tranche.build_sql(
        ["a" * 64],
        artifact_name=None,
        artifact_family=None,
        artifact_category=None,
        artifact_subtype=None,
        artifact_source="unit-test",
        workload_lane="raw_hash_reservoir",
        temp_suffix="abc123",
        source_note="test",
    )

    assert "existing.queue_status IN ('PENDING', 'PROCESSING')" in sql


def test_main_exits_cleanly_when_zimperium_repo_is_missing(monkeypatch, tmp_path: Path, capsys) -> None:
    missing_root = tmp_path / "missing-zimperium"
    out_dir = tmp_path / "diagnostics"
    monkeypatch.setattr(coverage, "REPO_ROOT", missing_root)
    monkeypatch.setattr(coverage, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(coverage, "SUMMARY_CSV", out_dir / "summary.csv")
    monkeypatch.setattr(coverage, "NEW_HASHES_CSV", out_dir / "new_hashes.csv")

    exit_code = coverage.main()
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "[SKIP] Zimperium IOC repo not present" in out
    assert (out_dir / "summary.csv").exists()
    assert (out_dir / "new_hashes.csv").exists()
