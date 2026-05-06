# Root & structure audit — ObsidianDroid (project update)

This document is a **status report** and **deep audit** of repository layout: what improved during the migration-style cleanup, why the repo root still looks busy, and how the project compares to a conventional professional Python application. It complements **[`STRUCTURE_MIGRATION_PLAN.md`](STRUCTURE_MIGRATION_PLAN.md)** (pass-by-pass history).

---

## 1. Executive summary

ObsidianDroid is intentionally a **hybrid layout**: an installable package under **`src/obsidiandroid/`**, plus large **legacy implementation trees** at the repository root (`analysis/`, `database/`, `ml_classification/`, `model/`, `utils/`) preserved for compatibility and test coverage. That hybrid is **professional for a mature research codebase** (explicit migration, shims, CI), but it **does not look like a minimal greenfield app** (single `src/` package only, empty root).

**Progress so far:** canonical CLI/common/pipeline/governance surfaces, diagnostics and dev tooling under **`scripts/`** (repo-root **`data_inspect/`** and **`devtools/`** shims **removed** — use **`scripts.diagnostics`** / **`scripts.dev`**), Makefile and CI as the operator entrypoints, pytest configuration folded into **`pyproject.toml`**, documentation split so long-form guides live under **`docs/`**, and automated GitHub Actions + Dependabot.

**Still visibly crowded at the root:** domain packages, shim directories, thin wrappers (`main.py`, shell scripts, bytecode/ML scan entries), metadata files, and **runtime/generated** directories when present locally (`output/`, `logs/`, `__pycache__/`, `.pytest_tmp/`). Reducing *listed* clutter further requires either **moving legacy domains** (big bang, high risk) or **accepting pointers-only at root** for docs (already partly done for AGENTS/GOVERNANCE/STRUCTURE).

---

## 2. When cleanup and moves started (timeline of passes)

Work proceeded in **documented passes** (see **`STRUCTURE_MIGRATION_PLAN.md`**). Condensed narrative:

| Phase | Focus |
|-------|--------|
| **Early passes (1–8)** | **`src/obsidiandroid/`** package shell, CLI under `cli/`, **`obsidiandroid.common`**, **`obsidiandroid.pipeline`** facade to **`analysis.pipeline.runner`**, **`obsidiandroid.governance`**, import smoke (**`scripts/dev/check_import_surface.py`**), **`utils/`** shims. |
| **Pass 6–9** | Docs/script indices; setuptools hygiene; module audits. |
| **Pass 10+** | **Root cleanup:** `engine_aliases.yaml` → **`config/`**; migration plan & governance → **`docs/`** with root stubs; **`run_ml_static_scan`** implementation → **`scripts/dev/`**; stale **`py-modules`** removed. |
| **Pass 11** | Shell scripts: canonical **`scripts/dev/*.sh`**; root **`setup.sh`**, **`run.sh`**, **`run_tests*.sh`** as thin wrappers. |
| **Pass 12** | Internal imports → **`scripts.diagnostics`** / **`scripts.dev`**; shim parity tests for **`devtools`**; **`data_inspect`** / **`devtools`** kept in setuptools discovery for **`pip install -e .`**. |
| **Pass 13** | **`pytest.ini`** merged into **`pyproject.toml`**; full **`AGENTS.md`** → **`docs/AGENTS.md`**; root **`AGENTS.md`** stub. |
| **Pass 14 (shim sunset)** | Remove **`data_inspect/`** and **`devtools/`**; drop setuptools **`include`** entries; document migration to **`scripts.diagnostics`** / **`scripts.dev`**. |
| **Pass 15–19** | Makefile as operator default (**`make verify`**, **`make ci`**, **`make setup/menu/install-editable`**); **`.editorconfig`** / **`.gitattributes`**; **`make verify`** + CI; strict ML scan; Dependabot (Actions + pip); Python **3.10/3.12** CI matrix; **`.python-version`**; **`.DEFAULT_GOAL := help`**. |

**When “moving files” became systematic:** starting around **Pass 10–11** (YAML, docs, dev scripts, shell canonical paths). **Large directories** (`analysis/`, `database/`, etc.) were explicitly **not** bulk-moved—policy is migration passes with tests, not drive-by refactors.

---

## 3. What “professional” looks like here (criteria)

| Criterion | Status |
|-----------|--------|
| **Installable package** | **`pyproject.toml`**, **`pip install -e .`**, console script **`obsidiandroid`**. |
| **Clear public API direction** | **`obsidiandroid.*`** for new code; facades for pipeline/governance/common. |
| **Testing** | **`pytest`** defaults in **`pyproject.toml`**; fast/slow split; **~390+** fast tests (default **`not slow`** selection; run **`make test-full`** for slow modules). |
| **CI/CD** | **`.github/workflows/ci.yml`**: **`make verify`**, **`make ml-scan-strict`**, **`pip check`**, Python matrix. |
| **Dependency hygiene** | Dependabot for **GitHub Actions** and **pip**; **`requirements.txt`** wired via dynamic metadata. |
| **Contributor docs** | **`docs/AGENTS.md`**, **`docs/developer_guide.md`**, **`Makefile`** help, optional **`.pre-commit-config.yaml`**. |
| **Operational clarity** | **`make ci`** mirrors CI; **`make tree-source`** after **`make clean-bytecode`** for layout reviews. |

**Gap vs a “clean single-package repo”:** multiple top-level Python **namespaces** (`analysis`, `database`, …) remain by design until a deliberate migration shrinks them.

---

## 4. Deep audit — repository root (current)

### 4.1 Metadata & tooling (should stay at root)

| Item | Role |
|------|------|
| **`README.md`**, **`LICENSE`**, **`pyproject.toml`**, **`requirements.txt`**, **`Makefile`** | Standard Python/OSS project signals; GitHub and tooling expect several of these at root. |
| **`.editorconfig`**, **`.gitattributes`**, **`.python-version`** | Cross-editor consistency and interpreter hint. |
| **`.github/`** | CI and Dependabot (not listed in naive `ls` without `-a`). |

### 4.2 Thin wrappers & entrypoints (small files; “noise” but functional)

| Item | Canonical implementation | Notes |
|------|-------------------------|--------|
| **`main.py`** | **`obsidiandroid.cli`** | Setuptools **`py-modules`**; checkout bootstrap via **`import utils`** (**Pass 103**); tests monkeypatch **`main`**. |
| **`clean_bytecode_cache`** / **`run_ml_static_scan`** | **`scripts.dev.*`** | **Pass 101:** repo-root shims removed; use **`python scripts/dev/clean_bytecode_cache.py`** / **`python -m scripts.dev.run_ml_static_scan`** or **`make`** targets. **`py-modules`** lists **`main`** only. |
| **`setup.sh`**, **`run.sh`**, **`scripts/dev/run_tests.sh`**, **`scripts/dev/run_tests_full.sh`** | **`scripts/dev/*.sh`** | Test runners; **`make test`** / **`make test-full`** call **`scripts/dev/`** directly. |

**Assessment:** Removing these without a **packaging + docs + CI** migration increases friction; lowest-risk reduction is **already done** (Makefile **`python -m`** / **`scripts/dev`** paths).

### 4.3 Documentation pointers (minimal bytes at root)

| Item | Purpose |
|------|---------|
| **`AGENTS.md`**, **`GOVERNANCE.md`**, **`STRUCTURE_MIGRATION_PLAN.md`** | Point to **`docs/*.md`** so root stays grep-friendly for tools expecting filenames here. |

### 4.4 First-class source trees (large; cannot “hide” without moves)

| Directory | Role |
|-----------|------|
| **`src/obsidiandroid/`** | **Canonical product package** (CLI, common, pipeline facade, governance, reporting/observability surfaces, diagnostics facade — plus placeholder roots for domains not yet bulk-moved). |
| **`analysis/`** | Pipeline stages, AV parsers, diagnostics glue — **core legacy implementation**. Pipeline observability APIs live under **`obsidiandroid.observability.pipeline_observability`** (Pass 32); the former **`analysis/observability`** shim path was **removed** (Pass 33). |
| **`database/`** | DB access, cohort SQL. |
| **`ml_classification/`** | Training, vectorization, labeling helpers. |
| **`model/`** | Model artifacts support (as present in repo). |
| **`config/`**, **`profiles/`** | Configuration and YAML profiles (**`package-data`** for profiles). |
| **`utils/`** | Legacy + **shims** re-exporting **`obsidiandroid.*`** where applicable; **`export_manager`** is a **module-alias shim** to **`obsidiandroid.reporting.export_manager`**. **`utils/logging/`** is a **thin shim** to **`obsidiandroid.observability.logging`** (implementation under **`src/obsidiandroid/observability/logging/`**). |
| **`tests/`** | Pytest tree. |
| **`scripts/`** | **`dev/`**, **`diagnostics/`**, **`research/`**, operator **`scripts/*.py`**. |

### 4.5 Removed compatibility shims (historical)

| Directory | Status |
|-----------|--------|
| **`data_inspect/`** | **Removed** — use **`scripts.diagnostics`** (see **`scripts/diagnostics/README.md`**). |
| **`devtools/`** | **Removed** — use **`scripts.dev`** (e.g. **`from scripts.dev import data_fuzzer`**). |

**Assessment:** Deletion completed; off-repo importers must switch import paths (no repo-root packages under those names after **`pip install -e .`**).

### 4.6 Runtime / generated (should not be treated as “project structure”)

Typically gitignored or partially ignored; often **still visible** in **`ls`** after local runs:

| Path | Notes |
|------|------|
| **`output/`**, **`logs/`** | Run outputs; **`make tree-source`** excludes. |
| **`__pycache__/`**, **`.pytest_cache/`**, **`.pytest_tmp/`** | Use **`make clean-bytecode`** before structural reviews. |
| **`.venv/`** | Local virtualenv (gitignored). |

### 4.7 Preserved evidence / baselines

| Path | Notes |
|------|------|
| **`artifacts/baselines/`** | Intentional regression/evidence snapshots (**not** ad-hoc **`output/`**). |

---

## 5. Gap analysis — why the root still feels busy

1. **Hybrid architecture** packs **~7** top-level Python trees (`analysis`, `database`, `config`, `ml_classification`, `model`, `utils`, `scripts`) **besides** **`src/`** — that is **more than most single-app repos** (shim packages removed).
2. **Wrappers + pointers** add **~10** small root files; each has a reason (setuptools, habits, Cursor/GitHub expectations).
3. **Runtime dirs** pollute **`ls`** unless hooks/docs remind contributors to use **`make clean-bytecode`** and **`make tree-source`**.
4. **README “Project Structure”** diagram is **abbreviated**; it does not list **`model/`**, **`profiles/`**, **`tests/`**, **`LICENSE`**, **`Makefile`**, **`requirements.txt`**, **`artifacts/`**, or pointers — readers should use **`make tree-source`** or this audit for truth.

---

## 6. Recommendations — next phases (prioritized)

### Near term (high ROI, lower risk)

1. Keep **`make ci`** / **`make verify`** as the **default pre-PR** story; ensure **`README`** “Contributing” links this audit once.
2. Run **`make tree-source`** in onboarding docs (already partly there).
3. Optionally add **`docs/contributing.md`** one-pager: hybrid layout explanation + **`make ci`** (avoid duplicating **`STRUCTURE_MIGRATION_PLAN.md`** in full).

### Medium term (requires planning)

4. ~~**Pass 15 (shim sunset):**~~ **Done** — see **`docs/STRUCTURE_MIGRATION_PLAN.md`**, **Pass 24** (shim package removal).
5. ~~**Pass 16:**~~ **Partially done** — **`obsidiandroid.diagnostics`** re-exports **`output_inventory`**, **`output_artifact_policy`**, **`feature_lineage_report`**; expand only after dependency review.
6. **Expand README tree** or generate it from **`make tree-source`** screenshot in docs — reduces “root looks huge” confusion without moving code.

### Long term (large effort)

7. **Incremental migration** of **`analysis/pipeline`** internals behind **`obsidiandroid.pipeline`** (already partially facaded); avoid duplicate stage logic.
8. **`database/`** vs **`obsidiandroid.database`** naming clarity before any physical move.

---

## 7. Summary table — “professional” checklist

| Area | Current maturity |
|------|------------------|
| Packaging & metadata | Strong (**`pyproject.toml`**, dynamic deps, console script). |
| Testing & CI | Strong (**`verify`**, matrix, strict ML scan, Dependabot). |
| Docs | Strong (**`docs/`** hub, AGENTS, migration plan, this audit). |
| Root aesthetics | **Moderate** — hybrid legacy layout + wrappers; **acceptable** with documented rationale. |
| Future consolidation | **Planned** — shim sunset + optional diagnostics facade; **no rush** without release coordination.

---

## 8. Related documents

- **[`STRUCTURE_MIGRATION_PLAN.md`](STRUCTURE_MIGRATION_PLAN.md)** — Pass-by-pass changelog and labels.
- **[`docs/AGENTS.md`](AGENTS.md)** — Day-to-day contributor rules.
- **[`README.md`](../README.md)** — User-facing overview (structure subsection intentionally partial).

### Documentation hygiene (ongoing)

Operators often copy-paste paths from docs; **phantom references** (missing scripts, old package layouts) waste time. Pass **21** tightened **`user_guide`** and **`modeling_reference`** against the actual tree (`scripts/`, `ml_classification/training/ml_trainers/`, `config/`). When adding new utilities, link to **real** paths or **`make help`** targets.

*Last updated through **Pass 22** (operations/architecture/code_review doc alignment; no code moves).*
