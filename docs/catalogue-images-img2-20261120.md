# IMG2: twin and split rows for 21 image-less Japanese rows (2026-11-20)

This batch adds images for 21 Japanese rows that had none, and adds 17 new rows for real cards that were hidden behind one checklist name. It is built on top of LINKS5T. Staging only: production is not touched. The model is unchanged, no vector was added or recomputed, and the phone index does not change.

Owner's approval (2026-11-20, in the links session): "Yes, do both", answering "split the 16 rows and give the 5 their twin's picture".
The per-row record (TCG Collector label, image URL, image path, the row it was split from or is a twin of) is in `docs/catalogue-images-img2-20261120.tsv`. The worklist is `img2-worklist-20261120.json` in the links session's notes.

| | |
|---|---|
| Parent (served) | `pokesingle_completion_20261119_links5t` / `PS-CATALOGUE-EN-JA-LINKS5T-20261119` |
| Release | `pokesingle_completion_20261120_img2` / `PS-CATALOGUE-EN-JA-IMG2-20261120` |
| Images | `/data/reference-images/ja-20261120-img2` (38 JPEG, quality 95, from TCG Collector WebP scans) |
| Features | `20261120-img2`, manifest `8343422207a6a60d5de2ad83c7ffb170df1f53ade0b4655c2a6082d71b26c792` (parent `d6a51405…`, 55,691 of 62,091 available); local and staging files match by sha256 |
| Artwork | `20261120-img2` (37,358 regions, unchanged; new manifest only) |
| SQL | `candidate.sql` sha256 `7fee7448457ea2dcdaeecd7a2277f22d0708f0be777f106d7afad37755467737`, 71 statements, committed in 21 s |
| Cards | 62,074 → 62,091 (17 new rows); 55,663 → 55,701 with an image; pad vectors 48,874 (unchanged) |
| Source kind | `tcgcollector_scan`, as in JAREC4/7 (owner approved TCG Collector scans on 2026-10-15) |

## What changed

**A. Twins (5 rows).** Each of these rows is the same printed card as a row that already has its picture. On 2026-11-09 they were held under the "one image file, one card" rule. The owner now allows them to reuse the same TCG Collector image:

- `ja:jr-tamamushi-city-gym-deck-u03` Defender: twin of `jr-hanada-city-gym-deck-u02` and `jr-miscellaneous-decks-053`
- `ja:jr-yamabuki-city-gym-deck-u04` Full Heal: twin of `jr-kuchiba-city-gym-deck-u04` and `jr-miscellaneous-decks-055`
- `ja:jr-yamabuki-city-gym-deck-u08` Potion: twin of `jr-hanada-city-gym-deck-u22` and `jr-miscellaneous-decks-050`
- `ja:jr-dialga-palkia-lv-x-constructed-standard-decks-u06` Dialga: twin of `jr-dialga-lv-x-constructed-standard-deck-006`
- `ja:jr-magmortar-vs-electivire-deck-kit-magmortar-u10` Magmortar: twin of `jr-magmortar-vs-electivire-deck-kit-010`

**B. Splits (16 rows → 33 cards).** Each of these checklist rows held one name that covers 2 or 3 different real cards, and TCG Collector's set and deck lists show each of them. The existing row takes the first card (the lowest TCG Collector number). Each other card gets a new row that copies the existing row's name, title, set and other columns. A new row has its own id, `provider_id`, `collector_number` and image, has no Cardmarket link, and gets its own `catalogue-completion-source:PS-CATALOGUE-EN-JA-IMG2-20261120:<id>` provenance row (with `split_from` and the TCG Collector label).

**Id scheme:** a new row takes the next free `uNN` in its set, the same convention as the existing unnumbered checklist rows. Rows with the same name in one set already share name and title (e.g. `jr-miscellaneous-decks-027`/`-028` Sabrina's Abra); the collector number tells them apart. I did not use the TCG Collector numbers as ids, because the existing row (e.g. `BWP-u05` = BW-P No. 239) cannot be renamed. Mixing `BWP-245` with `BWP-u05` would also invite a later duplicate `BWP-239`.

| Existing row (keeps) | New row(s) |
|---|---|
| `ja:BWP-u05` Oshawott (BW Promos 239) | `ja:BWP-u32` (245) |
| `ja:BWP-u06` Pikachu (BW Promos 248) | `ja:BWP-u33` (284), `ja:BWP-u34` (285) |
| `ja:BWP-u08` Reshiram (BW Promos 246) | `ja:BWP-u35` (250) |
| `ja:BWP-u09` Tepig (BW Promos 238) | `ja:BWP-u36` (241) |
| `ja:BWP-u13` _____'s Pikachu (BW Promos 240) | `ja:BWP-u37` (271) |
| `ja:jr-guren-town-gym-deck-u07` Blaine's Growlithe (Misc. Decks 009) | `ja:jr-guren-town-gym-deck-u24` (Misc. Decks 010) |
| `ja:jr-guren-town-gym-deck-u10` Blaine's Ponyta (Challenge from the Darkness 032) | `ja:jr-guren-town-gym-deck-u25` (Misc. Decks 011) |
| `ja:jr-guren-town-gym-deck-u14` Blaine's Vulpix (Challenge from the Darkness 028) | `ja:jr-guren-town-gym-deck-u26` (Misc. Decks 008) |
| `ja:jr-hanada-city-gym-deck-u08` Misty's Goldeen (Leaders' Stadium 032) | `ja:jr-hanada-city-gym-deck-u24` (Misc. Decks 018) |
| `ja:jr-hanada-city-gym-deck-u16` Misty's Staryu (Leaders' Stadium 033) | `ja:jr-hanada-city-gym-deck-u25` (Misc. Decks 020) |
| `ja:jr-kuchiba-city-gym-deck-u10` Lt. Surge's Magnemite (Leaders' Stadium 037) | `ja:jr-kuchiba-city-gym-deck-u24` (Leaders' Stadium 038) |
| `ja:jr-kuchiba-city-gym-deck-u12` Lt. Surge's Pikachu (Leaders' Stadium 036) | `ja:jr-kuchiba-city-gym-deck-u25` (Misc. Decks 022) |
| `ja:jr-kuchiba-city-gym-deck-u18` Lt. Surge's Voltorb (Leaders' Stadium 040) | `ja:jr-kuchiba-city-gym-deck-u26` (Misc. Decks 024) |
| `ja:jr-nivi-city-gym-deck-u02` Brock's Geodude (Leaders' Stadium 049) | `ja:jr-nivi-city-gym-deck-u26` (Misc. Decks 039) |
| `ja:jr-yamabuki-city-gym-deck-u11` Sabrina's Abra (Misc. Decks 027) | `ja:jr-yamabuki-city-gym-deck-u26` (Misc. Decks 028) |
| `ja:jr-yamabuki-city-gym-deck-u15` Sabrina's Gastly (Misc. Decks 029) | `ja:jr-yamabuki-city-gym-deck-u27` (Misc. Decks 030) |

The gym-deck rows are deck-list copies of cards that are also filed as Miscellaneous Decks or Leaders' Stadium rows, like the other gym-deck rows that already have pictures.

**Eye check:** I checked all 38 images against their TCG Collector label: the Japanese name (e.g. カツラのガーディ, マチスのコイル, ナツメのケーシィ, ミジュマル, レシラム, ポカブ, のピカチュウ), and for each split pair that the two cards differ in level, HP and art. All pass the image gate (shortest side >= 180, blur >= 40). No Cardmarket photos are used.

**Treatment:** all 38 rows are older-era (BW and vintage), so they are printing alternatives: image plus features, no vectors. The phone index exports only rows with vectors, so it does not change. `export_exceptions.json` needs no new ids, because the new rows' Latin names are never exported.

## Gate

The 1,891-photo replay ran under `caffeinate` with a 12h read role, using image `scanapp-api-staging:24856ba9` and 3 lanes; every shard exited 0. I scored it with `score_gate.py` and the corrected labels. **The baseline is the LINKS5S run, `data/catalogue-gaps/ja-links-20261116/out`.** It also covers LINKS5T, which changed only 3 link fields; its shards dev32, dev34 and d2dev20 were rerun after a role expiry.

| panel | photos | right first | wrong first | right offered | wrong-first upper bound |
|---|---|---|---|---|---|
| dev | 681 | 636 → 636 | 3 → 3 | 663 → 663 | 0.0129 |
| dev2 | 238 | 232 → 232 | 0 → 0 | 238 → 238 | 0.0159 |
| dev3 | 972 | 938 → 938 | 0 → 0 | 963 → 963 | 0.0039 |

There were 0 answers going from right first to not right first, 0 expected cards no longer offered and 0 cells lower, and the numerical gates pass.

Changed answers (3). All keep the same right card first, and none involves an IMG2 row:

- `dev2-ja-modern-002` (`ja:SM12a-193`, matched): the 5 alternatives are gone. IMG2's answer is the same as IMG1's run; the LINKS5S run took 29.6 s on this photo against 15.0 s here, so the baseline is the outlier. This photo is also one of the two the links session saw change between LINKS5F and LINKS5S.
- `dev2-ja-modern-004` (`ja:SM4A-027`): `printing_ambiguous` became `uncertain`, with the same best card and no alternatives. Same as IMG1's run; LINKS5S took 44.6 s here. This is the other photo that changed between LINKS5F and LINKS5S.
- `sealed-ja-modern-030` (`ja:BW1-Bb-013`): `printing_ambiguous` became `uncertain`, with the same best card. The baseline's printing list held only the card itself. This is the same kind of change as IMG1's `sealed-ja-older-001`. Harmless.

## Switch

The gate shows 0 right→wrong, so staging was switched with `scripts/catalogue-release-switch.sh apply`. The result was `FORWARD OK catalogue-img2-20261120`: health ok, ready, import `PS-CATALOGUE-EN-JA-IMG2-20261120`, 0 restarts, no out-of-memory kill. Only these lines of `/etc/scanapp-staging/catalogue-release.env` changed:

```
PLANETSCALE_SCHEMA=pokesingle_completion_20261120_img2
PLANETSCALE_IMPORT_ID=PS-CATALOGUE-EN-JA-IMG2-20261120
REFERENCE_FEATURES_DIR=/data/reference-features/20261120-img2
ARTWORK_BUNDLE_DIR=/data/artwork/20261120-img2
```

The rollback folder is `/etc/scanapp-staging/catalogue-rollback/catalogue-img2-20261120`. Its `catalogue-release.env.rollback` returns to LINKS5T (`pokesingle_completion_20261119_links5t`, features and artwork `20261116-img1`).

Going back:
`cd /etc/dokploy/compose/scanapp-scanapp-z1mwj4/code && RELEASE_NAME=catalogue-img2-20261120 PROJECT=scanapp-scanapp-z1mwj4 CONFIG_DIR=/etc/scanapp-staging COMPOSE_FILE=compose.dokploy.yaml bash scripts/catalogue-release-switch.sh rollback`

## Scripts

- `assemble_image_batch.py`: an accepted line with `new_row_from` and `collector_number` becomes a new row. Signature rows include the new rows. TCG Collector's source kind is now `tcgcollector_scan`.
- `build_image_batch.py`: passes `new_row_from`, `collector_number` and `tcgc_label` through to `updates.json`. A new row does not lower `missing_images`.
- `prepare_sql_images.py`: inserts the new rows as copies of their source row, adds their provenance rows, and counts both in the manifest and the guard.

Run folder: `data/catalogue-gaps/img2-20261120` (not in git).

## For the links session

The 17 new rows (above) and the 21 imaged rows have no Cardmarket link. The new rows are ready to be eye-checked on Cardmarket and linked in a LINKS release on top of IMG2.
