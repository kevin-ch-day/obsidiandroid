# Alien vs AlienBot Research Pass

Date: 2026-05-28

## Bottom line

Current evidence supports treating `AlienBot` as a naming surface of `Alien`, not as a separately governed Android banker family.

## Source-backed findings

1. ThreatFabric documented `Alien` in September 2020 as the Cerberus-line banker that rose as Cerberus declined.
2. Check Point documented a March 2021 Google Play dropper campaign that delivered `AlienBot Banker`.
3. Reference/institutional sources use the names interchangeably:
   - INCIBE: `Alien`, also known as `AlienBot`
   - PCRisk: `AlienBot (or simply Alien) Banker`

These are not all equal in authority, but together they point to a naming split around the same banker family rather than two strongly separate families.

## Sources used

- ThreatFabric / Security Insight mirror, `Alien - The Story of Cerberus' Demise`, 2020-09-24  
  https://securityinsight.nl/blog/alien-the-story-of-cerberus-demise
- Check Point Research, `Clast82 – A new Dropper on Google Play Dropping the AlienBot Banker and MRAT`, 2021-03-09  
  https://research.checkpoint.com/2021/clast82-a-new-dropper-on-google-play-dropping-the-alienbot-banker-and-mrat/
- CSO Online summary quoting ThreatFabric on Alien as a Cerberus fork  
  https://www.csoonline.com/article/569929/android-malware-alien-a-rising-threat-to-mobile-banking-users.html
- INCIBE `Alien` reference  
  https://www.incibe.es/servicio-antibotnet/info/Alien

## Local catalog findings

Android catalog footprint:

- `Alien`: 28 rows
- `AlienBot`: 1 row

Authority state before normalization:

- canonical `alien` existed
- canonical `alienbot` existed
- no `alienbot -> alien` alias fact existed

The only local `AlienBot` row:

- sample `355`
- `family_label = AlienBot`
- `sample_label = AlienBot`
- `vt_suggested_label = trojan.hqwar/bankbot`
- `classification_primary = Trojan`
- `classification_subtype = Banker`

This row had no existing sample-family mappings and no other DB dependencies on the `alienbot` canonical family.

## Applied data change

Normalization file:

- [alien_alienbot_normalization_2026_05_28_a.sql](/home/secadmin/Laughlin/GitHub/obsidiandroid/database/sql/archive/applied/2026-second-prune/alien_alienbot_normalization_2026_05_28_a.sql)

This pass:

1. adds accepted alias `alienbot -> alien`
2. adds alias fact `alienbot -> alien`
3. repairs sample `355` from `AlienBot` to `Alien`
4. seeds an accepted exact catalog-family mapping for repaired sample `355`

## Recommended policy

1. Use `Alien` as the canonical family.
2. Treat `AlienBot` as an accepted alias surface of `Alien`.
3. Keep Cerberus-lineage modeling separate:
   - `alien` remains Cerberus-lineage context, but not a Cerberus synonym.
4. Do not create a distinct `AlienBot` active family slice unless a materially separate body of source-backed samples appears later.
