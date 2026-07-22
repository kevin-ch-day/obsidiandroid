# Kuguo type lifecycle repair

## Research question

Can the already-active `kuguo` family keep its current identity while remapping
its primary type from the retired `pua` type to the active `adware` type,
without creating aliases, changing sample mappings, or reactivating `pua`?

## Contemporaneous database evidence

Before application, family 80 (`Kuguo`) was an active authority family whose
`primary_type_id` pointed at retired type 19 (`pua`). It had 689 catalog
mappings and about 670 authority-visible samples under the retired type. No
normalization target was set.

Database locator: `database://erebus_threat_intel_prod/android_malware_family?family_id=80`

## Independent evidence

- [Dr.Web: Adware.Kuguo.5](https://vms.drweb.com/virus/?i=17938587)
  classifies Kuguo as adware and documents adware-family behavior.
- [AMD deep ground-truth analysis (2017)](http://www.arguslab.org/documents/tech_reports/2017/amd_fgwei_2017.pdf)
  groups Kuguo with adware/PUA advertising families (with Dowgin, Youmi, Airpush).
- [SANER 2019 adware-as-malware study](https://jacquesklein2302.github.io/papers/2019-saner19era-id277-p-960b992-39643-final.pdf)
  treats Kuguo as a well-known adware-family identity.
- Microsoft still detects related samples under PUA-named signatures; that vendor
  naming is retained as supporting identity evidence, not as a reason to keep
  the retired local `pua` type active.

## Impact and conservative action

The repair remaps only `primary_type_id` from retired `pua` (19) to active
`adware` (3) and records review metadata. It retains family ID 80, leaves
mappings and aliases untouched, does not reactivate `pua`, and does not run a
benchmark. Expected effect: authority-visible Kuguo samples report `adware`
instead of the retired `pua` type.

## Rejected alternatives

- Reactivating `pua` would restore a retired governed type for one family.
- Retiring/deactivating `kuguo` would discard a high-volume adware identity.
- Remapping to `riskware` or `trojan` would contradict the adware consensus.

## Limitations

External sources support family identity and adware placement. This repair does
not assert every mapped sample's behavior, create a frozen benchmark artifact,
or change model features.
