.DEFAULT_GOAL := help

# Shared ignore pattern for `tree` (noise / generated paths).
_TREE_IGNORE := .git|.venv|__pycache__|*.pyc|output|logs|.pytest_cache|.pytest_tmp|*.egg-info|build|dist|.mypy_cache|.ruff_cache|.hypothesis|htmlcov|coverage.xml|wandb|mlruns

.PHONY: clean clean-bytecode tree-source tree-obsidiandroid tree-utils tree-exporting-shims test test-full setup menu install-editable doc-check verify verify-v3 ci ml-scan ml-scan-strict preflight-db check-run-integrity dev-import-check output-writer-audit help

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
	@echo "  make tree-utils      - (removed) legacy utils/ retired; use tree-obsidiandroid"
	@echo "  make tree-exporting-shims  - (removed) use src/obsidiandroid/common/export_*"
	@echo "  make dev-import-check  - verify obsidiandroid import paths (scripts/dev/check_import_surface.py)"
	@echo "  make output-writer-audit  - CSV audit of output-related write call-sites (scripts/dev/output_writer_audit.py)"
	@echo "  make verify          - import smoke (check_import_surface) + fast pytest; use before PRs"
	@echo "  make verify-v3       - V3 closure contract tests (validate script + ML seed exports)"
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
	@echo "Legacy utils/ removed; see src/obsidiandroid/ (common/, reporting/, cli/)." && exit 0

tree-exporting-shims:
	@echo "Former utils/exporting/ lives under src/obsidiandroid/common/export_* and reporting/." && exit 0

# Same as ./setup.sh -> scripts/dev/bootstrap_venv.sh
setup:
	./setup.sh

# Same as ./run.sh -> scripts/dev/launch_startup_menu.sh
menu:
	./run.sh

# Editable install so `import obsidiandroid` works from any cwd (uses active python).
install-editable:
	python -m pip install -e .

# Fast default: canonical script under scripts/dev/.
test:
	./scripts/dev/run_tests.sh

# Complete suite (CI / pre-release).
test-full:
	./scripts/dev/run_tests_full.sh

# MySQL/MariaDB connectivity (primary + Permission Intel DB). Exit 0 when healthy.
preflight-db:
	python -m database.split_db_health

# Optional static scan for ML call-site hygiene (scripts/dev/run_ml_static_scan.py).
ml-scan:
	python -m scripts.dev.run_ml_static_scan

ml-scan-strict:
	python -m scripts.dev.run_ml_static_scan --strict

doc-check:
	python scripts/dev/check_doc_hygiene.py

# Same gates as .github/workflows/ci.yml (run before pushing if you lack Actions feedback).
ci: doc-check verify verify-v3 ml-scan-strict

# Import surface + default fast test selection (CI-friendly local gate).
verify:
	python scripts/dev/check_import_surface.py && ./scripts/dev/run_tests.sh

# V3 closure contract lane (pytest fixtures; offline slot check when output/runs exists).
refresh-v3-handoff:
	python scripts/dev/refresh_v3_canonical_handoff.py --skip-missing-slots

validate-v3-live:
	python scripts/dev/validate_v3_canonical_runs.py --verify-only --strict --skip-missing-slots

wait-validate-majorfam:
	python scripts/dev/wait_validate_v3_slot.py --profile-id android_malware_major_families --refresh-handoff --validate-all

verify-v3:
	python -m pytest -q tests/test_validate_v3_canonical_runs.py tests/test_import_v3_run_to_db.py tests/test_obsidiandroid_research_ddl.py tests/test_ml_seed_exports.py tests/test_v3_label_contract.py tests/test_permission_pattern_contract.py tests/test_v3_canonical_hard_fail.py tests/test_v3_samples_label_contract.py tests/test_cohort_persistence.py tests/test_run_artifact_resolve.py tests/test_runtime_support_v3.py tests/test_research_validity_bundle_v3.py tests/test_hostile_audit_bundle_v3.py tests/test_v3_dl_handoff.py -m "not slow"
	python scripts/dev/validate_v3_canonical_runs.py --verify-only --strict --runs-root artifacts/baselines/v3_canonical_slots
	python scripts/import_v3_run_to_db.py --runs-root artifacts/baselines/v3_canonical_slots --release-tag v3.0.0
	@if [ -d output/runs/allcurrent_diagnostic ]; then python scripts/dev/validate_v3_canonical_runs.py --verify-only --strict --skip-missing-slots; fi
	@if [ -d output/runs/allcurrent_diagnostic ]; then python scripts/import_v3_run_to_db.py --runs-root output/runs --release-tag v3.0.0 --skip-missing-slots; fi

# Dry-run ObsidianDroid research DB import plans for canonical fixture slots.
dry-run-v3-db-import:
	python scripts/import_v3_run_to_db.py --runs-root artifacts/baselines/v3_canonical_slots --release-tag v3.0.0

# Quick smoke: obsidiandroid package and pipeline facade (editable install or PYTHONPATH=src).
dev-import-check:
	python scripts/dev/check_import_surface.py

# Read-only AST scan: path-like writes that may target output/ / diagnostics / runs / bundles.
output-writer-audit:
	python scripts/dev/output_writer_audit.py --out artifacts/baselines/output_writer_audit.csv

# Tier A QA: cohort/train/test/top-model consistency across canonical JSON sinks.
check-run-integrity:
	@test -n "$(RUN_ROOT)" || (echo "Usage: make check-run-integrity RUN_ROOT=output/runs/<run_id>"; exit 1)
	python scripts/check_run_integrity.py --run-root "$(RUN_ROOT)"
