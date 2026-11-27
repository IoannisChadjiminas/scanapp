# English rarities: catalogue RAR2 (2026-11-27)

After Delta Reign (RAR1, `docs/catalogue-delta-reign-rarity-20261127.md`), 1,018 English cards still
had no rarity. Each was checked against a source; 285 now have one and are served on staging.
Production is not touched. Every decision, with its source and evidence, is in
`docs/catalogue-english-rarity-20261127.json` (all 1,018 cards).

| Item | Value |
|---|---|
| Release | `PS-CATALOGUE-EN-JA-RAR2-20261127`, schema `pokesingle_completion_20261127_rar2` |
| Parent served before | `PS-CATALOGUE-EN-JA-RAR1-20261127` (unchanged) |
| Cards digest | `cfb62e61c601fc4d330e3f799e6441e4` → `4bed9a1f8d8b8541a86c087b61b1ab72` (62,091 rows; the old value was reproduced first) |
| Reference features | `20261127-rar1` → `20261127-rar2`, manifest `a8fc5241…` → `91392d90d27a5611f7aad222b0eed6ccf4f500fef47c99a95c6b10c8837e719a` |
| Artwork bundle, vectors | unchanged (`20261120-img2`) |
| Rollback folder | `/etc/scanapp-staging/catalogue-rollback/catalogue-rar2-20261127` (returns to RAR1) |
| Switch | FORWARD OK, healthy, restarts 0, OOM false, `catalogue corrections applied=0` |
| Run folder | `data/catalogue-gaps/rar2-en-20261127` |

## How each rarity was decided

| Source | Cards | Rule |
|---|---:|---|
| TCGdex | 35 | The card's TCGdex row has a rarity (MEP promos 089–110 and 120, Detective Pikachu 25, Mega Evolution Energy 009–016, 30th Celebration Mew B/G/R) |
| Original card | 179 | Trick or Trade, Prize Pack, Professor Program and Burger King reprints: the original is found by its set code and number **and** the names agree after normalising (stamps, `Lv.`, `Basic`, `[F]`); its rarity is copied |
| Alternate print | 43 | Sun & Moon `a`/`b` prints: the original's rarity, only where pokemontcg.io agrees |
| Printed symbol | 28 | Unseen Forces Unown A–Z, !, ?: every card prints ★; pokemontcg.io says Rare for 26 of them |

Set codes were mapped with TCGdex's official abbreviations; the codes TCGdex does not list were
mapped by hand and every one is guarded by the name check (`FL` is FireRed & LeafGreen; Trick or
Trade's `swsh10` cards are Lost Origin). Card images were checked against the copied rarity:
Burger King Lucario DP 6 and Prize Pack Professor's Research SVI 189 print ★, Trick or Trade
Pikachu PAL 62 prints ●.

Filled: Common 126, Rare 74, Uncommon 49, Promo 28, Ultra Rare 5, RGB Rare 3. The 5 Ultra Rare
alternates (`sm2-60a`, `sm3-88a`, `sm5-153a`, `sm11-79a`, `sm12-143a`) had their reference
features rebuilt with the full-art box (`rebuild_features.py`).

## Left empty (733), with the reason

| Cards | Reason |
|---:|---|
| 591 | TCGdex says `None`: McDonald's collections, trainer kits, My First Battle, Kalos Starter Set, Rumble, Best of Game, Futsal, 30th Classic Collection, Promos-A. These cards print no rarity |
| 84 | Classic decks (CLB, CLC, CLV): no source; the Squirtle CLB 001 image prints no rarity symbol |
| 17 | Reprints of a holo original (`Holo Rare`, `Rare Holo`): the reprint prints the same star but may not be holo, so the label is not copied |
| 11 | Alternates where the original and pokemontcg.io disagree (e.g. Enhanced Hammer 124a: Rare vs Uncommon) or pokemontcg.io has none |
| 9 | Reprints whose original was not found with a matching name |
| 21 | `pooka-cl*` copies and My First Battle blue Energy variants: no source |

## Gate (1,891 photos, against RAR1's run)

Same image, code, settings, shards and lanes as RAR1's gate; scored with `score_gate.py` and the
corrected labels.

| Panel | Photos | Right first | Wrong first | Right offered | Upper bound |
|---|---:|---|---|---|---|
| dev | 681 | 636 → 636 | 3 → 3 | 663 → 663 | 1.3% |
| dev2 | 238 | 232 → 232 | 0 → 0 | 238 → 238 | 1.6% |
| dev3 | 972 | 938 → 938 | 0 → 0 | 963 → 963 | 0.4% |

No answer changed in any field.

## After the switch

`/api/v1/cards/en:sm2-121a` Uncommon, `en:ex10-unown-A` Rare, `en:PPS4-SVI-189` Rare,
`en:mep-099` Promo; `en:xy0-9` stays empty; Delta Reign keeps its eight rarities.

## Not verified

A camera photo of the five rebuilt Ultra Rare alternates; the app (no app change).

## Going back

`CONFIG_DIR=/etc/scanapp-staging RELEASE_NAME=catalogue-rar2-20261127 PROJECT=scanapp-scanapp-z1mwj4 COMPOSE_FILE=compose.dokploy.yaml scripts/catalogue-release-switch.sh rollback`
