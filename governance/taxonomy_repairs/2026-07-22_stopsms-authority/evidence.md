# Stopsms authority repair

    ## Research question

    Can the existing inactive `stopsms` family record be restored as current
    Android family authority using its existing `sms-trojan` type, without adding
    aliases or changing mappings?

    ## Contemporaneous database evidence

    Before application, family 285 (`Stopsms`) was an inactive
    `lamda_catalog_gap_bootstrap` record typed `sms-trojan`, with no aliases, no
    normalization target, and no canonical-source metadata. It had 9 catalog
    mapping(s). No active family slug or alias collision for `stopsms` was found.

    Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=285`

    ## Independent evidence

    - [CIC AndMal2020](https://www.unb.ca/cic/datasets/andmal2020.html) lists StopSMS among Android adware-capture families (26 samples), co-occurring with SMS-trojan style monetization in corpus literature.
- [KronoDroid/MDPI](https://www.mdpi.com/2673-6470/6/1/5) treats Airpush/StopSMS as a major Android family involving SMS-trojan behavior.

    ## Impact and limitations

    The repair activates family 285 and adds source/review metadata only. It does not alter mappings.
