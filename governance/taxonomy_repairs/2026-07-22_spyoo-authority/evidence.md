# Spyoo authority repair

    ## Research question

    Can the existing inactive `spyoo` family record be restored as current
    Android family authority with a researched `stalkerware` type, without adding
    aliases or changing mappings?

    ## Contemporaneous database evidence

    Before application, family 693 (`Spyoo`) was an inactive
    `lamda_catalog_gap_bootstrap` record typed `spyware`, with no aliases, no
    normalization target, and no canonical-source metadata. It had 1 catalog
    mapping(s). No active family slug or alias collision for `spyoo` was found.

    Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=693`

    ## Independent evidence

    - [Kaspersky stalkerware survey](https://securelist.com/beware-of-stalkerware/90264/) lists iSpyoo among commercial stalkerware products.
- Zscaler stalkerware reporting likewise tracks Spyoo-class commercial spyware apps.

    ## Impact and limitations

    The repair activates family 693 , remaps primary type from spyware (2) to stalkerware (17), adds source/review metadata only. It does not alter mappings.
