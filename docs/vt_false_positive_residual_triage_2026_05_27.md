# VT False-Positive Residual Triage

Date: `2026-05-27`

This pass focused on the remaining
`v_vt_false_positive_review_candidates_effective` residue and used external
context to separate:

- strong exact-label suppressions
- plausible but still ambiguous legit-software rows
- rows that should remain analyst-visible

## Safe exact-label action applied

Applied:

- [database/sql/vt_false_positive_suppression_tranche_2026_05_27_a.sql](/home/secadmin/Laughlin/GitHub/obsidiandroid/database/sql/archive/applied/2026-second-prune/vt_false_positive_suppression_tranche_2026_05_27_a.sql)
- [database/sql/vt_false_positive_suppression_tranche_2026_05_27_b.sql](/home/secadmin/Laughlin/GitHub/obsidiandroid/database/sql/archive/applied/2026-second-prune/vt_false_positive_suppression_tranche_2026_05_27_b.sql)
- [database/sql/vt_false_positive_suppression_tranche_2026_05_27_c.sql](/home/secadmin/Laughlin/GitHub/obsidiandroid/database/sql/archive/applied/2026-second-prune/vt_false_positive_suppression_tranche_2026_05_27_c.sql)

Label suppressed:

- `t3sigs.vdb`
- `EZDetach7_setup.exe`
- `SodaPDFDesktop12.exe`

Why this was safe:

- IKARUS official documentation explicitly references `t3sigs.vdb` as the
  signature/VDB path for IKARUS anti.virus.
  - https://www.ikarussecurity.com/wp-content/downloads/IKARUS_antivirus_manual_en.pdf
- additional software-distribution references consistently describe it as the
  Ikarus engine/signature update artifact.
  - https://www.softpedia.com/get/Others/Signatures-Updates/Ikarus-Engine-Update.shtml

For `EZDetach7_setup.exe`:

- TechHit’s official product site clearly documents EZDetach as a legitimate
  Outlook attachment utility.
  - https://www.techhit.com/ezdetach/outlook_attachments.html
  - https://www.techhit.com/ezdetach/order.html
- sandbox reports label the installer as malicious, but the observed behaviors
  are also consistent with an NSIS-style installer, COM registration, browser
  launch, and shell integration rather than a malware-family clue.
  - https://hybrid-analysis.com/sample/94b6283d0025d702395313dff8576f347e10b95efe630d7b37c7d704fda0ee58?environmentId=100

For `SodaPDFDesktop12.exe`:

- multiple references tie the exact filename to the Soda PDF Desktop 12
  installer lineage from LULU Software / Soda PDF installation paths
  - https://softwaretested.com/file-library/file/sodapdfdesktop12.exe-lulu-software/
  - https://www.revouninstaller.com/preview-log/?pid=10167&pname=Soda
  - https://www.tenforums.com/general-support/190437-no-delete.html

Conclusion:

- safe enough for exact-label suppression
- not strong enough to justify any broader `setup.exe` or generic installer rule

## Strong malware-family residue that should stay visible

- `Gigabud`
  - documented Android malware family
  - should not be suppressed as a false positive
  - sources:
    - https://malpedia.caad.fkie.fraunhofer.de/details/apk.gigabud
    - https://zahidaz.github.io/awake/malware/families/gigabud/

## Ambiguous rows intentionally left unsuppressed

### `WEXTRACT.EXE .MUI`

Evidence cuts both ways:

- there are legitimate Microsoft-signed `wextract.exe.mui` / `WEXTRACT.EXE .MUI`
  binaries in Windows distributions
  - example references:
    - https://www.herdprotect.com/wextract.exe-f8f1217f666bf2f6863631a7d5e5fb3a8d1542df.aspx
    - https://strontic.github.io/xcyclopedia/library/wextract.exe-EF82872F2141313EF07C49405145DF3B.html
- but threat reports also show the same filename shape used in malware
  distribution campaigns
  - example:
    - https://files.passle.net/Passle/602651b953548812c0fa5fe2/MediaLibrary/Document/2024-08-01-15-52-06-960-CTIXFLASHWrap-Up-July2024.pdf

Conclusion:

- do not blanket-suppress this exact label yet
- keep as review-only unless we can verify signer/provenance on the local row

### `SodaPDFDesktop12.exe`

## Android rows that should remain analyst-visible

Do not suppress these as generic FP noise without stronger package-level
evidence:

- `Banker Trojan` on `com.gamecenter.android`
- `NEXTA LIVE.apk`
- `com.goyal.trzorwallet-1.apk`
- `8.apk`

These are low-consensus, but the package and lure context remain too suspicious
to classify as likely-legit without deeper sample-level review.
