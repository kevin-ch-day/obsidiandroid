# BianLian Scope Review

Date: 2026-05-29

## Summary

`BianLian` in ObsidianDroid should remain scoped to the Android banking malware
family.

The external material currently mixed under the `BianLian` name spans two
different malware contexts:

1. Android banker / botnet material
2. desktop/server ransomware or backdoor material

Those should not be ingested into the same Android family queue.

## Android BianLian

Primary Android sources:

- Fortinet, `BianLian: A New Wave Emerges`:
  https://www.fortinet.com/blog/threat-research/new-wave-bianlian-malware
- Fortinet, `Android/Bianlian Botnet Trying to Bypass Photo TAN Used for Mobile Banking`:
  https://www.fortinet.com/blog/threat-research/android-bianlian-botnet-mobile-banking
- ThreatMark, Android banking malware comparison mentioning BianLian:
  https://www.threatmark.com/new-android-banking-malware/
- ThreatFabric, Android dropper evolution:
  https://www.threatfabric.com/blogs/bianlian_from_rags_to_riches_the_malware_dropper_that_had_a_dream

Key points from the Android side:

- Android `BianLian` is a banker / dropper line first discussed in 2018.
- It abuses Accessibility Services, overlays, SMS, USSD/call features, screen
  capture, and remote-control style behavior.
- Fortinet explicitly says the helper `payload.apk` in the 2019 sample is not a
  separate malware family by itself.
- Fortinet's 2019 note also includes a separate `Anubis` sample only to discuss
  shared obfuscation, not family identity.

Safe Android family IOCs from the provided set:

- `ac32dc236fea345d135bf1ff973900482cdfce489054760601170ef7feec458f`
- `a3b826de0c445f0924c50939494a26b0d99ef3ccac80faacca98673625656278`

Not staged as Android family truth:

- `75e162dc291e15d13b0f3202a66e0c88ff2db09ec02922ee64818dbddcb78d6d`
  - helper payload from the Fortinet 2019 Android post
- `a99eb900d03aa1dd70d7712da7c42cc37ee2f2e21d763acd6ddf71a4027ed504`
  - Anubis sample from the Fortinet 2019 Android post

## Non-Android BianLian

The Unit42 page provided is about the ransomware/backdoor actor and encryptor
tooling, not Android banker samples:

- Unit42, `BianLian Ransomware Group Threat Assessment`:
  https://unit42.paloaltonetworks.com/bianlian-ransomware-group-threat-assessment/

The hashes listed there for encryptors, backdoors, and `Advanced Port Scanner`
should not be queued into ObsidianDroid as Android family ingest.

## Local repo / DB implications

- Keep `BianLian` governed as the Android family already promoted in
  `android_malware_family`.
- Stage only Android banker IOCs into `malware_artifact_ingest_queue`.
- Treat desktop/server `BianLian` material as out of scope for Android family
  authority and ingest.
