# Alltracker authority repair

    ## Research question

    Can the existing inactive `alltracker` family record be restored as current
    Android family authority with a researched `stalkerware` type, without adding
    aliases or changing mappings?

    ## Contemporaneous database evidence

    Before application, family 326 (`Alltracker`) was an inactive
    `lamda_catalog_gap_bootstrap` record typed `unknown`, with no aliases, no
    normalization target, and no canonical-source metadata. It had 1 catalog
    mapping(s). No active family slug or alias collision for `alltracker` was found.

    Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=326`

    ## Independent evidence

    - Spreitzenbarth catalogs AccuTrack-style apps that turn phones into covert GPS trackers.
- [CIC AndMal2020](https://www.unb.ca/cic/datasets/andmal2020.html) includes AccuTrack among adware/monitoring-adjacent families; AllTracker is the matching commercial monitoring brand identity in the local catalog.

    ## Impact and limitations

    The repair activates family 326 , remaps primary type from unknown (8) to stalkerware (17), adds source/review metadata only. It does not alter mappings.
