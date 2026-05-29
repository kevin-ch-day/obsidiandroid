# Metasploit Label Review

## Conclusion

`metasploit` and `meterpreter` should remain policy-held generic / behavior tokens, not
canonical Android malware families.

## Why

- Malwarebytes states that `Trojan.MetaSploit` is its generic detection name for
  trojans based on the Metasploit framework.
- SonicWall's Android write-up describes a set of Android APKs carrying Metasploit
  framework components and the `com.metasploit.stage` package, which is tooling /
  payload evidence rather than a stable family identity.

That means these labels are useful as operator evidence, but they should not be promoted
into `android_malware_family`.

## Local effect

- `metasploit` and `meterpreter` were already correctly policy-held in
  `vendor_label_generic_token_fact`
- one catalog row still carried `family_label = MetasploitZoom`
- that label was already separately policy-held as `metasploitzoom`

The correct fix is to remove `MetasploitZoom` from the governed family surface while
preserving the raw sample label as evidence.

## Sources

- Malwarebytes, *Trojan.MetaSploit*:
  https://www.malwarebytes.com/blog/detections/trojan-metasploit
- SonicWall, *Metasploit enhanced Android malware spotted in the wild*:
  https://www.sonicwall.com/blog/metasploit-enhanced-android-malware-spotted-in-the-wild-april-15-2016
