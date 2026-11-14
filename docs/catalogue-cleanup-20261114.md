# Catalogue clean-up release, switched on staging (2026-11-14)

This release does four things in one release on top of K3:
- It removes the 561 unprefixed duplicates of the first English pilot.
- It removes the ten Japanese `M-P` rows that duplicate `MP1`.
- It folds the extra Lugia V into `ja:SP-324`.
- It takes Pocket out of recognition.

The owner agreed to this plan ("i agree", 2026-11-14). The release was switched on staging after the 1,891-photo gate passed. A new phone index was published there afterwards. Production is not touched. The model is unchanged, and no vector was recomputed: vectors were only deleted or moved.

## Switch

| Item | Value |
|---|---|
| Release | `PS-CATALOGUE-EN-JA-CLEANUP1-20261114`, schema `pokesingle_completion_20261114_cleanup1` |
| Parent | `PS-CATALOGUE-EN-JA-REC46-K3-20261114`, schema `pokesingle_completion_20261111_jarec46` |
| Reference features | `/data/reference-features/20261114-cleanup`, manifest sha256 `fa96ea92befe2c1874f8ceeeb7b08f06080980a43c7e639c9ee25c824595d8ef` |
| Artwork bundle | `/data/artwork/20261114-cleanup`, manifest sha256 `388e0f9653b2d0b574d8884b591222e1435946aa7b83d3805679545de9b63b01` |
| SQL | 625 statements in one guarded transaction, sha256 `51ee0d66a735821bd91722fc0cf176bd614685b1eb957862c59dc084a83daa5b` |
| How | `scripts/catalogue-release-switch.sh apply`, `RELEASE_NAME=catalogue-cleanup-20261114`; only the four release lines of the env file changed |
| After | health ok, ready, import `PS-CATALOGUE-EN-JA-CLEANUP1-20261114`, restarts 0, no OOM |
| Rollback | `/etc/scanapp-staging/catalogue-rollback/catalogue-cleanup-20261114` (rollback file points to K3) |

## What changed

| Change | Rows | How |
|---|---:|---|
| Unprefixed duplicates `base1` 102, `swsh3` 201, `sv01` 258 | 561 deleted | Cosine 1.0 with the `en:` twin and a byte-identical image file. Products are moved to the twin. Helper rows are dropped. |
| `ja:M-P-u07..u16` | 10 deleted | These duplicate `ja:MP1-001,002,004,005,007..012`. Products are moved to the MP1 row. |
| `extra-blaziken`, `extra-gengar`, `extra-pikachu-mcdonalds` | 3 deleted | Successors are `ja:S8b-217`, `ja:SM9-103` and `en:2022swsh-7`. |
| `extra-m-tyranitar-ex-089-081` | 1 deleted | Its Cardmarket link moves to `ja:XY7-090`, which keeps its own vector. |
| `extra-lugia-v-326-s-p` | 1 deleted | Its vector and Cardmarket link move to `ja:SP-324`. |
| Pocket (`en:A*`, `en:B*`, `en:P-A*`) | 2,319 lose their vectors | The rows stay as archived catalogue rows and are not deleted. |
| `extra-mew-ex-205-metal` | 1 loses its vector | Its vector is identical to `en:sv03.5-205`. The row stays. |
| `extra-charmander-001-032`, `extra-pikachu-classic-clc008` | kept | Each is the only row for its print. |

Totals:
- Cards: 62,784 → 62,208. That is 561 + 10 + 5 = 576 rows deleted.
- Indexed vectors: 51,817 → 48,934.
- Square vectors: 43,695 → 40,812.
- Artwork regions: 37,796 → 37,478.
- Retrieval segments: 37 before and after.
- Products moved: 470.
- Helpers: 562 dropped and 2 moved.
- New `embeddings_sha256`: `94e7a0c3754ca30981062e32be860a0dcd82e54822a1316caf24dae3f87641b2`.
- New `ids_sha256`: `faeaa9131a88f7094968e07196220a4c36a357149804d8dbdffdca2d71bbaef7`.

Built with `api/scripts/ja_set_recovery/prepare_sql_cleanup.py` (SQL, pad vectors, artwork bundle) and `cleanup_features.py` (feature bundle: hard-linked parent without the deleted rows, re-signed). Both bundles have the same sha256 on this Mac and on the staging host.

## Gate

1,891 photos were replayed against the candidate (local docker, image `scanapp-api-staging:24856ba9`, 3 lanes). They were scored against K3's accepted run with `score_gate.py`. Scoring the K3 run against itself reproduces K3's numbers exactly.

| Panel | Photos | Right first | Wrong first | Right offered | Wrong-first upper bound |
|---|---:|---|---|---|---:|
| dev | 681 | 637 → 637 | 4 → 4 | 663 → 663 | 1.5% |
| dev2 | 238 | 232 → 232 | 0 → 0 | 238 → 238 | 1.6% |
| dev3 | 972 | 938 → 938 | 0 → 0 | 963 → 963 | 0.4% |

Right → wrong: 0. Right no longer offered: 0. Cells lower: none.

22 answers changed, and each was looked at:
- 15 changed only because an old id became its `en:` twin (`base1-44` → `en:base1-44`).
- 5 changed from `uncertain` to `matched` with the same right card: `dev-en-vintage-039`, `sealed-en-vintage-075`, `sealedF-en-modern-007`, `-046` and `-047`. Without the duplicate, the twin no longer competes with itself for the top place.
- 2 lost a deleted extra from their alternatives, and the next candidate entered at the end: `dev2-ja-modern-012` and `sealedF-en-promo-016`.
- 1 changed only the order of its alternatives.

No panel label refers to a deleted or changed row.

## Phone index

| Item | Value |
|---|---|
| Before | `28eaa9f4b1513b280c7806e03e84a5169598db103f01952b5767871c1e94cfc9` (K3 snapshot; 503 once the release was switched) |
| Now | `d40042cbb35dc7f8a8a021ffa67b7bf2af6875ffa499769d52ea6780ebf121f1`, 48,934 rows |
| Row kinds | 46,672 ordinary, 2,260 `language` (`zh-tw`), 2 `reference`, 0 `digital`, 0 `duplicate` |
| Rollback record | `/etc/scanapp-staging/catalogue-rollback/phone-index-cleanup-20261114/ACTIVE.before` |
| Check | manifest 200 inside the container and from `staging-scan.pokesingle.com`; the downloaded meta and ids files match the manifest's sha256; a ranged request on the vectors returns 206 |

How it was built:
1. A snapshot export of the release, run locally with a read-only role (`export_cloud_snapshot.py`).
2. This branch's `export_index.py` with the operational totals.
3. `export_exceptions.json` updated to this catalogue. The list only shrank: unprefixed ids 567 → 2, Latin-only Japanese names 10,276 → 10,274, Pocket 2,319 → 0.

The Pocket and duplicate rows are gone from the index because they are gone from the vectors, not because of a subset rule. The `zh-tw` rows are still in the index, marked `language`.

## Going back

On the staging host, run the following from the code directory:

```
CONFIG_DIR=/etc/scanapp-staging RELEASE_NAME=catalogue-cleanup-20261114 PROJECT=scanapp-scanapp-z1mwj4 COMPOSE_FILE=compose.dokploy.yaml scripts/catalogue-release-switch.sh rollback
```

Then write `28eaa9f4b1513b280c7806e03e84a5169598db103f01952b5767871c1e94cfc9` to `/data/phone-index/ACTIVE.next` and rename it to `ACTIVE`. Both steps are needed: each phone index matches only its own snapshot.

## Not done

- **Schemas `pokesingle_completion_20261111_jarec43`, `_jarec44` and `_jarec45` are not dropped.** Dropping a schema is permanent, and it waits for the owner's explicit confirmation. `jarec44` is the rollback target recorded for K3 (`second-batch-k3-20261114`), so keep it until K3 and this release are both accepted.
- The `zh-tw` rows remain in the server catalogue and in the phone index (marked `language`). Leaving them out of the phone index needs this PR's subset rule deployed on staging.
