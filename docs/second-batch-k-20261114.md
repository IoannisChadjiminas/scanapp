# Second batch K: Cardmarket links for the new cards (2026-11-14)

**Update, same day: K3 is served.** `PS-CATALOGUE-EN-JA-REC46-K3-20261114` (schema `pokesingle_completion_20261111_jarec46`)
replaced K and brings the total to **698** links; see "K2 and K3" below. Rollback folder
`/etc/scanapp-staging/catalogue-rollback/second-batch-k3-20261114` (returns to K).

A links-only release: 582 cards added in the second batch get a verified Cardmarket page and product id.
Names, images, vectors, artwork and features are unchanged. Production is not touched.

| Item | Value |
|---|---|
| Release | `PS-CATALOGUE-EN-JA-REC44-K-20261114`, schema `pokesingle_completion_20261111_jarec44` (`prepare_sql_fixes.py` on JAREC42) |
| Parent served before | `PS-CATALOGUE-EN-JA-REC42-J-20261113` |
| Built and never served | `..._jarec43` / `PS-CATALOGUE-EN-JA-REC43-K-20261114` (the first 518 links; its replay was stopped to add 64 more and replay once) |
| Artifacts | features and artwork `20261113-second-batch-j` (unchanged) |
| Rollback folder | `/etc/scanapp-staging/catalogue-rollback/second-batch-k-20261114` (returns to J) |
| Switch | FORWARD OK, healthy, restarts 0, OOM false |

Catalogue 62,784 cards (unchanged); cards with a Cardmarket link 48,220 -> 48,802.

## Where the links come from

Cardmarket list view (`?mode=list&perSite=50&site=N`), read by the repo's local collector (`scraper/`,
`collect_listings.py`) in its own Chrome profile, 45 s between pages, Cloudflare checks cleared by the owner.
69 explicit page seeds in 27 expansions, 3,036 products, no rate limit hit. The product id is the list row's
`productRow<id>` (`scraper/listings.py`). Run folder `data/catalogue-gaps/second-batch-k-20261113` (not in git).

| Source | Cards | How it is matched |
|---|---:|---|
| Delta Reign (`en:me06`), M6a, SI, SP pages read earlier in the owner's Chrome | 237 | product slug code + number, name read by eye; name-based exceptions for M6a 140/154/087 and DLR133 |
| List view, set code + number + name | 281 | `match_cardmarket_list.py`: exactly one product with that number whose English name is the one Cardmarket already uses for that Japanese name in the catalogue, page not in use |
| List view, read by eye | 33 | exactly one product at that number, English name checked against the Japanese one (e.g. ミブリム Hatenna, エール団の応援 Team Yell's Cheer, ウツギはかせの育てかた Professor Elm's Training Method) |
| List view, unnumbered basic energies | 31 | the set lists exactly one product of that energy type (Start Deck 100, Battle Academy, Eevee Heroes, XY Beginning Set, sm1+, sGG, WCS23) |

`prepare_sql_fixes.py` refuses a link already used by another row and a product id used twice; every link is
`cardmarket_verified=1`, provenance `cardmarket-list-view-second-batch-k-20261114`.

## Held (227, `held-links.json` in the run folder; browser worklist item 1)

| Reason | Cards |
|---|---:|
| Unnumbered card with several Cardmarket versions (trophies, promo energies, Victory Cup) | 102 |
| Several versions V1..V5 at that number and the list does not say which deck (Starter Set V decks, Charizard VMAX 1/2, Grimmsnarl) | 61 |
| Several versions, or the name differs, at that number | 43 |
| No product with that number | 13 |
| Page already held by another catalogue row (SP-324 Lugia V, SI-169, SI-174, SI-301, SI-310) | 5 |
| Link slug number differs from the printed number (SP-252, SP-253) | 2 |
| Two decks share the numbering (SC2-020 Marnie) | 1 |

These need the product page (which deck, which print) and are left for the browser sitting.

## Gate (1,891 photos)

| Panel | Photos | Right first | Wrong first | Upper bound |
|---|---:|---|---|---|
| dev | 681 | 637 -> 637 | 4 -> 4 | 1.5% |
| dev2 | 238 | 232 -> 232 | 0 -> 0 | 1.6% |
| dev3 | 972 | 938 -> 938 | 0 -> 0 | 0.4% |

Right -> wrong 0; right card always offered; no cell lower. Against J, 0 of 1,891 photos changed status or
first answer; the 28 photos that differ from the step-1 run are the same 28 already judged for J.
The run was slow while the machine was swapping (other apps open); speed does not change the answers.

## K2 and K3: 116 more links (switched as one release)

| Source | Cards | How it is checked |
|---|---:|---|
| Starter Set V decks (5), Charizard VMAX 1 and 2, Grimmsnarl VMAX: the V1..V5 versions | 101 | Cardmarket numbers each deck's products in one id block (Grass 524150-524260, Fire 524265-524375, Water 524380-524490, Lightning 524495-524610, Fighting 524615-524730; Grimmsnarl 523835-523930, Charizard 1 523935-524035, Charizard 2 524040-524135). Every chosen product's photo was looked at by eye in the owner's Chrome (the photo host is not behind the check): set mark colour and printed number match ours (Grass green /023, Fire red /023, Water blue /023, Lightning yellow /024, Fighting brown /024, `sC` /021, `sC2` /021, Grimmsnarl teal /020) |
| `SP-252`, `SP-253` energies | 2 | product page shows number 252, photo shows 253/S-P (the slugs say 251/252) |
| `en:mep-099` Greninja ex, `en:mep-100` Sylveon ex | 2 | V2 is the oversized jumbo card; the regular card is V1 |
| Battle Strength Decks (`BKv`, `BKt`, `BKc`) | 8 | Cardmarket numbers carry the deck letter (BK 001V, 002T, 008C ...) |
| `en:30th-R`, `-G`, `-B` Mew | 3 | Cardmarket `Mew (30C R/RGB)`, `G/RGB`, `B/RGB` |

`..._jarec45` / `PS-CATALOGUE-EN-JA-REC45-K2-20261114` (105 links) was built and never served; its replay was stopped to add the 11
links of K3 and replay once. K3 gate: same table as above (right -> wrong 0, no cell lower, upper bound 1.5% / 1.6% / 0.4%), 0 of 1,891
photos changed against J. Phone index `28eaa9f4` (published by the clean-up session) still answers 200 after the switch.

Held: 111. `ja:jr-grimmsnarl-vmax-starter-set-010` (Cardmarket's photo for the only candidate is a red /021 Charizard-deck card) and
`ja:SC2-012` (no Rare Candy in the Charizard 2 block); `ja:SI-169`, `-174`, `-301`, `-310` (the page is held by the `zh-tw:` rows of the
same cards; Chinese left out of scope); `ja:SP-324` (duplicate of `extra-lugia-v-326-s-p`, which holds the page). Searches in the owner's
Chrome found no Japanese product for Victory Cup and Tropical Beach (English BW and World Championship prints only), the BW-P stamped
Level Ball / Enhanced Hammer / Max Potion / Team Plasma Badge, or the deck-box basic energies. `ja:M-P-u07`..`u16` turned out to be
duplicates of `ja:MP1-001`..`012` (mP1 nnn/023, already linked): they go to the duplicate clean-up release with the 561 unprefixed rows.

## Going back
`CONFIG_DIR=/etc/scanapp-staging RELEASE_NAME=second-batch-k3-20261114` ... `rollback` returns to K; then the same with
`RELEASE_NAME=second-batch-k-20261114 PROJECT=scanapp-scanapp-z1mwj4 COMPOSE_FILE=compose.dokploy.yaml scripts/catalogue-release-switch.sh rollback`
