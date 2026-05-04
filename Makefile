.DEFAULT_GOAL := help

# Shared ignore pattern for `tree` (noise / generated paths).
_TREE_IGNORE := .git|.venv|__pycache__|*.pyc|output|logs|.pytest_cache|.pytest_tmp|*.egg-info|build|dist|.mypy_cache|.ruff_cache|.hypothesis|htmlcov|coverage.xml|wandb|mlruns

.PHONY: clean clean-bytecode tree-source tree-obsidiandroid tree-utils tree-exporting-shims test test-full setup menu install-editable doc-check verify ci ml-scan ml-scan-strict preflight-db check-run-integrity dev-import-check help

help:
	@echo "Targets:"
	@echo "  make setup         - create/refresh .venv and pip install -r requirements.txt (./setup.sh)"
	@echo "  make menu          - launch interactive startup menu (./run.sh; sets PYTHONPATH=src)"
	@echo "  make install-editable  - pip install -e . (use project venv: source .venv/bin/activate)"
	@echo "  make test          - fast pytest (excludes slow-marked tests; see pyproject.toml [tool.pytest.ini_options])"
	@echo "  make test-full     - full pytest including slow integration modules"
	@echo "  make preflight-db  - MySQL/MariaDB connectivity check (split_db_health)"
	@echo "  make ml-scan       - static scan for suspicious .predict() / .predict_proba() sites"
	@echo "  make ml-scan-strict  - same scan; exit 1 if any warning (matches CI)"
	@echo "  make doc-check     - block reintroduced phantom paths in README + key docs"
	@echo "  make ci            - doc-check + verify + ml-scan-strict (parity with GitHub Actions)"
	@echo "  make clean         - alias for clean-bytecode (bytecode + stray logs under .)"
	@echo "  make clean-bytecode  - run scripts/dev/clean_bytecode_cache.py on the repo root"
	@echo "  make tree-source     - repo-root layout (excludes .venv, output, caches; needs \`tree\`)"
	@echo "  make tree-obsidiandroid  - package tree: src/obsidiandroid only (migration progress)"
	@echo "  make tree-utils      - legacy utils/ tree (compare with tree-obsidiandroid)"
	@echo "  make tree-exporting-shims  - utils/exporting/ (shim-only re-exports)"
	@echo "  make dev-import-check  - verify obsidiandroid import paths (scripts/dev/check_import_surface.py)"
	@echo "  make verify          - import smoke (check_import_surface) + fast pytest; use before PRs"
	@echo "  make check-run-integrity RUN_ROOT=<path>  - manifest vs observability rollup (Tier A)"

clean: clean-bytecode

clean-bytecode:
	python scripts/dev/clean_bytecode_cache.py . --exclude venv --exclude .venv

# Optional: install the `tree` package on Fedora (`dnf install tree`) to use these targets.
tree-source:
	@command -v tree >/dev/null 2>&1 && tree -I '$(_TREE_IGNORE)' || (echo "Optional: install \`tree\` to list the source tree (e.g. dnf install tree)." >&2; exit 0)

tree-obsidiandroid:
	@command -v tree >/dev/null 2>&1 && tree -L 4 -I '$(_TREE_IGNORE)' src/obsidiandroid || (echo "Install \`tree\` (e.g. dnf install tree)." >&2; exit 0)

tree-utils:
	@command -v tree >/dev/null 2>&1 && tree -L 3 -I '$(_TREE_IGNORE)' utils || (echo "Install \`tree\`." >&2; exit 0)

tree-exporting-shims:
	@command -v tree >/dev/null 2>&1 && tree -L 2 utils/exporting || (echo "Install \`tree\`." >&2; exit 0)

# Same as ./setup.sh -> scripts/dev/bootstrap_venv.sh
setup:
	./setup.sh

# Same as ./run.sh -> scripts/dev/launch_startup_menu.sh
menu:
	./run.sh

# Editable install so `import obsidiandroid` works from any cwd (uses active python).
install-editable:
	python -m pip install -e .

# Fast default: invoke canonical script (repo-root ./run_tests.sh is a thin wrapper to the same path).
test:
	./scripts/dev/run_tests.sh

# Complete suite (CI / pre-release).
test-full:
	./scripts/dev/run_tests_full.sh

# MySQL/MariaDB connectivity (primary + Permission Intel DB). Exit 0 when healthy.
preflight-db:
	python -m database.split_db_health

# Optional static scan for ML call-site hygiene (repo-root run_ml_static_scan.py wraps this).
ml-scan:
	python -m scripts.dev.run_ml_static_scan

ml-scan-strict:
	python -m scripts.dev.run_ml_static_scan --strict

doc-check:
	python scripts/dev/check_doc_hygiene.py

# Same gates as .github/workflows/ci.yml (run before pushing if you lack Actions feedback).
ci: doc-check verify ml-scan-strict

# Import surface + default fast test selection (CI-friendly local gate).
verify:
	python scripts/dev/check_import_surface.py && ./scripts/dev/run_tests.sh

# Quick smoke: obsidiandroid package and pipeline facade (editable install or PYTHONPATH=src).
dev-import-check:
	python scripts/dev/check_import_surface.py

# Tier A QA: cohort/train/test/top-model consistency across canonical JSON sinks.
check-run-integrity:
	@test -n "$(RUN_ROOT)" || (echo "Usage: make check-run-integrity RUN_ROOT=output/runs/<run_id>"; exit 1)
	python scripts/check_run_integrity.py --run-root "$(RUN_ROOT)"
