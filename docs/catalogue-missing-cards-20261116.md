# Cards missing from the catalogue, English and Japanese (2026-11-16)

Question: which real English and Japanese cards have no row in the catalogue at all? (Cards that have a row
but no vector are counted separately in `docs/phone-index-v3-20261116.md`.) Pocket (digital) and Chinese
cards are out of scope. Read-only: nothing in the catalogue or on staging changed.

Catalogue compared: `PS-CATALOGUE-EN-JA-LINKS4-20261115` (the staging catalogue), from a local snapshot.
Work files: `data/catalogue-gaps/missing-cards-20261116/` (`en-tcgdex.json`, `ja-tcgdex.json`,
`ja-limitless.json`, and the small comparison scripts that wrote them).

## Sources

| Source | Covers | Fetched |
|---|---|---|
| TCGdex `/v2/{en,ja}/sets/{id}` card lists | 221 English sets; 204 Japanese sets, 121 of them with a card list | 2026-11-16 |
| Limitless JP set lists (`limitlesstcg.com/cards/jp/<code>`) | 264 Japanese sets, Black & White (2010) onward | saved 2026-11-14 by the names work |
| pokemontcg.io set list | 177 English sets with card totals (independent check) | saved 2026-11-11 |

A card counts as present when a catalogue row of the same set has the same number (leading zeros ignored).
Limitless sets map to ours through the names work's set map, then by the same code; `SVP` = `SV-P` and
`SCd` = `jr-grimmsnarl-vmax-starter-set` were matched by hand.

## English: nothing missing that a list shows

- Every card on TCGdex's 221 English set lists has a catalogue row (Pocket left out).
- Against pokemontcg.io's 177 sets, the only shortfall was Team Up (`sm9`): pokemontcg.io counts 198 cards,
  TCGdex and the catalogue stop at 196. Bulbapedia's Team Up list also ends at 196/181; the two extra are the
  `152a`/`152b` Pokémon Communication variants (we have `152b`; `152a` is a championship reverse-holo promo).
- Four TCGdex English sets have no card list: Jumbo cards (160), W Promotional (7), Sample (10), Radiant
  Collection (25). Radiant Collection's 25 cards are inside our `bw*` sets as `RC` numbers; the other three
  are oversize, sample and pre-release products, to check by hand.
- Our sets that TCGdex does not have came from other sources and are not checked by a list here:
  Prize Pack Series 1-9, Trick or Trade 2022-2024, the Classic decks, Burger King, Professor Program,
  the 151 UPC metal card.

## Japanese, Black & White onward: nothing missing

Against the 264 Limitless sets:

| Kind | Cards | What it is |
|---|---:|---|
| Numbered, filed elsewhere | 3 | `SC` 002 ジャノビー is `ja:pc-shiny-collection-2` (a companion set); `SGG` 0 and `SGI` 0 (basic energies numbered 0) are our `SGG-u01` and `SGI-u01` |
| Numbered, in the catalogue without its number | 77 | Sword & Shield promos `SP` 001-099: our `ja:SP-u01`..`u82` rows (English names, placeholder numbers) are these cards (きずぐすり = Potion, マリィ = Marnie, ...). They need their printed numbers, not new rows |
| Suffix variants | 210 | Limitless lists mirror and deck-mark prints as `1r`, `1a`, `13b` (`XY` The Best of XY 128, `WAK` 17, `HS` 14, `XYP` 13, ...). The catalogue does not model these as separate cards |
| Unnumbered basic energies per product | 300 | Limitless lists each deck's basic energies (`NAN1`, `G`, `D`, ...). The catalogue keeps basic energies in the `EN*` and energy sets, not per product |

Against TCGdex's 121 Japanese card lists (mostly the older sets: e-Card, PCG, neo, VS, web, Base-era):
nothing missing apart from the named energies of `M6a` (8) and `MF` (5), the same kind as above. TCGdex's
`BW8a` ラセンフォース (Spiral Force) is our `BW8-Brf`.

## Japanese sets no list covers: 184 sets, 5,652 rows

Neither TCGdex (no card list) nor Limitless (starts at Black & White) lists these, so their checklists have to
be read by hand (Bulbapedia or TCG Collector in the owner's Chrome; both block automated access):

| Group | Sets | Rows we have |
|---|---|---:|
| DP and Platinum expansions | DP1, DP2, DP3, DPS, DPt1, DPt2, DPt3, DPt4 | 852 |
| LEGEND expansions | L1HG, L1SS, L2, L3, LL | 329 |
| ADV and DP expansions with TCG Collector ids | ADV: jr-adv-expansion-pack, jr-miracle-of-the-desert, jr-rulers-of-the-heavens, jr-magma-vs-aqua-two-ambitions, jr-undone-seal. DP: jr-moonlit-pursuit, jr-dawn-dash, jr-cry-from-the-mysterious, jr-temple-of-anger, jr-moonlit-pursuit-dawn-dash | 726 |
| Promos | DPP, DPtP, LP, PPP, S8a-P, jr-adv-promos, jr-pcg-promos, jr-p-promos, jr-play-promos, jr-t-promos, jr-j-promos, jr-miscellaneous-promos | 950 |
| Decks, gift boxes, kits, collection packs | about 120 `jr-*` products, the DPt LV.X decks and packs, Classic (CLF, CLK, CLL), MG, WCP, PW, S8a-G | about 2,600 |
| Energy sets | EN06 .. EN21, jr-mega-evolution-energies, jr-scarlet-violet-energies | 122 |
| Companion rows (`pc-*`, `pooka-*`) | rows added to complete the sets above | 98 |

The full list is in `ja-tcgdex.json` and `ja-limitless.json` (`our_sets_not_on_limitless`).

## Main older Japanese expansions, read by hand (23 sets)

Checklists read on Bulbapedia (the Japanese set lists on each English set's page, e.g. `Undaunted (TCG)` for
Reviving Legends) on 2026-11-16, in the app's built-in browser (Claude in Chrome was not connected). DP and
Platinum Japanese cards carry no printed number, so those sets were compared by card name (our 001-122 style
numbers there are our own); LEGEND and ADV sets are numbered and were compared by number.

| Set | Ours | Checklist | Missing |
|---|---:|---:|---|
| DP1 Space-Time Creation | 122 | 122 (Diamond + Pearl Collections) | - |
| DP2 Secret of the Lakes | 123 | 123 | - |
| DP3 Shining Darkness | 119 | 119 | - |
| Moonlit Pursuit, Dawn Dash | 70, 70 | 70, 70 | - |
| Cry from the Mysterious, Temple of Anger | 65, 65 | 65, 65 | - |
| DPS Intense Fight in the Destroyed Sky | 92 | 92 | - |
| DPt1-DPt4 | 96, 90, 100, 90 | 96, 90, 100, 90 | - |
| L1HG HeartGold Collection | 71 (+8 basic energies) | 71 | - |
| L1SS SoulSilver Collection | 71 | 71 | - |
| Magma vs Aqua: Two Ambitions | 80 | 80 | - |
| L2 Reviving Legends | 73 + 8 companion | 81 | - (8 in `pc-reviving-legends`, `pooka-l2`) |
| L3 Clash at the Summit | 68 + 13 companion | 81 | - (13 in `pc-clash-at-the-summit`) |
| LL Lost Link | 38 + 2 companion | 40 | - (2 in `pc-lost-link`) |
| ADV Expansion Pack | 43 + 12 companion | 55 | - (12 in `pooka-adv-expansion-pack`) |
| Miracle of the Desert | 48 + 5 companion | 53 | - (5 in `pooka-miracle-of-the-desert`) |
| Rulers of the Heavens | 48 + 6 companion | 54 | - (6 in `pooka-rulers-of-the-heavens`) |
| Undone Seal | 72 + 11 companion | 83 | - (11 in `pooka-undone-seal`) |

**Nothing missing** in these 23 sets. 57 of their cards are filed under a companion set id (`pc-*`, `pooka-*`,
rows added from other sources to complete the set) instead of the main set id; every number on the checklist
has a row in the main set or its companion.

Found on the way (not missing cards):

- `jr-moonlit-pursuit-dawn-dash` (135 rows, titles like "Magcargo Lv.35") is the same 135 distinct cards as
  `jr-moonlit-pursuit` + `jr-dawn-dash` (140 cards, 5 in both). It looks like a second copy of those two sets.
- `ja:jr-dawn-dash-014` is titled "Dark Magcargo"; the Dawn Dash card is a plain Magcargo (the combined set
  has it as "Magcargo Lv.35").
- 19 L1HG and 18 L1SS rows have unpadded numbers (`13`, not `013`) and a Japanese set name; no number repeats,
  so the sets are complete, only inconsistently written.

## Japanese promos, decks and products, read by hand

Bulbapedia, 2026-11-16, same method (numbered products by number; deck pages count each distinct numbered
card once, so a card in both decks of a two-deck kit appears once there and twice here).

| Matched the checklist | Sets |
|---|---|
| Promos | DPP 127, DPtP 51, PPP 7, ADV-P 63, PCG-P 154, P 47, T 24, J 2, PLAY 32, LP 79 (+ our 12 Illusion's Zorua/Zoroark `500`-`511`), WCP 108 (87 + 21 in `pooka-wcp`), S8a-P 25, Pikachu World 9 |
| Numbered decks and kits | Aqua and Magma Deck Kits 33, Black and Silver Deck Kits 20, the 18 ADV/PCG constructed starter and standard decks, Extra Regulation Box (48 + 9 energies), Master Kit, Leafeon vs Metagross, Garchomp vs Charizard, Giratina vs Dialga, Infernape vs Gallade, Battle Starter Decks, the DPt, Emerald, Latias/Latios and Mew • Lucario gift boxes, Arceus LV.X decks, the three Holon Research Tower quarter decks, the four Movie Commemoration VS packs, Theater Limited VS Pack, 10th and 11th Movie sets, Movie Random Pack, Melee! Pokémon Scramble, Southern Islands, Scarlet & Violet energies, the Classic decks (with their `pooka-` companions), Vending Machine Series 1 and 2 |
| **Missing** | **Vending Machine Series 3 (Green): 2 cards.** Bulbapedia lists two different Kadabra and two different Haunter; we have one of each (`u21`, `u14`). Neither has a TCGdex image |

Not compared (no comparable list): the unnumbered half decks, Entry Packs, Quick Starter Gift Set and
Heatran/Magmortar kits (Bulbapedia lists every card in the deck, reprints and energies included), the gym
decks, Neo Premium Files, PokéPark, Venusaur/Charizard/Blastoise random decks, Intro Packs, McDonald's
Pokémon-e Minimum Pack (Bulbapedia's page lists a different product), `jr-miscellaneous-promos` and
`jr-miscellaneous-decks` (TCG Collector groupings), MG, Mega Evolution energies and the `EN*` energy sets:
about 40 products, 900 rows.

## Answer

- **English: 0 cards missing**, apart from 3 small special products without a list (Jumbo, W Promotional, Sample).
- **Japanese, from 2010 on: 0 cards missing**; 77 SP promos present without their printed number; mirror and deck-mark variants
  and per-product basic energies are not modelled (510 list entries).
- **Japanese main expansions before 2010 (23 sets read): 0 cards missing**; 57 are filed under companion set ids.
- **Japanese promos, decks and products: 2 cards missing** (Vending Machine Series 3 Kadabra and Haunter);
  about 40 products (900 rows) have no comparable list.
- Fixes rather than additions: 77 SP promo numbers, `jr-dawn-dash-014` "Dark Magcargo" title, the duplicate
  `jr-moonlit-pursuit-dawn-dash` set, and 57 + 1 cards filed under companion set ids.
