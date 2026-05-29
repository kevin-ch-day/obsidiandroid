# VT False-Positive Triage View

Date: `2026-05-27`

This pass adds a companion triage surface over the suppression-aware effective
false-positive queue:

- [database/sql/create_vt_false_positive_review_candidates_triage.sql](/home/secadmin/Laughlin/GitHub/obsidiandroid/database/sql/create_vt_false_positive_review_candidates_triage.sql)

Live view name:

- `v_vt_false_positive_review_candidates_triage`

## Why this view exists

The effective false-positive queue is now small enough that its main problem is
not raw size. It is mixed semantics:

- real malware-family low-consensus rows
- generic placeholders
- artifact/hash/file-name residue
- ambiguous legit-software / installer residue

Those are different QA problems and should not share one flat analyst lane.

## Triage lanes

- `real_malware_family_or_class_review`
  - keep analyst-visible
  - current examples: `Gigabud`, `Banker Trojan`

- `generic_placeholder_review`
  - likely needs reclassification or explicit placeholder handling
  - current examples: `UNCLASSIFIED`, `Phishing`

- `legit_software_or_installer_review`
  - requires stronger provenance before suppression
  - current examples:
    - `WEXTRACT.EXE            .MUI`
    - `PandaObfuscator.exe`
    - `libWBP122.dll`
    - `Uninstall.exe`
    - `setup.exe`

- `file_artifact_review`
  - filename-based residue, often weak context

- `hash_artifact_review`
  - hash-shaped or artifact-shaped labels

- `other_review`
  - catchall for manual handling

## Current live shape

At creation time the lane counts were:

- `real_malware_family_or_class_review`: `17`
- `file_artifact_review`: `15`
- `generic_placeholder_review`: `9`
- `hash_artifact_review`: `7`
- `legit_software_or_installer_review`: `5`
- `other_review`: `3`

This view does not suppress anything by itself. It is a repair/QA routing
surface only.
