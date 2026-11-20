# Second batch A3: 30th Celebration (`M6a`), rows with a full-size image (2026-11-12)

| Item | Value |
|---|---|
| Release | `PS-CATALOGUE-EN-JA-REC25-A3-20261111`, schema `pokesingle_completion_20261111_jarec25` |
| Parent | `PS-CATALOGUE-EN-JA-REC20-A2-20261111` |
| Code staging runs | main `a916be4` (no server code change) |
| Artifacts | features `20261111-second-batch-a3r`, artwork `20261111-second-batch-a3r`, images `/data/reference-images/ja-20261111-second-batch-a3` (not mirrored to the CDN) |
| Rollback folder | `/etc/scanapp-staging/catalogue-rollback/second-batch-a3-20261111` |
| Switch | `prepare` + `forward`, FORWARD OK, healthy, restarts 0, OOM false |

## Rows
49 rows (TCGdex list, Limitless image 736 x 1,024; every image looked at by eye): numbers 003-103 that we lacked and
the eight basic energies (`ja:M6a-u01`..`u08`). Japanese names; set name as held (`30th CELEBRATION`).
Catalogue 62,336 cards (was 62,287). 34 scannable, 15 printing alternatives, 0 display-only, 0 left out.
The 45 rows without a full-size image (104-158, Mew B/G/R) are in batch B.

**First build failed the gate and was changed.** The first build made all 49 scannable. With the 15
Pikachu cards (019, 020, 023, 024, 030, 031, 032, 034, 036, 037, 038, 041, 042, 045, 046) in the index, two sealed promo
photos (`sealedF-ja-promo-065`, `sealed-ja-promo-045`) went from a right first answer to a wrong one, and for one the
right card was no longer offered (55 answers changed in all; the 14 differing photos run again on an idle machine gave
the same). Without just those 15 vectors both photos return to the stored answers (tested). The 15 stay in the
catalogue as printing alternatives (features, no vectors); the schema of that first build (`..._jarec21`) was never served.

## Gate (1,891 photos, step-1 method, against the step-1 stored run)

| Panel | Photos | Right first | Wrong first | Upper bound |
|---|---:|---|---|---|
| dev | 681 | 637 -> 637 | 4 -> 4 | 1.5% |
| dev2 | 238 | 232 -> 232 | 0 -> 0 | 1.6% |
| dev3 | 972 | 938 -> 938 | 0 -> 0 | 0.4% |

Right -> wrong 0; right card always offered; no cell lower. 11 photos differ, none in the first answer or the status:
only the lower alternatives. New offers are A1/A2/A3 cards or existing look-alikes (`M6a-051`, `M6a-100`, `M6a-084`,
`M6a-028`, `SI-251`, `SAg-001`, `XYP-280`, `XYP-095`), judged as same-art printing choices (accepted by design); where an
older alternative dropped out of the 8-entry list (`DPS-092`, `PMCG3-028`, `SMP-325`, `SP-109`, `SMP-008`,
`jr-battle-starter-deck-raichu-004`) it is not the right card: wrong -> wrong, accepted and logged. `sealed-en-modern-022`
writes one alternative as `swsh3-201` (id style), same card.

## Not measured
Real camera, app build, iPhone, phone hint numbers on Japanese cards, a phone index (not rebuilt), Cardmarket
links (all 49 on the browser worklist), artifact checksums (`MANIFEST` not set).

## Going back
`CONFIG_DIR=/etc/scanapp-staging RELEASE_NAME=second-batch-a3-20261111 PROJECT=scanapp-scanapp-z1mwj4 COMPOSE_FILE=compose.dokploy.yaml scripts/catalogue-release-switch.sh rollback`
