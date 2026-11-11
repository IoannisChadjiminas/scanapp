# Data-only fixes, step 1 of the remaining-cards plan (2026-11-11)

Step 1 of `docs/remaining-cards-plan-20261111.md`: fixes that need no new image. One server
change and one catalogue release on staging. Production is not touched.

## What changed

### In the server code

| Change | Where | Effect |
|---|---|---|
| The 28 Unseen Forces Unown Collection rows (`exu`) are no longer listed | `api/app/routes/cards.py` (`_LISTED_ONCE`) | Search, the set list and the chase list show each Unown once, as its `ex10` card with its image. The `exu` rows stay in the catalogue and still answer when asked for by id, so a portfolio that holds one keeps working. No image is copied |
| L2 and L3 print `/080` | `api/app/set_totals.py` (`TOTAL_CORRECTIONS`) | The number rules compare a read `/080` with the right total. SM7a (`/060`) was already there |
| The release script takes label and link fixes | `api/scripts/ja_set_recovery/prepare_sql_fixes.py` | A fix can now set `name`, `view_title`, `set_name`, `category`, `printed_collector_number` (each with a reason and a source), and move a row to the Cardmarket page that the crawl matched to it. The script refuses a release that makes two cards newly share a page |

### In the catalogue (release `PS-CATALOGUE-EN-JA-REC18-20261111`)

Schema `pokesingle_completion_20261111_jarec18`, built as a copy of JAREC15. 345 card rows
differ and nothing else: the nine table counts are equal, the 34 visual aliases are intact, no
image was added, moved or removed.

| Rows | Fix | Checked against |
|---|---|---|
| 12 | LEGEND Promos `LP-500`–`LP-511`: the row had the English title as its name. They are the Design Contest prints of 幻影のゾロア (7) and 幻影のゾロアーク (5) | Bulbapedia, L-P Promotional cards |
| 1 | Islands Await You `SM2K-062`: no usable name. It is the secret-rare 基本雷エネルギー, 062/050 | Two Japanese shop lists for the set |
| 3 | VS pack `VS1-142`–`144`: name did not match the card in the row's own image (R団のバンギラス, 草エネルギー, 炎エネルギー) | The row's reference image, by eye |
| 4 | `S8-126`–`129`: the Japanese name (and for two the category) belonged to the neighbouring card | The row's reference image, by eye |
| 7 | `SV4a-321`, `326`, `337`, `355`, `SV-P-183`, `184`, `200`: the row held the English title and the Cardmarket page of another product with the same number. Moved to the page the crawl matched to the card; the product id was already right | The matched Cardmarket product row |
| 2 | English Black & White promos: Reshiram prints `BW004`, Zekrom prints `BW005` | The row's reference image, by eye |
| 320 | SV4a rows carried the set name of SV3a. Now シャイニートレジャーex | The set's cards and the TCGdex set list |

A first build (`…_jarec17`) also set the rarity of `SM2K-062` to Secret Rare. That catalogue
would not load: the reference-feature bundle is signed over each card's image path and rarity,
so a rarity change needs a new bundle. The rarity change was taken out, the script now refuses
`rarity` as a label fix, and the release was rebuilt as `…_jarec18`. On the owner's instruction
the unused `…_jarec17` schema (9 tables, 407 MB) was dropped at 14:32Z, after checking that
staging did not use it and nothing outside pointed into it. The expired role that built both
schemas had its objects reassigned to the default `postgres` role first.

One of the seven moved links ended a shared page: `ja:SV-P-200` had the page of the English
N's Resolve. Shared Cardmarket pages went from 578 to 577.

The 13 rows the plan called "no usable name" are all real cards and stay. None was dropped.
Their entries in the coverage queue keep their "no image" reason, with the name now filled.

## Left as it is, and why

| Item | Why |
|---|---|
| Card ids in L1HG and L1SS (two styles in one set) | The ids key the image vectors, the phone index and users' portfolios. The totals are already right through the aliases. Renaming them is a migration, not a data fix |
| `DPBP#NNN` printed numbers for DP1–DP3 | Needs a change to the number parser and about 362 footers checked by eye. Its own step |
| SM7a `/060`, SM10b `/054` | Already right on staging |
| 40 SV4a rows that carry the English name "Shiny Treasure ex" | The set list already shows the Japanese name. These rows are unchanged, so nothing about them is measured by this release |
| `BW01`, `BW06` printed numbers | Not checked by eye, so not changed |
| The 28 `exu` rows themselves | Hidden from lists, not deleted (see above) |

Local labelling tools (not in git) were also fixed for future panels: text notes in `twins`
are no longer read as card ids, and the POP series pools are separate. The frozen panels were
not rebuilt.

## Gates

Full replay of the three stored photo panels (1,891 photos) with this branch's code against the
new catalogue, compared with the latest stored run on staging's catalogue (JAREC15, 20 flags).

| Panel | Photos | Right first, before → after | Wrong first, before → after | Upper bound on wrong first |
|---|---|---|---|---|
| dev | 681 | 637 → 637 | 4 → 4 (the same four photos, the same wrong card) | 1.5% |
| dev2 | 238 | 232 → 232 | 0 → 0 | 1.6% |
| dev3 | 972 | 938 → 938 | 0 → 0 | 0.4% |

- Right → wrong: **0**. No cell lower than staging. Wrong-first upper bound under 3% on every panel.
- Across all 1,891 photos one stored answer differs in any field: `dev-ja-older-065` (L2 004/080)
  went from "uncertain" to "matched" on the same, right card. That is the `/080` total. The table
  accepts it (uncertain → matched on the right card).
- The SV4a set name, the labels and the moved links changed no answer.

Not measured here: the phone. The phone index is a separate artifact built from JAREC15 and is
not rebuilt by this release, so phone answers are unchanged and the 20 renamed rows keep their
old names in it until the next index build.

Server tests: 1,346 pass, 13 skipped. Script tests: 5 pass.

## Going back

Staging: `scripts/catalogue-release-switch.sh rollback` with the rollback folder recorded for
this switch. The code change is independent of the catalogue: with the old catalogue the
`exu` filter and the two totals still apply and are harmless.
