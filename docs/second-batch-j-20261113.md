# Second batch G, H, I, J: one combined release (2026-11-13)

On the owner's instruction (2026-11-13) G, H, I and J were built as four stacked releases and replayed **once**, on the last one,
J, which contains all four. Staging went from F straight to J. Production is not touched.

| Item | Value |
|---|---|
| Release | `PS-CATALOGUE-EN-JA-REC42-J-20261113`, schema `pokesingle_completion_20261111_jarec42` |
| Parent served before | `PS-CATALOGUE-EN-JA-REC38-F-20261113` (G `..._jarec39`, H `..._jarec40`, I `..._jarec41` were built on the way and never served) |
| Code staging runs | main `a916be4` |
| Artifacts | features and artwork `20261113-second-batch-j`; images `en-20261113-second-batch-g`, `ja-20261113-second-batch-h`, `en-20261113-second-batch-i`, `ja-20261113-second-batch-j` (none mirrored to the CDN) |
| Rollback folder | `/etc/scanapp-staging/catalogue-rollback/second-batch-j-20261113` (returns to F) |
| Switch | FORWARD OK, healthy, restarts 0, OOM false |

Catalogue 62,784 cards (was 62,605). All images below were looked at by eye against name and printed number.

| Part | What | Cards | Source of image | Treatment |
|---|---|---:|---|---|
| G | Images for four display-only English rows: `en:30th-B`, `-G`, `-R` (Mew RGB, 30C EN) and `en:mep-120` Celebratory Fanfare | 4 (existing rows) | Bulbagarden Archives, downloaded through the owner's Chrome with the owner's approval | 4 scannable |
| H | Folder `MG`: **Mega Gengar ex, Mega Dragonite ex & Mega Feraligatr ex Special Deck Set** (product name from TCG Collector), `ja:MG-001`..`038` | 38 new | TCG Collector | 3 scannable, 35 printing alternatives |
| I | **Delta Reign** `en:me06-001`..`141` under the TCGdex ids (so TCGdex art can replace the images later without a second copy of the set) | 141 new | TCG Collector (TCGdex still has no art) | 140 scannable, 1 printing alternative |
| J | Images for 38 existing Japanese rows that had none | 38 (existing rows) | TCG Collector | 1 scannable, 37 printing alternatives (older eras keep no vectors) |

All TCG Collector images are 320 x 447 and flagged to upgrade later.

J's 38 rows: `ja:DPt4-Slp-016`, `ja:HS-038`, `ja:HS-039`, `ja:LP-500`, `ja:LP-501`, `ja:LP-502`, `ja:LP-503`, `ja:LP-504`, `ja:LP-505`, `ja:LP-506`, `ja:LP-507`, `ja:LP-508`, `ja:LP-509`, `ja:LP-510`, `ja:LP-511`, `ja:SM2K-062`, `ja:SMG-019`, `ja:jr-emerald-gift-box-deoxys-013`, `ja:jr-emerald-gift-box-deoxys-014`, `ja:jr-emerald-gift-box-rayquaza-013`, `ja:jr-emerald-gift-box-rayquaza-014`, `ja:jr-garchomp-vs-charizard-sp-deck-kit-charizard-014`, `ja:jr-gift-box-latias-014`, `ja:jr-gift-box-latias-016`, `ja:jr-master-kit-bulbasaur-009`, `ja:jr-master-kit-torchic-008`, `ja:jr-mew-lucario-gift-box-lucario-015`, `ja:jr-mewtwo-vs-genesect-deck-kit-genesect-011`, `ja:jr-mewtwo-vs-genesect-deck-kit-genesect-014`, `ja:jr-mewtwo-vs-genesect-deck-kit-genesect-015`, `ja:jr-miscellaneous-decks-050`, `ja:jr-miscellaneous-decks-053`, `ja:jr-miscellaneous-decks-054`, `ja:jr-miscellaneous-decks-055`, `ja:jr-miscellaneous-decks-056`, `ja:jr-miscellaneous-decks-064`, `ja:jr-miscellaneous-decks-071`, `ja:jr-movie-commemoration-vs-pack-sky-splitting-deoxys-002`.

Not filled from TCG Collector, with the reason:
- 20 matched rows whose image is only 162 px wide (under the 180 px gate): 2006 Energies, the No. 1/2/3 Trainer promos, Victory Medal / Ring.
- 18 rows whose match was a card filed under another set (gym-deck and gift-set reprints): using it would give two cards one image.
- About 270 rows where TCG Collector shows only a card back, or several prints with the same name and nothing to tell which is ours.

## Gate (1,891 photos, against the step-1 stored run)

| Panel | Photos | Right first | Wrong first | Upper bound |
|---|---:|---|---|---|
| dev | 681 | 637 -> 637 | 4 -> 4 | 1.5% |
| dev2 | 238 | 232 -> 232 | 0 -> 0 | 1.6% |
| dev3 | 972 | 938 -> 938 | 0 -> 0 | 0.4% |

Right -> wrong 0; right card always offered; no cell lower. 28 photos differ; against F, six new ones, all in the alternatives only (first answer
and status unchanged): new Delta Reign cards (`en:me06-056`, `en:me06-014`) and `MG` cards (`ja:MG-003`, `ja:MG-014`) offered as look-alikes,
accepted by design; where an older alternative dropped out of the list it was not the right card (wrong -> wrong, logged).

Because the four parts were replayed together, a change cannot be attributed to one part; none needed to be.

## Going back
`CONFIG_DIR=/etc/scanapp-staging RELEASE_NAME=second-batch-j-20261113 PROJECT=scanapp-scanapp-z1mwj4 COMPOSE_FILE=compose.dokploy.yaml scripts/catalogue-release-switch.sh rollback`
