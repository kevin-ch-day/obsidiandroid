import os
from pathlib import Path
import importlib.util
import sys

MODULE_PATH = Path(__file__).resolve().parents[1] / "clean_bytecode_cache.py"
spec = importlib.util.spec_from_file_location("clean_bytecode_cache", MODULE_PATH)
cbc = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cbc
spec.loader.exec_module(cbc)


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

    cwd_logs = tmp_path / "logs"
    cwd_logs.mkdir()
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

    coverage_file = target / ".coverage"
    coverage_file.write_text("x")

    cbc.clean_bytecode_cache(target)

    assert not build_dir.exists()
    assert not egg_info_dir.exists()
    assert not pytest_tmp_dir.exists()
    assert not coverage_file.exists()
