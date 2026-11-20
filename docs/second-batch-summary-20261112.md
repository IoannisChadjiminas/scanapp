# Second batch: summary (2026-11-12)

Work order: `docs/second-batch-agent-plan-20261111.md`. Staging only; production was not switched.

## Staging now
Catalogue `PS-CATALOGUE-EN-JA-REC42-J-20261113` (schema `pokesingle_completion_20261111_jarec42`), 62,784 cards (was 61,975 on JAREC18).
Code: main `a916be4`, 20 flags unchanged.

| Batch | Release | Added | Scannable / alternatives / display-only | Rollback folder | Record |
|---|---|---:|---|---|---|
| A1 Start Deck 100 | REC19-A1 | 128 | 28 / 100 / 0 | `catalogue-rollback/second-batch-a1-20261111` | `second-batch-a1-20261111.md` |
| A2 eight starter products | REC20-A2 | 184 | 66 / 118 / 0 | `.../second-batch-a2-20261111` | `second-batch-a2-20261111.md` |
| A3 30th Celebration with art | REC25-A3 | 49 | 34 / 15 / 0 | `.../second-batch-a3-20261111` | `second-batch-a3-20261111.md` |
| A4 promos and decks | REC26-A4 | 103 | 38 / 65 / 0 | `.../second-batch-a4-20261111` | `second-batch-a4-20261111.md` |
| B official-list only | none | 0 | | | `second-batch-b-20261111.md` |
| C product energies | REC34-C | 76 | 6 / 52 / 18 | `.../second-batch-c-20261111` | `second-batch-c-20261111.md` |
| D English rows | REC36-D | 7 | 2 / 0 / 5 | `.../second-batch-d-20261112` | `second-batch-d-e-20261112.md` |
| E `M6a` secret rares with official images | REC37-E | 9 | 9 / 0 / 0 | `.../second-batch-e-20261112` | `second-batch-d-e-20261112.md` |
| F 30th Celebration rest, LEGEND decks (TCG Collector) | REC38-F | 74 | 55 / 19 / 0 | `.../second-batch-f-20261113` | `second-batch-f-20261113.md` |
| G+H+I+J, one replay: 4 English images, `MG` deck set 38, Delta Reign 141, 38 images for existing rows | REC42-J | 179 new + 42 images | see record | `.../second-batch-j-20261113` | `second-batch-j-20261113.md` |

Every switch passed: right -> wrong 0, right card always offered, no cell lower, wrong-first upper bound 1.5% / 1.6% / 0.4%.
Rows file: 811 `done`, 6 `left_out`, each with its reason.

## Left out (6 rows)
- **4 Sword & Shield promos** (ホップ, きずぐすり, モンスターボール, ビート): two prints each; our single row has no image or number, so which print we hold is not known.
- **Vending Series 3 Kadabra, Haunter:** Bulbagarden has both prints of each; same reason.
- **D3** (McDonald's 2013, count-only English sets): on the browser worklist; not rows of the rows file.

Delta Reign uses TCG Collector images until TCGdex publishes art; the TCGdex ids are kept so the mirror job can replace them.

## What the work learned
- A gate replay must not run on a loaded machine: at load 19 (five containers plus builds) answers flip. Four containers at 3 CPUs each is stable.
- New Pikachu art can move promo Pikachu photos: the 15 `M6a` Pikachu cards are printing alternatives, not scannable.
- Display-only rows are not always neutral: Japanese image-less rows sharing names with held cards lowered stored answers (B); the seven English ones (D) changed nothing.
- A release with no new vectors must not append an empty retrieval segment (fixed in `build_release.py`).

## Clean-up for later
Inactive candidate schemas never served: `..._jarec21`, `22`, `23`, `24`, `27`, `28`, `31`, `32`, `33`. Their staged artifact folders on
the data volume (`*-second-batch-a3`, `-a4`, `-b`, `-c`, `-br`, `-cr`, `-bnovend`, `-bnom6a`, `-bnol2`) and `/root/stage-*` work folders.
The short-lived read role `sbcards-read-*` expires 2026-11-12 19:21Z.

## Not verified
A real camera, the app build, iPhone, Japanese changed-number hints, the phone index (not rebuilt; contains none of the 540 cards),
Cardmarket links of the new cards, artifact checksums at switch time (`MANIFEST` not set).
