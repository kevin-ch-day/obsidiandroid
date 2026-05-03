.PHONY: clean test test-full

clean:
	python clean_bytecode_cache.py . --exclude venv --exclude .venv

# Fast default (~ excludes integration-heavy modules; see pytest.ini `slow` marker).
test:
	./run_tests.sh

# Complete suite (CI / pre-release).
test-full:
	./run_tests_full.sh
