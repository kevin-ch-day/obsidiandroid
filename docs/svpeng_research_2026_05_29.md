# Svpeng Research Note

## Summary

`Svpeng` should be present in the governed Android family authority as a distinct
Android banking trojan family.

## Why it belongs in Android authority

- Kaspersky tracks `Trojan-Banker.AndroidOS.Svpeng` as an Android banking trojan
  family that overlays banking interfaces and steals financial data.
- Malwarebytes documented Svpeng as an Android trojan with phishing and banking
  credential theft behavior.
- The family is long-lived and well-established enough that it should not remain
  absent from the canonical Android family list simply because the current local
  catalog slice has no direct rows for it.

## Policy

- add `Svpeng` as a canonical Android family
- keep it separate from ransomware-only or desktop malware groupings
- do not infer lineage from the current local slice without stronger sourcing

## Sources

- Kaspersky Threats, *Trojan-Banker.AndroidOS.Svpeng*:
  https://threats.kaspersky.com/en/threat/Trojan-Banker.AndroidOS.Svpeng/
- Malwarebytes Labs, *Android Trojan gets an update*:
  https://www.malwarebytes.com/blog/news/2013/11/android-trojan-gets-an-update
