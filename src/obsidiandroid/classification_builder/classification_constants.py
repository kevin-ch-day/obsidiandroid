# Filename: ml_classification/builder/classification_constants.py
# Purpose : Centralized constants for classification enrichment and normalization

# Whitelist of engines considered reliable for variant field enrichment
TRUSTED_VARIANT_ENGINES = {
    "AhnLab_V3",
    "Alibaba",
    "Avast",
    "Avast-Mobile",
    "BitDefender",
    "BitDefenderFalx",
    "K7GW",
    "Kaspersky",
    "Microsoft"
}

# Normalize various alias traits into consistent tagging language
TRAIT_TAG_ALIASES = {
    "spyware": "spy",
    "spynm": "spy",
    "spynote": "spy",
    "banker": "banker",
    "sms-trojan": "sms",
    "smstrojan": "sms",
    "dropper": "dropper",
    "installer": "dropper",
    "backdoor": "backdoor",
    "rat": "remote-access",
    "ransomware": "ransom",
    "fakeapp": "fake",
    "phish": "phishing",
    "adware": "adware",
    "tool": "hacking-tool",
    "pup": "unwanted",
    "gen": "generic",
    "heur": "heuristic",
    "malware": "malware"
}
