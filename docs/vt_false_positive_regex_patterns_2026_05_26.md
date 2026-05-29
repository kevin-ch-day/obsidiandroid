# VT False-Positive Regex Patterns

This note captures the structural false-positive patterns now visible in the
live Erebus review surface.

## Main Repeated Shapes

### 1. Installer / admin-tool labels

Examples:

- `DellRemoteAssist.exe`
- `Syn3Updater_1.0.0.1.exe`
- `Syn3Updater_1.0.0.2.exe`
- `UniFi-installer.exe`
- `winssh-pageant.exe`
- `winssh-pageant-v1.2_amd64.zip`
- `MixMaster.exe`
- `MixMaster Online.exe`
- `ZXPInstaller.Setup.exe`
- `StarCraft-II-Setup.exe`
- `unifi-video-v3.1.5-x64-installer.exe`

These often show up with only `1–2` VT detections and produce repeat review
churn. They are a better fit for narrowly scoped suppression than for repeated
manual review.

### 2. Generic detection names

Examples:

- `UNCLASSIFIED`
- `Phishing`
- `Banker Trojan`

These are not family candidates and should stay outside authority work.

### 3. Package/hash-like labels

Examples:

- hash-looking file names
- raw archive/doc names like `ace.jar`, `0612.doc`
- Android bundle names like `classes.dex`

These are strong signals that the review surface is carrying artifact-shape
noise rather than malware naming truth.

## Practical Use

1. Mine repeated exact labels from the `installer_or_admin_tool` bucket.
2. Suppress only the ones with clear public legitimacy and weak detections.
3. Keep ambiguous installers or mixed-signal tools out of broad suppression.
4. Keep Android family governance separate from mixed-platform installer/admin
   false-positive churn.

## SQL

Use:

- [vt_false_positive_regex_pattern_audit.sql](/home/secadmin/Laughlin/GitHub/obsidiandroid/database/sql/vt_false_positive_regex_pattern_audit.sql)
