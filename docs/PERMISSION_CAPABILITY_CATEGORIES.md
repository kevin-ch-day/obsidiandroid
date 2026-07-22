# Permission capability categories (v2.4.0)

**Contract version:** `1.0.0`  
**Module:** `obsidiandroid.reporting.permission_capability_categories`

Capability categories are orthogonal to Android protection / governance lanes.
Static permission declarations do not prove runtime behavior.

## Categories

See `CANONICAL_CAPABILITY_CATEGORIES` in source. Multi-label assignment occurs
only via `EXPLICIT_PERMISSION_CAPABILITY_MAP`.

## Offline generation

```bash
PYTHONPATH=src python scripts/diagnostics/generate_permission_capability_categories.py \
  --run-root <completed-run-root> \
  --run-id 20260721T231415Z__e0c43b
```

Outputs are run-scoped under `diagnostics/permission_capability_categories/`
(or `--output-dir`) and must not be committed.
