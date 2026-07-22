# Obad authority repair

    ## Research question

    Can the existing inactive `obad` family record be restored as current
    Android family authority with a researched `backdoor` type, without adding
    aliases or changing mappings?

    ## Contemporaneous database evidence

    Before application, family 497 (`Obad`) was an inactive
    `lamda_catalog_gap_bootstrap` record typed `adware`, with no aliases, no
    normalization target, and no canonical-source metadata. It had 1 catalog
    mapping(s). No active family slug or alias collision for `obad` was found.

    Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=497`

    ## Independent evidence

    - [AWAKE Obad](https://awakewiki.org/malware/families/obad/) summarizes Kaspersky Backdoor.AndroidOS.Obad as a multi-function Android backdoor using Device Admin exploits, premium SMS, proxying, and remote shell.
- [ZDNet](https://www.zdnet.com/article/first-case-of-android-trojan-spreading-via-mobile-botnets-discovered/) covers Obad botnet-based mobile distribution.

    ## Impact and limitations

    The repair activates family 497 , remaps primary type from adware (3) to backdoor (6), adds source/review metadata only. It does not alter mappings.
