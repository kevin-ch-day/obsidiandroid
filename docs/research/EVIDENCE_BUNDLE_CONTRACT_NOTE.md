# Evidence Bundle Contract Note

This note defines the current output-governance contract for strict reproducibility runs.

## Directory Roles

- `output/runs/<run_id>/bundles/permission_trends/`: Full structural-analysis research bundle.
- `output/runs/<run_id>/diagnostics/`: QA, provenance, audits, and diagnostic artifacts.
- `output/runs/<run_id>/paper_exports/`: Strict publication-facing subset (evidence mode only).

## Table Role Taxonomy (Locked)

Allowed table roles in the permission-trends bundle manifest:

- `primary_structural`
- `auxiliary_table`
- `diagnostic_table`

Policy:

- Diagnostic tables are kept in `diagnostics/` only.
- Diagnostic tables must not appear under `bundles/permission_trends/tables/`.

## JSD Artifact Rule (Locked)

- `family_jsd_pairs_top{N}`: canonical audit/verification table.
- `family_jsd_matrix_top{N}`: render/visualization input table.

## CSV vs LaTeX Policy (Locked)

- Bundle CSV files are canonical research data artifacts.
- LaTeX table generation is limited to `paper_exports` in evidence mode.
- Bundle does not generate LaTeX tables by default.

## Bundle Contract Files

Under `bundles/permission_trends/contracts/`:

- `permission_trends_bundle_manifest.json`: machine-readable artifact contract.
- `permission_trends_table_inventory.csv`: governance inventory for table classification and usage.

## Validation Modes

- Full evidence-bundle validation: `python scripts/research/check_evidence_bundle.py --run-ids <run_id>`
- Bundle governance only (non-evidence runs): `python scripts/research/check_evidence_bundle.py --run-ids <run_id> --bundle-only`

## Publication Export Packaging (Locked)

Evidence-mode exports now include:

- `paper_exports/figures/` (5 locked figures)
- `paper_exports/tables/` (5 locked tables)
- `paper_exports/tables_latex/` (LaTeX derived from locked CSV tables only)
- `paper_exports/docs/paper_registry.json` (deterministic artifact mapping)

Validation enforces no fallback naming in publication-facing artifacts, including:

- no `.latest` names
- no `topN` table filenames
- no fallback stem usage in paper registry rows

## Legacy Naming Deprecation

Deprecated patterns:

- `*_topN` filename assumptions in downstream consumers.

Current policy:

- Prefer explicit `top{N}` stems when N is fixed by policy/profile.
- Backward-compatible readers may still accept legacy names for older runs.
- New runs should be consumed via canonical `artifact_id` lookups from bundle manifest.

Sunset timeline:

1. Current release: keep `topN` fallback readers.
2. Next release: emit deprecation warnings when fallback is used.
3. Following release: remove `topN` fallback support.
