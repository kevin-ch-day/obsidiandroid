# Acecard authority repair

    ## Research question

    Can the existing inactive `acecard` family record be restored as current
    Android family authority with a researched `banker` type, without adding
    aliases or changing mappings?

    ## Contemporaneous database evidence

    Before application, family 317 (`Acecard`) was an inactive
    `lamda_catalog_gap_bootstrap` record typed `unknown`, with no aliases, no
    normalization target, and no canonical-source metadata. It had 1 catalog
    mapping(s). No active family slug or alias collision for `acecard` was found.

    Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=317`

    ## Independent evidence

    - [Kaspersky: Trojan-Banker.AndroidOS.Acecard](https://threats.kaspersky.com/en/threat/Trojan-Banker.AndroidOS.Acecard/) documents overlay phishing against banking apps plus SMS/call interception and GPS collection.
- [Kaspersky blog](https://www.kaspersky.com/blog/acecard-android-trojan/11368/) describes Acecard as a major Android banking Trojan family.

    ## Impact and limitations

    The repair activates family 317 , remaps primary type from unknown (8) to banker (12), adds source/review metadata only. It does not alter mappings.
