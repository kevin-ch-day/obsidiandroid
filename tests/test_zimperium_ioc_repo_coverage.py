from __future__ import annotations

from pathlib import Path

import scripts.diagnostics.report_zimperium_ioc_repo_coverage as coverage


class _FakeCursor:
    def __init__(self) -> None:
        self._rows: list[tuple[str, ...]] = []

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
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
                requested = {str(v).lower() for v in params} or {"d" * 64}
                self._rows = [(token, "sha256") for token in requested if token == "d" * 64]
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


class _FakeConnection:
    def cursor(self):
        return _FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_report_treats_registry_mapped_md5_and_sha1_as_known(
    monkeypatch, tmp_path
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    sample_file = repo_root / "feed.csv"
    sample_file.write_text("\n".join(["a" * 32, "b" * 40, "c" * 64]), encoding="utf-8")

    output_dir = tmp_path / "out"
    monkeypatch.setattr(coverage, "REPO_ROOT", repo_root)
    monkeypatch.setattr(coverage, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(coverage, "SUMMARY_CSV", output_dir / "summary.csv")
    monkeypatch.setattr(coverage, "NEW_HASHES_CSV", output_dir / "new_hashes.csv")
    monkeypatch.setattr(coverage, "database_connection", lambda: _FakeConnection())

    coverage.main()

    summary = (output_dir / "summary.csv").read_text(encoding="utf-8").splitlines()
    new_hashes = (output_dir / "new_hashes.csv").read_text(encoding="utf-8").splitlines()

    assert summary[0].startswith("repo_file,source_label")
    assert "feed.csv" in summary[1]
    assert ",0," in summary[1] or summary[1].endswith(",0,,")
    assert new_hashes == ["repo_file,source_label,hash_type,hash_value"]
