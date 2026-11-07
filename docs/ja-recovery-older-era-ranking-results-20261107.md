# Older-era ranking plan: step 0 and step 1 results (2026-11-07)

Results for steps 0 and 1 of `ja-recovery-older-era-ranking-plan-20261107.md`. Both were
read-only: nothing on staging or PlanetScale changed, and no flag or code in `api/app` changed.

## Step 0: demand

Source: staging `results.sqlite` (read-only), 10,187 scans from 2026-09-16 to 2026-11-07. A scan
counts when its first card or its confirmed card is a Japanese card in a held era (any era except
Mega Evolution, Scarlet & Violet, Sword & Shield and Sun & Moon). Only scan ids, card ids,
language fields and timestamps were read. No photos or OCR text were read.

| | Scans | Sessions |
|---|---|---|
| All scans | 10,187 | 834 |
| Japanese-language scans (search, detected or requested `ja`) | 2,862 | 299 |
| Held-era first or confirmed card | 1,200 | 104 |
| — in automated bursts (median gap under 15 s, mostly 15–19 Oct) | 1,174 | 97 |
| — **human-paced** | **26** | **7** |

There were 1,366 human-paced scans in total. Of those, 126 were Japanese-language and 26 had a
held-era first or confirmed card. Those 26 split as: XY 7, Original 7, Black & White 6, e-Card 4,
VS 1, other 1. Their statuses were: retake 14, uncertain 10, matched 1, no match 1. Only 2 were
confirmed.

Under the plan's rule this is "a handful". Step 2, the held-card mask, is not worth building for
demand alone.

Script: `scratchpad/demand.py`, run over a staging export of ids only.

## Step 1: verifier experiment

`api/scripts/ja_set_recovery/verify_families.py` ran in the local replay container. It used
staging API image `e99c2332`, the all-eras candidate `jarec` with its features and artwork, and
`persist=False`. For each photo it runs the real `recognize_bytes`. It keeps the final frame, the
full-card query vector and the mask, then:

1. Retrieves the full card at k=100 and artwork at k=50.
2. Groups candidates into artwork families by pad cosine ≥ 0.95.
3. Verifies the top 24 families with the existing `LocalArtworkVerifier.verify(limit=24)`.

The proposed rule: a family leads when it has ≥ 12 inliers and at least 1.5× the runner-up.

### The two known failures

| Photo | Scanner on `jarec` | Inlier leader |
|---|---|---|
| `PCG1-048-1` | correct, uncertain | `PCG1-048`, 37 vs 0 ✔ |
| `PCG1-048-2` | **retake** | `PCG1-048`, 38 vs 0 ✔ (would fix) |
| `PMCG4-017-1` | correct, uncertain | no family verified (leaves today's answer) |
| `PMCG4-017-2` | **Mewtwo promo** (`jr-miscellaneous-promos-005`) | Dark Charizard `web1-042`, 31 vs 18 for `PMCG4-017` ✔ |

`web1-042` is the Web-era reprint of the same Dark Charizard artwork. The family is right and the
Mewtwo promo was not verified at all. The pad-cosine family rule did not join the two reprints,
which is a point for step 3 below.

### The 98-photo panel

The panel has 87 labelled photos, 10 unlabelled ("fresh") photos, and 1 that never reached
retrieval.

| Result | Photos |
|---|---|
| Clear leader, right artwork (expected card, or a reprint with the same title) | 57 of 87 labelled (47 the exact expected id) |
| Clear leader, right artwork, **other language** (`PCG6-075` JP → `en:ex11-113` Metagross Star) | 1 (counted above) |
| No clear leader (several families verified, margin too small) | 24 |
| No family verified | 12 |
| Clear leader that contradicts a correct served answer | **0** for the artwork. 1 (`PCG6-075`) would flip the language if families were per-language |
| Served answer is retake, leader is right (would fix) | 3 (`S5I-085-2`, `S7D-083-2`, `SM1S-068-1`) |
| Unlabelled photos with a clear leader in the other language from the served answer | 4: Marill `sv02-204`→`SV2P-073`, Gengar & Mimikyu `SM9-038`→`en:sm9-53`, Mew ex `svp-053`→`SV2a-205`, Mewtwo `svp-052`→`SV2a-183` (not checked by eye) |

The deeper cut helps a little. The expected card is in the full-card top 20 for 77 labelled photos
and in the top 100 for 81. Its family is in the top 24 families for 82.

Time to verify 24 families (amd64 emulation on the Mac): median 316 ms, p95 1.6 s, max 2.1 s.
Staging CPU is not measured yet.

### Verdict

**Pass, with one design change.** Both known failures come out with the right artwork family on
top, or with no decision. No labelled photo gets the wrong artwork. Three current retakes would
be fixed.

The change: families must span languages and reprints. Verified inliers show *shared artwork*,
which is exactly what joins `PMCG4-017`/`web1-042` and `PCG6-075`/`ex11-113`. So step 3 must:

- move the whole artwork family up, never a single card;
- keep today's order inside the family (number, name, **language**, visual).

If it moved only the inlier leader, it would flip the language on `PCG6-075` and possibly on the
four unlabelled photos.

## What this means for the plan

- **Step 3 (family verify)** is worth building. The benefit is not only for held cards: 3 of the 3
  fixes are modern cards that are retakes today.
- **Step 2 (held-card mask)** has almost no demand behind it: 26 human scans in 7 weeks. Build it
  only together with step 3, if at all.
- Before building: an eye check of the 4 unlabelled cross-language leaders, and the stored-upload
  replay as the main gate (plan, "Gates").

Files (git-ignored run folder `replay-local/work/`): `families-fail2.jsonl`,
`families-panels.jsonl`, `families-panels-summary.json`, `families-panels.log`.
