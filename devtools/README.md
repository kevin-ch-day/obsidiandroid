# `devtools/` (compatibility shims)

**Implementations moved to [`scripts/dev/`](../scripts/dev/).**

- **Synthetic data fuzzer:** [`scripts/dev/data_fuzzer.py`](../scripts/dev/data_fuzzer.py) — `devtools/data_fuzzer.py` re-exports it for tests (`from devtools import data_fuzzer`).
- **ML `.predict()` scan:** [`scripts/dev/scan_ml_predict_misuse.py`](../scripts/dev/scan_ml_predict_misuse.py) — used by [`run_ml_static_scan.py`](../run_ml_static_scan.py).

Developer-only tooling; not production pipeline stages. Not shipped as `obsidiandroid` API surface.
