# Second batch A2: eight starter products (2026-11-11)

Batch A2 of `docs/second-batch-agent-plan-20261111.md`. Production is not touched.

| Item | Value |
|---|---|
| Release | `PS-CATALOGUE-EN-JA-REC20-A2-20261111`, schema `pokesingle_completion_20261111_jarec20` |
| Parent | `PS-CATALOGUE-EN-JA-REC19-A1-20261111` (`..._jarec19`, not written) |
| Code staging runs | main `a916be4` (no server code change) |
| Features / artwork / images | `20261111-second-batch-a2` (features, artwork), `/data/reference-images/ja-20261111-second-batch-a2` (184 files, not mirrored to the CDN) |
| Rollback folder | `/etc/scanapp-staging/catalogue-rollback/second-batch-a2-20261111` |
| Switch | `prepare` + `forward`, FORWARD OK, healthy, restarts 0, OOM false |

## Rows

184 Limitless rows, all added with a Limitless image (736 x 1,024), every image looked at by eye
against name, number and set mark. Japanese names. Catalogue: 62,287 cards (was 62,103).

| Set | Added | Id style |
|---|---:|---|
| Starter Set V Fighting `SAf` | 25 | `ja:SAf-001`..`024`, energy `u01` |
| Starter Set V Grass `SAg` | 24 | same |
| Starter Set V Lightning `SAl` | 25 | same |
| Starter Set V Fire `SAr` | 24 | same |
| Starter Set V Water `SAw` | 24 | same |
| Charizard VMAX Starter Set `SCr` | 21 | `ja:SCr-001`.. |
| Grimmsnarl VMAX Starter Set `SCd` | 20 | set id `jr-grimmsnarl-vmax-starter-set` (its code `SCd` is already a Traditional-Chinese set of ours) |
| Charizard VMAX Starter Set 2 `SC2` | 21 | `ja:SC2-001`.. |

66 scannable, 118 printing alternatives (108 with an existing twin), 0 display-only, 0 left out.
No Cardmarket link was added (all 184 are on the browser worklist). No `check` rows.

## Gate

Replay of the 1,891 stored photos (this branch's code, image `24856ba9`, four containers),
against the step-1 stored run.

| Panel | Photos | Right first | Wrong first | Upper bound |
|---|---:|---|---|---|
| dev | 681 | 637 -> 637 | 4 -> 4 | 1.5% |
| dev2 | 238 | 232 -> 232 | 0 -> 0 | 1.6% |
| dev3 | 972 | 938 -> 938 | 0 -> 0 | 0.4% |

Right -> wrong 0; right card always still offered; no cell lower. Four photos differ; all four keep
status and first answer. Two of them (`sealed-en-modern-022`: `swsh3-201` written without `en:`
in an alternative; `sealed-ja-vintage-074`: `ja:SI-251` from A1 offered as one more alternative) are
as in the A1 record. The other two are judged here:

| Photo | Change in the alternatives | Verdict |
|---|---|---|
| `sealedF-ja-modern-061` | new A2 card `ja:SAg-001` offered | Accepted: a same-art printing choice |
| `sealedF-ja-promo-028` | `SMP-008` replaced by the existing `XYP-095` in the 8-entry list; first answer `SMP-249` unchanged, status unchanged | Accepted and logged as wrong -> wrong (neither is the right card). The same photo on JAREC18 gives the stored answer again, so the change comes from this release; the cause was not traced |

## Not measured
Real camera, app build, iPhone, phone hint numbers on Japanese cards, a phone index (not
rebuilt), Cardmarket links, artifact checksums (`MANIFEST` not set).

## Going back
`CONFIG_DIR=/etc/scanapp-staging RELEASE_NAME=second-batch-a2-20261111 PROJECT=scanapp-scanapp-z1mwj4 COMPOSE_FILE=compose.dokploy.yaml scripts/catalogue-release-switch.sh rollback`
