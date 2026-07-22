# Congur authority repair

    ## Research question

    Can the existing inactive `congur` family record be restored as current
    Android family authority with a researched `ransomware` type, without adding
    aliases or changing mappings?

    ## Contemporaneous database evidence

    Before application, family 356 (`Congur`) was an inactive
    `lamda_catalog_gap_bootstrap` record typed `unknown`, with no aliases, no
    normalization target, and no canonical-source metadata. It had 1 catalog
    mapping(s). No active family slug or alias collision for `congur` was found.

    Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=356`

    ## Independent evidence

    - [NHS Digital: Congur Android Ransomware](https://digital.nhs.uk/cyber-alerts/2018/cc-2039) documents PIN-reset device locking, data theft, and botnet abuse.
- Kaspersky Q1 2017 mobile ransomware reporting identified Congur as a dominant Android ransomware family.

    ## Impact and limitations

    The repair activates family 356 , remaps primary type from unknown (8) to ransomware (4), adds source/review metadata only. It does not alter mappings.
