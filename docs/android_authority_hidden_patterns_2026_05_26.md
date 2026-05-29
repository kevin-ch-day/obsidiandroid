## Hidden-pattern note

This note captures the current residual Android authority tail after the May 26, 2026 family and token curation passes.

### Main pattern

The residual unresolved surface is no longer dominated by obvious descriptor noise. After the latest regex-driven policy tranches, the tail breaks into two classes:

- a `missing_resolved_family` package-heavy bucket led by `<blank>` tokens from `raw_hash_reservoir_20260520`
- a small set of short, family-looking tokens that still need family research rather than more suppression

### What regex found

The strongest missed patterns were not new families. They were class-like or malformed tokens that still looked family-like because they were lowercase and compact:

- `infostealer`
- `spanishbanker`
- `banker trojan`
- `masquerading malware`
- `ransomware`
- `fraud financial apps`
- `hiddenadware`
- `trojan.boogr`
- `threatsfromiran`
- `msoftransomware`

Those are now policy-held in `vendor_label_generic_token_fact`.

### What remains after policy cleanup

The residual short-token queue is now mostly:

- `coro`
- `andup`
- `beitaad`
- `blur`
- `botnetrogue`
- `bouncinggolf`
- `coybolt`
- `coybot`
- `dorxor`
- `escobar`
- `fklz`
- `flexnet`
- `maypacker`
- `nexus`
- `oscorp`
- `rainbowmix`
- `rampantkitten`
- `rustdesk`
- `smseye`
- `tekya`
- `telerat`
- `thiefbot`
- `venus`
- `wolfrat`
- `xavier`
- `xerxes`
- `zombinder`

These should not be flattened by regex alone. They need one of:

- real family research
- alias-to-existing-family review
- campaign/dropper/service classification

### External signals that changed interpretation

- `Zombinder` is described by ThreatFabric as a dropper/binding service used to distribute Android malware rather than a canonical payload family:
  - https://www.threatfabric.com/blogs/zombinder-ermac-and-desktop-stealers
  - https://www.threatfabric.com/blogs/android-droppers-the-silent-gatekeepers-of-malware

- `TeleRAT` is documented by ESET as an Android RAT family, and related Telegram-abusing Android RAT activity can branch into other named families:
  - https://www.welivesecurity.com/2018/06/18/new-telegram-abusing-android-rat/

- `Tekya` is a documented Android ad-fraud / click-fraud family rather than a generic adware descriptor:
  - Check Point Research coverage was the useful reference during this pass.

### Operational implication

The next lift should not be another broad regex cleanup. The regex work has already removed most descriptor-class leakage. The remaining high-value work is:

1. family-candidate research on short lowercase tokens
2. service/dropper/campaign classification for tokens like `zombinder`
3. separate handling of the `raw_hash_reservoir_20260520` `<blank>` package cluster
