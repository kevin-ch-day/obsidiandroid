# `data_inspect/` (compatibility shims)

**Inspection scripts have moved to [`scripts/diagnostics/`](../scripts/diagnostics/).**

This directory retains **thin modules** that re-export from `scripts.diagnostics.*` so legacy imports keep working, for example:

- `from data_inspect import inspect_classification_results`
- `python data_inspect/inspect_complexity_hotspots.py` (runs the shim; prefer `python scripts/diagnostics/inspect_complexity_hotspots.py`)

For documentation of each script, see [`scripts/diagnostics/README.md`](../scripts/diagnostics/README.md).
