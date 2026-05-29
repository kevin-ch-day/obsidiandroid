# Android Banker Family Gap Review

This note compares a provided Android banker family list against the current governed
`android_malware_family` table and the live `malware_sample_catalog`.

## Already governed as Android families

- `Anubis`
- `BankBot`
- `BrasDex`
- `Cerberus`
- `Coper`
- `EventBot`
- `FluBot`
- `GINP`
- `Marcher`
- `Medusa`
- `MysteryBot`
- `Nexus`
- `Octo`
- `PixBankBot`
- `SharkBot`
- `TeaBot`
- `Xenomorph`

## Governed through alias / lineage handling

- `Cabassous`
  - modeled as a retired canonical with accepted normalization to `FluBot`
- `ExobotCompact.D`
  - currently handled as an alias surface on the `Octo` branch, not a separate canonical

## True Android family gap fixed in this pass

- `BianLian`
  - local catalog already had Android banker rows with `family_label = BianLian`
  - the repo was missing a canonical Android family row
  - a prior generic-token suppression for `bianlian` was incorrect and should be retired

## Not Android-governed from current local evidence

- `Emotet`
  - current local rows are Windows / document-downloader debt, not Android-family evidence
- `QakBot`
  - no local Android-family evidence in the current catalog
- `Zbot`
  - no local Android-family evidence in the current catalog

## Still research candidates, but not promoted in this pass

- `Elibomi`
- `Svpeng`

Those may be legitimate Android families, but they were not promoted here because the
current local DB slice did not already contain governed-family rows or enough direct
local evidence to add them safely without a dedicated source pass.
