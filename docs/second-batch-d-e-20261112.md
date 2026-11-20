# Second batch D and E: English rows and found images (2026-11-12)

Two releases on staging, on top of C. Production is not touched. Code staging runs: main `a916be4` (no server code change).

| | D | E |
|---|---|---|
| Release | `PS-CATALOGUE-EN-JA-REC36-D-20261112` | `PS-CATALOGUE-EN-JA-REC37-E-20261112` |
| Schema | `pokesingle_completion_20261111_jarec36` | `pokesingle_completion_20261111_jarec37` |
| Parent | REC34-C | REC36-D |
| Features / artwork | `20261112-second-batch-d2` | `20261112-second-batch-e` |
| Rollback folder | `/etc/scanapp-staging/catalogue-rollback/second-batch-d-20261112` | `.../second-batch-e-20261112` |
| Switch | FORWARD OK, healthy, restarts 0, OOM false | same |

Catalogue after E: 62,531 cards. No image is mirrored to the CDN.

## D: seven English rows (D1 and D2 of the plan)
The release scripts now take English rows (`JAREC_LANGUAGE=en`; letter numbers like `B`, unpadded numbers like `det1-25`).

| Card | Image | Treatment |
|---|---|---|
| `en:mep-099` Greninja ex, `en:mep-100` Sylveon ex | pokemon.com card image (`MEP_EN_99.png`, `MEP_EN_100.png`, the source of our other MEP rows), 245 x 342, looked at by eye; flagged to upgrade (under 500 px) | scannable |
| `en:30th-B`, `-G`, `-R` Mew | none: TCGdex lists an image but `assets.tcgdex.net/en/me/30th/<B,G,R>/high.webp` returns 404 | display-only |
| `en:mep-120` Celebratory Fanfare, `en:det1-25` Lt. Yoshida | none on TCGdex, pokemon.com or pokemontcg.io | display-only |

Gate: the 1,891 answers are identical to those on C (no answer changed in any field). Unlike batch B, these display-only rows lowered no stored answer.

## E: nine 30th Celebration (`M6a`) secret rares
Images from the official card search (`pokemon-card.com`, folder `M6a`, 868 x 1,212; the LEGEND half 480 x 687). The official list
has no numbers: each image's footer was read by eye and matched to the TCGdex row. Added: 140 ニューラ, 141 ひかるセレビィ, 142 ルギア,
146 メタグロス, 150 ゲンガー, 152 ダークライ＆クレセリアLEGEND, 154 レックウザEX, 155 ゲノセクトEX, 158 ソルガレオGX. All 9 scannable.
The official folder holds only the regular prints of the other secret-rare names (104-135), so those images would be the wrong card; they stay out.

Gate: right -> wrong 0, right card always offered, no cell lower, upper bounds 1.5% / 1.6% / 0.4%. Against D, three photos differ, only in
the alternatives, first answer and status unchanged: `sealed-ja-older-013` (`PCG1-024`) and `sealed-ja-vintage-016` (`PMCG4-041`) are
offered `M6a-146`, `sealedF-ja-modern-039` (`BW5-Brn-037`) is offered `M6a-154`: reprints of the same art, accepted by design;
`CP6-102` dropped from one list: wrong -> wrong, logged.

## Other sites tried
Bulbapedia, Bulbagarden Archives and TCG Collector answer with a Cloudflare challenge (not solved; on the worklist). PokeDataVault has no
Japanese 30th Celebration page. The LEGEND-deck folders `L2-Sb`/`L2-Sh` are 162 x 226 everywhere found.

## Not measured
As in A1; Cardmarket links; the phone index.

## Going back
`CONFIG_DIR=/etc/scanapp-staging RELEASE_NAME=second-batch-e-20261112 PROJECT=scanapp-scanapp-z1mwj4 COMPOSE_FILE=compose.dokploy.yaml scripts/catalogue-release-switch.sh rollback`
(then `second-batch-d-20261112` for D).
