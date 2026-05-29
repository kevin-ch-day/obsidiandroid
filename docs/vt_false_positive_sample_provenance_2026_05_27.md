# VT False-Positive Sample Provenance

Date: `2026-05-27`

This note records residual false-positive rows that were repairable only after
inspecting the raw VT payload, because the visible `sample_label` alone was too
generic.

Applied:

- [database/sql/vt_false_positive_suppression_tranche_2026_05_27_d.sql](/home/secadmin/Laughlin/GitHub/obsidiandroid/database/sql/archive/applied/2026-second-prune/vt_false_positive_suppression_tranche_2026_05_27_d.sql)

## Why sample scope was used

These rows had generic visible names like `Uninstall.exe` or `setup.exe`, so
label-pattern suppression would have been too broad. The raw VT payload under
`v_virustotal_file_report_event_hydrated.payload_json` exposed stronger product
metadata for the individual samples.

## Sample-scoped suppressions

### `sample_id=31152` `Uninstall.exe`

- VT raw meaningful name: `Uninstall.exe`
- product: `Ubiquiti UniFi Controller`
- description: `UniFi Controller`
- source of confidence: raw VT `signature_info`

Action:

- suppress by `sample` only

### `sample_id=32643` `WEXTRACT.EXE .MUI`

- VT raw meaningful name: `WEXTRACT.EXE            .MUI`
- product: `Internet Explorer`
- description: `Win32 Cabinet Self-Extractor`
- certificate chain present in VT raw payload

Action:

- suppress by `sample` only

Reason:

- this label has legitimate Microsoft provenance in this sample
- but the same filename shape is also used in malicious distribution chains, so
  global exact-label suppression would be too risky

### `sample_id=32673` `setup.exe`

- VT raw meaningful name: `setup.exe`
- product: `PC Building Simulator`
- description: `PC Building Simulator Setup`

Action:

- suppress by `sample` only

### `sample_id=31038` `PandaObfuscator.exe`

- VT raw meaningful name: `PandaObfuscator.exe`
- product: `Panda Obfuscator`
- description: `Panda Obfuscator`

Action:

- suppress by `sample` only

Reason:

- product metadata is strong enough for this specific sample
- publisher/signature evidence is not as strong as the Microsoft/Ubiquiti cases,
  so this remains sample-scoped rather than label-scoped
