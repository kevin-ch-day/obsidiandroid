.PHONY: clean test test-full preflight-db help

help:
	@echo "Targets:"
	@echo "  make test          - fast pytest (excludes slow-marked tests; see pytest.ini)"
	@echo "  make test-full     - full pytest including slow integration modules"
	@echo "  make preflight-db  - MySQL/MariaDB connectivity check (split_db_health)"
	@echo "  make clean         - remove __pycache__ and stray logs (see clean_bytecode_cache.py)"

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
