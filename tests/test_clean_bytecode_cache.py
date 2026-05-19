import scripts.dev.clean_bytecode_cache as cbc


def test_clean_bytecode_cache_respects_exclude_dirs(tmp_path):
    target = tmp_path
    pycache = target / "__pycache__"
    pycache.mkdir()
    (pycache / "foo.pyc").write_text("x")
    venv_cache = target / "venv" / "__pycache__"
    venv_cache.mkdir(parents=True)
    (venv_cache / "bar.pyc").write_text("x")

    cbc.clean_bytecode_cache(target, exclude_dirs=["venv"])

    assert not pycache.exists()
    assert (venv_cache / "bar.pyc").exists()


def test_clean_bytecode_cache_scopes_log_cleanup_to_target_root(tmp_path, monkeypatch):
    target = tmp_path / "target"
    target.mkdir()
    target_logs = target / "logs"
    target_logs.mkdir()
    (target_logs / "target.log").write_text("x")

    # ``tmp_path/logs`` may already exist from autouse output/log isolation fixtures.
    cwd_logs = tmp_path / "logs"
    cwd_logs.mkdir(parents=True, exist_ok=True)
    cwd_file = cwd_logs / "cwd.log"
    cwd_file.write_text("x")

    monkeypatch.chdir(tmp_path)
    cbc.clean_bytecode_cache(target)

    assert not (target_logs / "target.log").exists()
    assert cwd_file.exists()


def test_clean_bytecode_cache_removes_build_and_pytest_artifacts(tmp_path):
    target = tmp_path
    build_dir = target / "build"
    build_dir.mkdir()
    (build_dir / "artifact.txt").write_text("x")

    egg_info_dir = target / "obsidiandroid_framework.egg-info"
    egg_info_dir.mkdir()
    (egg_info_dir / "PKG-INFO").write_text("x")

    pytest_tmp_dir = target / ".pytest_tmp_quickmenu"
    pytest_tmp_dir.mkdir()
    (pytest_tmp_dir / "state.txt").write_text("x")

    pytest_tmp_generic = target / ".pytest_tmp"
    pytest_tmp_generic.mkdir()
    (pytest_tmp_generic / "state.txt").write_text("x")

    pytest_cache_dir = target / ".pytest_cache"
    pytest_cache_dir.mkdir()
    (pytest_cache_dir / "README").write_text("x")

    ruff_cache_dir = target / ".ruff_cache"
    ruff_cache_dir.mkdir()
    (ruff_cache_dir / "state").write_text("x")

    mypy_cache_dir = target / ".mypy_cache"
    mypy_cache_dir.mkdir()
    (mypy_cache_dir / "state").write_text("x")

    htmlcov_dir = target / "htmlcov"
    htmlcov_dir.mkdir()
    (htmlcov_dir / "index.html").write_text("x")

    coverage_file = target / ".coverage"
    coverage_file.write_text("x")
    coverage_extra = target / ".coverage.unit"
    coverage_extra.write_text("x")

    cbc.clean_bytecode_cache(target)

    assert not build_dir.exists()
    assert not egg_info_dir.exists()
    assert not pytest_tmp_dir.exists()
    assert not pytest_tmp_generic.exists()
    assert not pytest_cache_dir.exists()
    assert not ruff_cache_dir.exists()
    assert not mypy_cache_dir.exists()
    assert not htmlcov_dir.exists()
    assert not coverage_file.exists()
    assert not coverage_extra.exists()
