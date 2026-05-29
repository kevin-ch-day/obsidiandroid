# BlackRock Research Note

## Conclusion

BlackRock should remain a distinct canonical Android banking family.
The source-backed relationship is ancestry, not synonymy:

- `BlackRock` is derived from `Xerxes`.
- `Xerxes` is a LokiBot-descended family in its own right.
- The repo should keep `BlackRock` and `Xerxes` separate and use lineage metadata for the relationship.

## Source-backed points

- ThreatFabric states that BlackRock was uncovered in May 2020 and derived from the Xerxes banking malware.
- ThreatFabric also says Xerxes is part of the LokiBot descendance and that BlackRock was the only Android banking Trojan based on Xerxes observed at the time.
- ThreatFabric’s lineage chain is:
  - LokiBot first appeared in late 2016 / early 2017.
  - Parasite followed in late 2018 as a direct successor in the same lineage.
  - Xerxes appeared in May 2019 and was later made public.
  - BlackRock appeared in May 2020 and was derived from Xerxes.
- The repository currently has no governed `Parasite` family row, so that upstream step is a research note only for now, not an active taxonomy node.
- BlackRock’s behavior is broad: overlays, keylogging, SMS theft, notifications, AV evasion, device-admin abuse, and a notably large target list that extends beyond banking apps into social, communication, lifestyle, dating, and shopping apps.

## Local repository state

- `BlackRock` is already a canonical family in `src/obsidiandroid/labeling/malware_family_constants.py`.
- `Xerxes` is already governed as its own canonical family in the authority SQL.
- A lineage edge now exists in the live DB:
  - `BlackRock -> Xerxes` with `relation_type = derived_from`

## Operational implication

- Do not add a family alias between `BlackRock` and `Xerxes`.
- Keep any future cleanup in the lineage layer, not the alias layer.
- Treat BlackRock as an evolution in capability and targeting breadth, not a replacement name for LokiBot or Xerxes.
- If `Parasite` is introduced later, model it as a separate lineage node upstream of Xerxes instead of folding it into BlackRock.

## Sources

- ThreatFabric, *BlackRock - the Trojan that wanted to get them all*:
  https://www.threatfabric.com/blogs/blackrock_the_trojan_that_wanted_to_get_them_all
- ThreatFabric, *LokiBot - The first hybrid Android malware*:
  https://www.threatfabric.com/blogs/lokibot_the_first_hybrid_android_malware
