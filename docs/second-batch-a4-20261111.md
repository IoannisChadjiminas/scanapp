# Second batch A4: promos and decks (2026-11-12)

| Item | Value |
|---|---|
| Release | `PS-CATALOGUE-EN-JA-REC26-A4-20261111`, schema `pokesingle_completion_20261111_jarec26` |
| Parent | `PS-CATALOGUE-EN-JA-REC25-A3-20261111` |
| Code staging runs | main `a916be4` |
| Artifacts | features and artwork `20261111-second-batch-a4r`, images `/data/reference-images/ja-20261111-second-batch-a4` (not mirrored to the CDN) |
| Rollback folder | `/etc/scanapp-staging/catalogue-rollback/second-batch-a4-20261111` |
| Switch | `prepare` + `forward`, FORWARD OK, healthy, restarts 0, OOM false |

## Rows
103 of the 107 rows, all with an image (Limitless; the ten Mega promos from the official card search), every image
looked at by eye. Catalogue 62,439 cards (was 62,336). 38 scannable, 65 printing alternatives, 0 display-only.

| Set | Added |
|---|---:|
| Sword & Shield Promos `SP` | 48 (44 + 4 `check` rows resolved below) |
| Black & White promos `BWP` | 16 (14 + 2 `check`) |
| Mega promos `M-P` | 16 (10 official, 6 unnumbered 勝利のしるし) |
| Scarlet & Violet promos `SV-P` | 12 |
| Battle Strength Decks `BKv` 4, `BKt` 3, `BKc` 1 | 8 |
| XY promos `XYP` | 3 |

### The `check` rows
- **Victory Proof (勝利の証), `SP`:** three unnumbered prints (優勝, 2位, 3位). Our `ja:SP-u77` image is the 2位 print. Added the other two
  (`SP-u81`-type ids, from Limitless `NaN1` and `NaN3`).
- **げんきのハチマキ (55 and 136), マオ&スイレン (89 and 256):** our row shows number 055 and 089 (CSS 2021 / Gym stamps). Added 136 and 256.
- **Heavy Ball and Team Plasma Badge, `BWP`:** our `BWP-122` Heavy Ball and `PBG-011` Team Plasma Badge carry no Battle Carnival
  stamp; the Limitless prints do (different art). Added both as new prints.

### Left out (4 rows, on the browser worklist)
`SP` ホップ (5 / 58), きずぐすり (17 / 51), モンスターボール (19 / 54), ビート (27 / 56): our single unnumbered row has no image or number, so
which print we hold cannot be established without the owner's Chrome. The second print of each is not added.

## Gate

| Panel | Photos | Right first | Wrong first | Upper bound |
|---|---:|---|---|---|
| dev | 681 | 637 -> 637 | 4 -> 4 | 1.5% |
| dev2 | 238 | 232 -> 232 | 0 -> 0 | 1.6% |
| dev3 | 972 | 938 -> 938 | 0 -> 0 | 0.4% |

Right -> wrong 0; right card always offered; no cell lower. 14 photos differ against the step-1 run; the 11 of A3 plus three more:
`dev-ja-promo-049` (alternative `S4-025` dropped), `dev2-ja-promo-017` (`BWP-120` replaced by `XYP-382`): wrong -> wrong, accepted and logged;
`sealedF-ja-modern-011`: status uncertain -> printing ambiguous with the right card `SM5S-014` still first and `SP-326` offered as its same-art
printing (accepted by design). No first answer changed.

## Not measured
As in A1; Cardmarket links (all 103 on the browser worklist).

## Going back
`CONFIG_DIR=/etc/scanapp-staging RELEASE_NAME=second-batch-a4-20261111 PROJECT=scanapp-scanapp-z1mwj4 COMPOSE_FILE=compose.dokploy.yaml scripts/catalogue-release-switch.sh rollback`
