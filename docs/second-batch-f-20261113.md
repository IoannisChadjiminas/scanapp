# Second batch F: 30th Celebration and LEGEND-era decks from TCG Collector (2026-11-13)

| Item | Value |
|---|---|
| Release | `PS-CATALOGUE-EN-JA-REC38-F-20261113`, schema `pokesingle_completion_20261111_jarec38` |
| Parent | `PS-CATALOGUE-EN-JA-REC37-E-20261112` |
| Code staging runs | main `a916be4` |
| Artifacts | features and artwork `20261113-second-batch-f`, images `/data/reference-images/ja-20261113-second-batch-f` (not mirrored to the CDN) |
| Rollback folder | `/etc/scanapp-staging/catalogue-rollback/second-batch-f-20261113` |
| Switch | FORWARD OK, healthy, restarts 0, OOM false |

## Rows
74 rows that batch B left out, now with images from TCG Collector (read in the owner's Chrome with the owner's approval), 320 x 447,
each looked at by eye against name and printed number (151/103 is printed upside down on the LEGEND top half). Flagged to upgrade later.
Catalogue 62,605 cards (was 62,531). 55 scannable, 19 printing alternatives.

| Set | Rows | Ids |
|---|---:|---|
| 30th Celebration `M6a` 104-135, 151, Mew B/G/R | 36 | `ja:M6a-104` .. `ja:M6a-R` |
| Tyranitar Constructed Standard Deck (official folder `L2-Sb`) | 19 | `ja:jr-tyranitar-constructed-standard-deck-001`..`019` |
| Steelix Constructed Standard Deck (`L2-Sh`) | 19 | `ja:jr-steelix-constructed-standard-deck-001`..`019` |

The official list showed 20 rows per deck: バンギラス and ハガネール were listed twice. TCG Collector shows each deck with 19 cards (001-019/019),
so the second entry is not a card and is left out. The two new Pikachu ex (126, 127) are held as printing alternatives from the start,
because new Pikachu vectors moved promo Pikachu photos to a wrong first answer in A3.

Batch B left these rows out because image-less rows lowered stored answers. With images, the replay shows no such effect.

## Gate (1,891 photos, against the step-1 stored run)

| Panel | Photos | Right first | Wrong first | Upper bound |
|---|---:|---|---|---|
| dev | 681 | 637 -> 637 | 4 -> 4 | 1.5% |
| dev2 | 238 | 232 -> 232 | 0 -> 0 | 1.6% |
| dev3 | 972 | 938 -> 938 | 0 -> 0 | 0.4% |

Right -> wrong 0; right card always offered; no cell lower. 22 photos differ; against E, six new ones, all in the alternatives only
(first answer and status unchanged): new F cards offered (`M6a-131`, `M6a-134`, `M6a-109`, `jr-steelix-constructed-standard-deck-001`),
same-art or look-alike choices, accepted by design; where an older alternative dropped out of the list it was not the right card
(wrong -> wrong, logged).

## Going back
`CONFIG_DIR=/etc/scanapp-staging RELEASE_NAME=second-batch-f-20261113 PROJECT=scanapp-scanapp-z1mwj4 COMPOSE_FILE=compose.dokploy.yaml scripts/catalogue-release-switch.sh rollback`
