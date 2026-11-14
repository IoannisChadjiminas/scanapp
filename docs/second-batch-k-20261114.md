# Second batch K: Cardmarket links for the new cards (2026-11-14)

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

## Going back
`CONFIG_DIR=/etc/scanapp-staging RELEASE_NAME=second-batch-k-20261114 PROJECT=scanapp-scanapp-z1mwj4 COMPOSE_FILE=compose.dokploy.yaml scripts/catalogue-release-switch.sh rollback`
