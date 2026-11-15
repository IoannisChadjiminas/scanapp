# English titles of scraped Japanese rows, switched on staging (2026-11-15)

`view_title` is the English title the server shows, uses to group same-art Japanese printings (`PRINTING_TITLE_FAMILY`)
and the phone index exports as `alt_name`. On 131 `ja:` rows it held text scraped from a Cardmarket page instead of a
title:
- 121 rows like `Ultra Ball (BKW 010)From N/A` (Japanese promos, e-Card, PCG, MMB and BW-P energies).
- 10 rows like `L18:  【30†Image: Palossand-GX` (`ja:SMP-104`, `ja:20th-041` `L80: Mime`, …).

The owner approved fixing them through a gated release ("ok do"). TITLES1 sets 128 of them; 3 are held. Production
is not touched. Names, vectors, ids, images, links and both bundles are unchanged.

## Switch

| Item | Value |
|---|---|
| Release | `PS-CATALOGUE-EN-JA-TITLES1-20261115`, schema `pokesingle_completion_20261115_titles1` |
| Parent | `PS-CATALOGUE-EN-JA-LINKS3-20261115` (`pokesingle_completion_20261114_links3`), see `docs/catalogue-names-families-20261114.md` |
| SQL | `prepare_sql_fixes.py` with `FIX_KEY=scraped_titles_20261115`: 211 statements in one guarded transaction, sha256 `c5de971186c037beabb1babc060a12b303de3e5bf9c038840818ad89934dabab`; 128 cards updated, cards md5 `118d29f95645280699f72542e5203c65` |
| How | `scripts/catalogue-release-switch.sh apply`, `RELEASE_NAME=catalogue-titles-20261115` on 2026-11-15. Only `PLANETSCALE_SCHEMA` and `PLANETSCALE_IMPORT_ID` of the env file changed (checked line by line against the live file) |
| After | health ok, ready, restarts 0, no OOM |
| Rollback | `/etc/scanapp-staging/catalogue-rollback/catalogue-titles-20261115` (rollback file points to LINKS3) |

## What changed

Every row is listed in `docs/catalogue-titles-20261115.tsv` (old title, new title, how).

| How | Rows | Example |
|---|---:|---|
| Title inside the scraped text, equal to the catalogue's English title for that Japanese name | 98 | `ja:BKW-010` ハイパーボール: `Ultra Ball` |
| Title inside the scraped text, no other row to compare with, checked by eye | 11 | `ja:E4-079` オラクル: `Oracle`; `ja:SMP-104` シロデスナGX: `Palossand GX` |
| Basic energies in the catalogue's style | 11 | `ja:BWP-071` 基本草エネルギー: `Grass Energy` → `Basic Grass Energy` |
| From the Japanese name, because the scraped text names another card | 8 | `ja:SV-P-155` タイカイデンex: `Pikachu ex` → `Kilowattrel ex` |
| Held | 3 | see below |

The eight from the Japanese name: `ja:M6-048` Mega Malamar ex, `ja:SV-P-155` Kilowattrel ex, `ja:SV-P-165` Veluza ex,
`ja:SV-P-210` Scizor ex, `ja:SV-P-254` Ethan's Ho-Oh ex, `ja:SV-P-258` Bloodmoon Ursaluna ex, `ja:SV10-082` Team
Rocket's Porygon2, and `ja:SMP-263` Tauros GX (its scraped `Tauros-GX` was right but in another style).

Held, title left as it was:
- `ja:MDB-045` ブレンドエネルギー 草炎超悪: the Japanese name says GRPD (草炎超悪), the scraped text and link say GFPD.
- `ja:PCG3-020` トーチの星: the text and link say `Torchic Gold Star`, but the Japanese name itself looks wrong.
- `ja:PCG4-047` 未知: the text says `Unown [E]`; the Japanese name has no letter to check it against.

## Gate

1,891 photos replayed against TITLES1 (local docker, image `scanapp-api-staging:24856ba9`, 3 lanes, all eleven lanes
exited 0 with every row), scored against K3's accepted run with `score_gate.py`.

| Panel | Photos | Right first | Wrong first | Right offered | Wrong-first upper bound |
|---|---:|---|---|---|---:|
| dev | 681 | 637 → 637 | 4 → 4 | 663 → 663 | 1.5% |
| dev2 | 238 | 232 → 232 | 0 → 0 | 238 → 238 | 1.6% |
| dev3 | 972 | 938 → 938 | 0 → 0 | 963 → 963 | 0.4% |

Right → wrong: 0. Right no longer offered: 0. Cells lower: none. The 96 changed answers against K3 are the same 96 as
LINKS3's, and all 1,891 answers (status, best, suggestions, alternatives, printing) are identical to the LINKS3 run:
no panel photo meets a changed title.

## Phone index

| Item | Value |
|---|---|
| Before | `07e3a028571c086d8b3a4fd6d2c7cc4e067065a863bef8a52f1a884cef7e9adb` |
| Now | `e19e142e80eac95b620efa1ad3adc67a2c9e9e78f33f830b229a004d410c9a62`, 48,934 rows |
| Same as before | ids file and float16 vectors byte for byte; in `card_index.meta.tsv` only `alt_name` changed, on 126 rows (the other 2 fixed rows have no vector) |
| Rollback record | `/etc/scanapp-staging/catalogue-rollback/phone-index-titles-20261115/ACTIVE.before` |
| Check | manifest 200 inside the container and from `staging-scan.pokesingle.com`; meta, ids and version files download with the manifest's sha256; a ranged request on the vectors returns 206 and the whole file matches |

Built from a local snapshot export of TITLES1 (read-only role) with this branch's `export_index.py --families`.
`export_exceptions.json` is unchanged apart from its note. Only the 3 held rows still carry `From N/A` in `alt_name`.

## Going back

On the staging host, from the code directory:

```
CONFIG_DIR=/etc/scanapp-staging RELEASE_NAME=catalogue-titles-20261115 PROJECT=scanapp-scanapp-z1mwj4 COMPOSE_FILE=compose.dokploy.yaml scripts/catalogue-release-switch.sh rollback
```

Then write `07e3a028571c086d8b3a4fd6d2c7cc4e067065a863bef8a52f1a884cef7e9adb` to `/data/phone-index/ACTIVE.next` and
rename it to `ACTIVE`.

## Not done

- **Seven wrong Cardmarket links.** `ja:M6-048`, `ja:SV-P-155`, `-165`, `-210`, `-254`, `-258` and `ja:SV10-082` link
  to an Indonesian, Traditional Chinese or 30th Celebration product with the same number but a different card; that is
  where their wrong titles came from. This release changes titles only; clearing or fixing the links is a links release.
- **The 3 held titles** above need a source for the right card.
