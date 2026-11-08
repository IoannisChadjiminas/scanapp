# Older-era ranking plan: results (2026-11-07, amended 2026-11-08)

Results for `ja-recovery-older-era-ranking-plan-20261107.md`. Nothing on staging or PlanetScale
has changed.

**Status: the held older eras remain blocked.** Family verification (step 3, PR 108) fixes
blurry retakes, including `PCG1-048-2`. It cannot fix `PMCG4-017-2` on the all-eras catalogue:
there the vintage name choice picks a printing (the new Mewtwo promo) before the artwork check
runs. The older-era vectors stay unreleased until the vintage name choice is changed and every
gate in the plan passes.

## Step 0: a scan count, not a demand measure

Staging has no real users. Its scans are the owner's own tests and the regression panels, so the
count below says nothing about how often collectors scan older-era Japanese cards. **No product
decision rests on it.** The held-card mask is decided on product grounds: Japanese vintage is part
of the product.

Source: staging `results.sqlite` (read-only), 10,187 scans from 2026-09-16 to 2026-11-07. A scan
counts when its first card or its confirmed card is a Japanese card in a held era (any era except
Mega Evolution, Scarlet & Violet, Sword & Shield and Sun & Moon). Only scan ids, card ids,
language fields and timestamps were read. No photos or OCR text were read.

| | Scans | Sessions |
|---|---|---|
| All scans | 10,187 | 446 |
| Japanese-language scans (search, detected or requested `ja`) | 2,862 | 299 |
| Held-era first or confirmed card | 1,200 | 104 |
| — in automated bursts (median gap under 15 s, mostly 15–19 Oct) | 1,174 | 97 |
| — **human-paced** | **26** | **7** |

There were 1,366 human-paced scans in total. Of those, 126 were Japanese-language and 26 had a
held-era first or confirmed card. Those 26 split as: XY 7, Original 7, Black & White 6, e-Card 4,
VS 1, other 1. Their statuses were: retake 14, uncertain 10, matched 1, no match 1. Only 2 were
confirmed.

The script, `api/scripts/ja_set_recovery/count_held_era_scans.py`, reads only scan ids, session
ids, timestamps, language fields and card ids.

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

**Passes for what it measures, not for the motivating problem.** On the panel, the inlier leader
never names a wrong artwork, and three current retakes would be fixed. That makes the verifier a
safe tie-breaker. It does not make the older eras scannable: in the real pipeline `PMCG4-017-2`
never reaches the verifier (see the status above and step 3).

The change: families must span languages and reprints. Verified inliers show *shared artwork*,
which is exactly what joins `PMCG4-017`/`web1-042` and `PCG6-075`/`ex11-113`. So step 3 must:

- move the whole artwork family up, never a single card;
- keep today's order inside the family (number, name, **language**, visual).

If it moved only the inlier leader, it would flip the language on `PCG6-075` and possibly on the
four unlabelled photos.

## What this means for the plan

- **Step 3 (family verify)** is worth building. Its fixes so far are modern cards that are
  retakes today.
- **The vintage name choice** must change before any older-era vectors can be released.
- The stored-upload replay is the main gate (plan, "Gates"). The 4 unlabelled cross-language
  leaders still need an eye check.

Files (git-ignored run folder `replay-local/work/`): `families-fail2.jsonl`,
`families-panels.jsonl`, `families-panels-summary.json`, `families-panels.log`.

## Step 3: family verification (built, flag off)

Branch `claude/rank-family-verify` (from `main`): commits `fd528f2` and `3bb74a1`. The setting is
`RANK_FAMILY_VERIFY`, default off, with `LOCAL_VERIFY_FAMILIES=16`. Deeper retrieval (k=100/50)
is left out: the experiment showed it gains little.

A trace of the pipeline's own verifier changed the design. The right artwork was usually not
crowded out. Instead:

- the verifier confirmed it and the misread title vetoed it (`local_artwork_incompatible` →
  retake: `PCG1-048-2`, `SM1S-068-1`); or
- the OCR filter removed it before verification (`S5I-085-2`, `S7D-083-2`).

When the shortlist goes to verification, the flag also checks one reference per artwork family
(reprints and other-language prints), without the OCR filter.

A family that leads (≥ 12 inliers, 1.5× the next family):
- moves up as a whole and keeps today's order inside it;
- its matches join the verified list only when another artwork led, or when nothing was verified;
- otherwise it only stops the OCR-incompatibility retake.

The status is never `matched`.

Panel replay (98 photos, API image `e99c2332` with the branch code mounted):

| Release | Flag | Best/status changes |
|---|---|---|
| served `jarec5` | off | 0 |
| served `jarec5` | on | 3, all fixes: `S5I-085-2`, `S7D-083-2`, `SM1S-068-1` retake → right card (review) |
| all-eras `jarec` | on, vs `jarec` off | 4, all fixes: the same 3 plus `PCG1-048-2` |

The first version moved a trainer-kit Potion photo from one wrong printing to another;
`3bb74a1` removed that.

Tests: 6 new unit tests. The API suite has 1,217 passed and 1 failed, an unrelated `.webp` extension
check in `test_photo_corpus_collect`.

**Not fixed: `PMCG4-017-2` on the all-eras catalogue.** The verifier never runs there: the
vintage name choice (`VINTAGE_NAME_CHOICES`) picks the new Mewtwo promo and the scan ends
`printing_ambiguous`. The held older-era cards therefore still cannot get vectors with this flag
alone; that needs a fix in the vintage name choice. The two base Charizard photos are already wrong
on the served release and do not change.

Before switching the flag on staging: the stored-upload replay (plan, "Gates"), and
`family_verify_ms` measured on the staging CPU.

## Step 3, second version: after the review (2026-11-08)

The review asked for four changes, now on `claude/rank-family-verify` as commit `1af7bb4` (PR 108,
flag still off).

1. **Families by artwork, not title.** Measured on the reference scans, cosine on DINO vectors
   cannot separate reprints from other artworks. Dark Charizard `PMCG4-017`/`web1-042` scores
   0.74 full-card and 0.76 artwork crop; the different-artwork Mewtwo promo scores 0.72 and 0.65.
   The family test is therefore the printing index's own same-artwork check: the
   exposure-normalised illustration thumbnail, correlation ≥ 0.84. It measures:
   - Potion kit reprints: ≥ 0.97
   - Marill EN/JP: 0.96
   - two different Charizards: about 0

   Before verification, rows join a family only when they are full-card twins (≥ 0.95), or when
   titles are equal **and** thumbnails correlate. A title alone never joins. After verification,
   families whose verified members share a title merge. This catches reprints whose scans differ
   (Dark Charizard thumbnails 0.45): two different illustrations cannot both pass the geometric
   check on one photo. The tests now include same-name, different-artwork rows that must stay
   apart.
2. **Depth setting.** `FAMILY_VERIFY_FULL_K` / `FAMILY_VERIFY_ARTWORK_K`, default 20/15 (today).
   Deeper rows are ranked apart and join the shortlist only as members of a decided family.
3. **One SIFT extraction per scan.** `LocalArtworkVerifier.verify(prepared=...)`. The shortlist
   check and the family check share the photo's query features.
4. **Replays on the served API image** `24856ba9`, the image staging runs since 2026-11-07 15:24
   UTC; its `app/` tree is byte-identical to `main`. The `cbbf83b2` image is no longer deployed.

### Gate replays (98 photos, image `24856ba9`)

| Run | Changes |
|---|---|
| served `jarec5`, image as served, vs the earlier `e99c2332` replay | 0 |
| served `jarec5`, branch code, flag off | **0** |
| served `jarec5`, flag on, depth 100/50 | 3, all fixes: `S5I-085-2`, `S7D-083-2`, `SM1S-068-1` retake → right card (review) |
| all-eras `jarec`, flag on, depth 100/50, vs `jarec` as served | 4, all fixes: the same 3 plus `PCG1-048-2` |
| all-eras `jarec`, flag on, depth 20/15 | identical to depth 100/50 |

On this panel the deeper retrieval changes nothing. It only matters when the check runs and the
right card is outside the top 20, and that does not happen here. The setting stays at today's
values unless a panel shows a gain.

### Cost on the staging CPU

16 of the 98 photos trigger local verification. The recorded inputs were timed in a 1-CPU,
700 MB container on staging with the served feature bundle (`bench-staging-20261108.json`):

| Per triggered scan | Median | p95 |
|---|---|---|
| shortlist check (today) | 0.49 s | 1.52 s |
| family check, shared SIFT | 0.28 s | 1.13 s |
| family check, own SIFT | 0.49 s | 1.92 s |
| two extra artwork-crop embeddings (only when the artwork depth is raised) | 0.26 s | 0.27 s |

With the flag on at today's depth, a triggered scan costs about 0.28 s more at the median and
1.1 s more at p95. Untriggered scans cost nothing extra.

### Why `PMCG4-017-2` is still wrong (trace)

The vintage name choice does not pick the printing. It runs after verification, only adds
choices, and never changes the first card. The scan is decided earlier:

- The OCR "name" is the evolution note モンスターカードに重ねて使います, read at 0.995.
- The top five full-card candidates are all newly added cards (Mewtwo promo, Cyndaquil, Bayleef,
  Hitmontop, Articuno) at 0.80–0.82. Dark Charizard is found only by the artwork stream.
- Local verification is skipped. The top score (0.818) is above 0.78, and the close-neighbour
  condition is bypassed because the bogus "name" is confident.

The step 1 experiment showed that once verification runs on this photo, Dark Charizard leads
(`web1-042` 31, `PMCG4-017` 18) and the Mewtwo promo does not verify. The older-era fix is
therefore a change to the verification **trigger** for unnumbered Japanese vintage scans. The
vintage name choice itself needs no change.
