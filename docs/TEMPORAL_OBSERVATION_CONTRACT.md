# Temporal observation contract (v2.4.0)

**Contract version:** `1.0.0`  
**Modules:** `obsidiandroid.reporting.temporal_observation_contract`,
`obsidiandroid.reporting.temporal_permission_trends`

This is an observation-date framework, **not** APK creation dating.

## Precedence

1. first_seen_in_the_wild (when present and parseable)
2. first_discovered (when present and parseable)
3. first_analyzed / first submission (default coverage proxy)

Original source fields are retained. Platform-event annotations under
`config/research/android_platform_event_annotations_v1.json` are contextual
markers only; causal Android-update claims are not permitted.

## Offline generation

```bash
PYTHONPATH=src python scripts/diagnostics/generate_temporal_permission_trends.py \
  --run-root <completed-run-root> \
  --run-id 20260721T231415Z__e0c43b \
  --min-support 30
```

Outputs must not be committed.
