# Plague authority repair

    ## Research question

    Can the existing inactive `plague` family record be restored as current
    Android family authority with a researched `adware` type, without adding
    aliases or changing mappings?

    ## Contemporaneous database evidence

    Before application, family 516 (`Plague`) was an inactive
    `lamda_catalog_gap_bootstrap` record typed `unknown`, with no aliases, no
    normalization target, and no canonical-source metadata. It had 1 catalog
    mapping(s). No active family slug or alias collision for `plague` was found.

    Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=516`

    ## Independent evidence

    - [Kaspersky Securelist](https://securelist.com/pig-in-a-poke-smartphone-adware/97607/) documents AdWare.AndroidOS.Plague displaying overlay/notification ads and silent installs.
- [CIC AndMal2020](https://www.unb.ca/cic/datasets/andmal2020.html) lists Plague among adware families.

    ## Impact and limitations

    The repair activates family 516 , remaps primary type from unknown (8) to adware (3), adds source/review metadata only. It does not alter mappings.
