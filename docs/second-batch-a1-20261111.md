# Second batch A1: Start Deck 100 (2026-11-11)

Batch A1 of `docs/second-batch-agent-plan-20261111.md`. One catalogue release on staging.
Production is not touched.

## Release

| Item | Value |
|---|---|
| Release | `PS-CATALOGUE-EN-JA-REC19-A1-20261111` |
| Schema | `pokesingle_completion_20261111_jarec19` |
| Parent | `PS-CATALOGUE-EN-JA-REC18-20261111` (`..._jarec18`, not written) |
| Code staging runs | main `a916be4` (staging checkout; this release changes no server code) |
| Features / artwork | `/data/reference-features/20261111-second-batch-a1`, `/data/artwork/20261111-second-batch-a1` |
| Images | `/data/reference-images/ja-20261111-second-batch-a1` (128 files, not mirrored to the CDN) |
| Rollback folder | `/etc/scanapp-staging/catalogue-rollback/second-batch-a1-20261111` |
| Switch | `scripts/catalogue-release-switch.sh prepare` + `forward`, FORWARD OK, healthy, restarts 0, OOM false, import id matches |

The candidate (schema, features, artwork, images) was first built by an earlier session of
another agent (branch `codex/second-batch-staging`). Its own replay was not usable: it ran the
old staging image code, not this repository's code. All 128 images were looked at again by eye in
this session before the gate was run.

## Rows

128 rows from Limitless `SI`, all added, all with a Limitless image (736 x 1,024). Names are the
Japanese names. Numbered rows keep the 3-digit ids and `/414`. The seven basic energies are
unnumbered: `ja:SI-u02` to `u08` (`u01` is the existing Darkness Energy).

| Set | Added | Scannable | Printing alternatives | Display-only | Left out |
|---|---:|---:|---:|---:|---:|
| SI Start Deck 100 | 128 | 28 | 100 | 0 | 0 |

Catalogue: 62,103 cards (was 61,975); SI 428 cards (was 300). No `check` rows in this batch. No
Cardmarket link was added: all 128 are on the browser worklist (Cardmarket not verified).
Delta Reign: TCGdex still has 141 rows and no art on 2026-11-11 (D4 waits).

## Gate

Replay of the three stored panels (1,891 photos) with this branch's code in the API image
`24856ba9`, the step-1 method, against the stored step-1 run on JAREC18.

| Panel | Photos | Right first, before -> after | Wrong first | Upper bound on wrong first |
|---|---:|---|---|---|
| dev | 681 | 637 -> 637 | 4 -> 4 | 1.5% |
| dev2 | 238 | 232 -> 232 | 0 -> 0 | 1.6% |
| dev3 | 972 | 938 -> 938 | 0 -> 0 | 0.4% |

Right -> wrong 0; the right card is always still offered; no cell lower.

**How this was reached.** The first full run, made with five containers on a machine at load 19,
had 14 answers that differed from the baseline, four of them right -> wrong on English photos
(`dev-en-modern-002`, `dev-r8-en-promo-013`, `dev-r8-en-vintage-041`, `-042`). On an idle
machine the same four photos give the stored answers on both JAREC18 and the candidate, so the
cause was the load (timeouts), not the release. All 14 differing photos were then re-run on the
candidate alone and those results replace the loaded ones; the rest of the run is as first made.
One photo (`dev-ja-vintage-existing-134`) was killed by the memory cap and re-run alone with a
higher cap: same right answer. The replay machine should not be overloaded again; a gate run
needs at most 3 containers.

Two answers still differ after that, both judged:

| Photo | Change | Verdict |
|---|---|---|
| `sealed-en-modern-022` | one alternative is written `swsh3-201` instead of `en:swsh3-201` (the id style of the non-prefixed English rows); same card, same answer | Accepted (same card, same answer) |
| `sealed-ja-vintage-074` | right card `ja:neo3-042` still matched first; the new card `ja:SI-251` is offered as one more alternative | Accepted: a newly added look-alike appears below the right answer. This is the one judgment the table does not state in words; flagged here |

## Not measured

A real camera, the app build, iPhone, phone hint numbers on Japanese cards, a phone index
(not rebuilt, it has none of these cards), Cardmarket links and prices for the 128 cards, the
three artifact checksums (`MANIFEST` was not set for the switch).

## Going back

`CONFIG_DIR=/etc/scanapp-staging RELEASE_NAME=second-batch-a1-20261111 PROJECT=scanapp-scanapp-z1mwj4 COMPOSE_FILE=compose.dokploy.yaml scripts/catalogue-release-switch.sh rollback`
