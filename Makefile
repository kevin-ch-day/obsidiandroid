.PHONY: clean test test-full preflight-db check-run-integrity ml-scan help

help:
	@echo "Targets:"
	@echo "  make test          - fast pytest (excludes slow-marked tests; see pytest.ini)"
	@echo "  make test-full     - full pytest including slow integration modules"
	@echo "  make preflight-db  - MySQL/MariaDB connectivity check (split_db_health)"
	@echo "  make ml-scan       - static scan for suspicious .predict() / .predict_proba() sites"
	@echo "  make clean         - remove __pycache__ and stray logs (see clean_bytecode_cache.py)"
	@echo "  make check-run-integrity RUN_ROOT=<path>  - manifest vs observability rollup (Tier A)"

clean:
	python clean_bytecode_cache.py . --exclude venv --exclude .venv

# Fast default (~ excludes integration-heavy modules; see pytest.ini `slow` marker).
test:
	./run_tests.sh

# Complete suite (CI / pre-release).
test-full:
	./run_tests_full.sh

# MySQL/MariaDB connectivity (primary + Permission Intel DB). Exit 0 when healthy.
preflight-db:
	python -m database.split_db_health

# Optional static scan for ML call-site hygiene (see run_ml_static_scan.py; use --strict in CI if desired).
ml-scan:
	python run_ml_static_scan.py

# Tier A QA: cohort/train/test/top-model consistency across canonical JSON sinks.
check-run-integrity:
	@test -n "$(RUN_ROOT)" || (echo "Usage: make check-run-integrity RUN_ROOT=output/runs/<run_id>"; exit 1)
	python scripts/check_run_integrity.py --run-root "$(RUN_ROOT)"
