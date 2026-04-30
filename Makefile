.PHONY: clean test

clean:
	python clean_bytecode_cache.py . --exclude venv --exclude .venv

test:
	./run_tests.sh
