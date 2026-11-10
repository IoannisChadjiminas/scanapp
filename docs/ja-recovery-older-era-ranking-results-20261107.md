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

## Steps 3 and 4b gate replays, 2026-11-08 (served image `24856ba9`, PR 108 at `7586db4`)

All three flags together (`RANK_FAMILY_VERIFY`, `VERIFY_UNMATCHED_NAME`, `RANK_SPECIES_NAMES`).
Flags-off baselines from the step 2 and vintage runs are reused.

**Step 3 found and fixed one bug.** The family check promoted a different-language printing of
the same artwork on two English uploads: Brute Bonnet got the Chinese print, Comfey the Japanese
one. Commit `087cdc1` limits promotion to the scan's languages. Both uploads are right again.

**Step 4b** (species names, commit `7586db4`) fixes `neo1-072-1`. The trace: a new row,
"Ho-Oh ex", led over ルギア because English-only names were never compared with the Japanese read,
and a stray `30` matched its number.

| Gate | Result |
|---|---|
| `PMCG4-017-2` on all-eras | fixed |
| `neo1-072-1` on all-eras | fixed (step 3 alone: retake) |
| 98 photos, flags off | 0 changes |
| 98 photos, flags on | fixes `PMCG4-017-2`, `PCG1-048-2`, `PCG5-041-1/-2`, `S5I-085-2`, `S7D-083-2`, `SM1S-068-1`; base Charizard now shows the `CLL-003` reprint first, with the original as a printing choice; **`E4-091-1` and `PCG3-064-1`: uncertain → matched, right card** |
| Stored uploads (203), compared with the flags-off baseline | 3 fixes; **`51c3d0bb`: uncertain → matched, right card**; base Charmeleon `49dc3c8a`: one wrong card for another (`ja:PMCG1-017` → `en:xy12-10`, same artwork, `base1-24` still an alternative); `b9c67517`: same wrong card, now with printing choices |
| Vintage (135), all-eras, flags on | 116 first / 14 offered / 0 wrong / 5 retake (served today: 82 / 6 / 17 / 30) |
| Staging CPU | Family check: median 0.44 s, p95 2.3 s extra, on 92 of 203 uploads. Species lookup: about 3 ms per 60 candidates. |

**Gate not met: vintage photos worse than on the served catalogue.**

- **`jr-miscellaneous-promos-014-1`, Surfing Pikachu: right first → `web1-025`.** A regression
  that 4b exposes.
  - `web1-025` has the same illustration in an e-Card frame, and its catalogue name is a
    transliteration (サーフィンピカチュ). That name used to keep it out of artwork verification. With
    species names it resolves to ピカチュウ, enters verification and verifies (86 inliers against
    101).
  - It then leads only because the Pokédex number `No.025` printed on the card is read as a
    collector number and matches its `025`.
  - The number read is the cause. The species rule removed an accidental shield.
- **Same artwork, the reprint now first and the original offered as a printing choice:**
  `PMCG1-021-1` (`CLL-003`), `PMCG2-017-1` (`CLF-006`) and `PMCG2-047-1` (`XYP-261`). The
  English-named reprints now get the same name evidence as the originals, so visual similarity
  decides.
- **Already present with the flags off on all-eras:** `PMCG2-047-2`, matched → uncertain, right
  card.

The older-era vectors stay blocked. Step 5 waits for an owner decision on the items in bold and on
the Pokédex-number read.

## Step 4c gate replays, 2026-11-08 (PR 108 at `7dc6659`, all four flags)

**Compared with 4b:**
- 98 photos (both catalogues), stored uploads (both catalogues) and flags off: 0 changes.
- Vintage panel: 7 changes.
  - Fixes: Surfing Pikachu `jr-miscellaneous-promos-014-1` (right card first, with printing
    choices) and `PMCG3-022-1` (retake → right card).
  - Uncertain → matched on the right card: `PMCG5-041-1`, `jr-southern-islands-u09-2` and both
    `jr-vending-machine-series-3-green-u27` photos.
  - **`neo1-072-1` back to a retake.**

Vintage totals: 117 first / 13 offered / 0 wrong / 5 retake. All 41 held cards are first or
offered.

**Gate not met: `neo1-072-1`.**
- With the Pokédex `249` gone, the only number left is `30`. It matches "Ho-Oh ex" (`030`), and
  "Ho-Oh ex" no longer pays the `249` conflict that held it down in 4b. It leads again,
  0.792 against 0.739.
- The `30` is the resistance value: 抵抗力 / ダメージ `-30`. `NON_COLLECTOR_NUMBER_RE` removes
  `-30` only when no word character precedes the minus (`(?<!\w)`). Kana and kanji are word
  characters, so `ダメージ-30` and `抵抗力-30` pass through as collector `30`.
- That happens on 54 of 135 vintage photos (87 `ダメージ-30` lines, 34 `抵抗力-30`).

4b's fix for `neo1-072-1` therefore rested on one misread number cancelling another.

## Step 4d gate replays, 2026-11-08 (PR 108 at `3e28c1b`, all five flags)

**Compared with 4c:**
- 98 photos (both catalogues), flags off, and stored uploads (both catalogues): 0 changes.
- Vintage panel: 11 changes.
  - `neo1-072-1` fixed: Lugia first, now with no stray footer number left.
  - `PMCG4-053-1`: wrong card → no match.
  - Nine photos uncertain → matched, right card.

**Every gate, with all five flags against the flags-off baselines:**

| Gate | Result |
|---|---|
| `PMCG4-017-2`, `neo1-072-1`, Surfing Pikachu | all right first |
| 98 photos, flags off | 0 changes |
| 98 photos, flags on | 8 fixes (all-eras), 6 (served); no right card lost |
| Stored uploads (203) | 3–4 fixes; no right card lost |
| Vintage (135) against served today | 118 first / 12 offered / **0 wrong** / 5 retake, against 82 / 6 / 17 / 30. All 41 held cards are first or offered. |
| Matched on a wrong card | unchanged: 98 photos 3 → 3, uploads 2 → 2, vintage 0 → 0 |
| Staging CPU | family check +0.44 s median / +2.3 s p95 on scans that run it (step 3 timing); species lookup about 3 ms per scan; the two footer rules are a regular expression each |

**Changes that are not plain fixes, for the owner:**
1. Uncertain → matched on the right card: 98 photos `E4-091-1`, `PCG3-064-1`; upload
   `51c3d0bb`; vintage `PMCG2-017-2`, `PMCG5-020-1`, `PMCG5-041-1`, `neo1-072-2`, `neo2-042-1`,
   `web1-042-1`, `jr-miscellaneous-promos-028-1`, `-029-1`, `jr-southern-islands-u09-2`,
   `-u11-1`, `jr-vending-machine-series-2-red-u02-1`, and both `series-3-green-u27` photos.
   Vintage matched rises from 16 to 28, still with 0 wrong.
2. A same-artwork reprint shown first, with the original as a printing choice: base Charizard
   (98 photos and vintage `PMCG1-021-1`), `PMCG2-017-1` (`CLF-006`) and `PMCG2-047-1`
   (`XYP-261`).
3. One wrong card for another: base Charmeleon upload `49dc3c8a` (`ja:PMCG1-017` →
   `en:xy12-10`, same artwork, `base1-24` an alternative). `b9c67517`: same wrong card, now with
   printing choices.
4. With the flags off on all-eras: `PMCG2-047-2`, matched → uncertain, right card.

No photo loses a right card it had first on the served catalogue, except to a same-artwork
reprint that offers it as a printing choice (item 2).

**Owner decision, 2026-11-08:** all four groups above are accepted (right-card matched upgrades,
same-artwork reprints first with the original offered, the Charmeleon and `b9c67517` wrong-to-wrong
changes, `PMCG2-047-2` matched → uncertain). Step 5 may start.

## Step 5: the real candidate JAREC6, 2026-11-08

`pokesingle_completion_20261108_jarec6` / `PS-CATALOGUE-EN-JA-REC6-20261108` (inactive). JAREC5
plus vectors for 5,995 held older-era cards:
- 5,670 exactly as replayed in the all-eras gates;
- 325 from the JAREC3/4 image batches;
- 229 batch cards stay printing alternatives at the 0.95 twin rule.

Totals: 51,253 pad vectors, 36,668 artwork rows, artwork bundle `20261108-ja-recovery-held`.
Built with `build_held_release.py` and `prepare_sql_held.py`; applied in one transaction (38 s).

**Replays (served image, five flags on):**
- 98 photos and vintage panel: identical to the accepted step 4d results (0 changes).
  Vintage: 118 / 12 / 0 / 5.
- Flags off on JAREC6: `PCG1-048-2` and `PMCG4-017-2` regress. The vectors must never be
  served without the flags.
- Stored uploads: one change against 4d, and one older change the owner never saw:
  1. **`e6c4043e`** (new in JAREC6). The photo is a graded English base Charizard; the panel's
     confirmed id `en:ex14-99` (Alakazam ☆) is a wrong label. Served shows `en:30th-c-001`, the
     same artwork, with `base1-4` as a printing choice. JAREC6 shows
     `ja:jr-miscellaneous-promos-123` first (a Japanese-catalogued Charizard promo of the same
     art, from an image batch), and `base1-4` is no longer a printing choice.
  2. **`b28fa245`** (present on every all-eras run; the 4d report compared all-eras runs with
     the all-eras baseline and missed it). The photo is Drifblim GYM promo `ja:SV-P-235`.
     Served shows the wrong `ja:SMP-260` first; all-eras shows `ja:jr-miracle-of-the-desert-005`
     (Illumise, a different Pokémon). The right card is the first alternative in both.

Gate not met: staging is not switched. Both need a trace.

### Traces of the two upload changes (served JAREC5 flags off against JAREC6 flags on)

**`e6c4043e` (English base Charizard, graded).**
- The new leader `ja:jr-miscellaneous-promos-123` (from the JAREC4 image batch, new vectors
  here) is a real Japanese release: a スペシャルジャンボカード of base Charizard **printed in
  English**, visual 0.82.
- `ranking_languages` keeps an `en` detection only when the visual leader is English or the text
  has English rule words. With a Japanese-catalogued leader and only "Charizard" read, the
  ranking languages become `()`:
  - the English printings lose their +0.05;
  - the family check keeps the leader's language;
  - `base1-4` (27 inliers on served) is no longer verified.
- Cause: a Japanese row with an English-printed reference image. Its jumbo frame keeps it under
  the 0.95 twin rule against `base1-4`.

**`b28fa245` (Drifblim GYM promo `ja:SV-P-235`).**
- The footer `235/SV-P` is read as `235/5V-P`, giving a bogus explicit fraction `235/5` and
  `5V`. That reliable "fraction" conflicts with the right card on served too, which is why
  served shows the wrong `SMP-260`.
- On JAREC6 the held row `ja:jr-miracle-of-the-desert-005` (Illumise, `005`, one of the 5,670
  replayed vectors) takes the stray `5`. It leads at 0.870 despite the species mismatch
  (ルギア-style penalty −0.04).
- Cause: an OCR S→5 misread of the `SV-P` promo code. It exists on served already; the new
  vectors only change which wrong card wins.

## Switched, 2026-11-08 23:01Z

JAREC6b and seven flags on staging. Details, replays and rollback are in
`docs/japanese-set-recovery-finish-plan-20261106.md`. Both JAREC6 upload blockers are fixed in
JAREC6b:
- `b28fa245` Drifblim is now right (`OCR_PROMO_S5_GUARD`);
- `e6c4043e` shows served's answer again (the jumbo Charizard is held).

## Proof panel (Phase T) baseline and the first scanner fix, 2026-11-09

The eBay proof panel (`data/catalogue-gaps/proof-panel-20261109`, seed 20261109) has a
development half of 673 photos and a sealed half of 535. Labels are re-checked for same-name
printings: 2 development and 1 sealed corrections, all holo against non-holo. Sealed runs are
logged in `sealed/runs.log`.

**Staging today (JAREC8, seven flags):**

| Half | Right first | Wrong first (95% Wilson) |
|---|---|---|
| Development | 92.3% | 0.7% [0.3, 1.7] |
| Sealed, run 1 | 94.2% | **2.6% [1.6, 4.3]** |

The sealed wrong rate misses the pass bar (≤1% with an upper bound under 3%). Worst cells:
- modern Japanese, 7.8%;
- English vintage, 4.2%;
- Japanese promos, 3.6%.

**Consequence:** no vector release can pass until the scanner's existing wrong answers come down.
JAREC9 (39 older-era vectors, inactive) changes nothing on any panel, so it is held, and its sealed
run is not spent.

**Development-half wrong answers (5) and their causes:**
1. A bogus name read penalises a Japanese-named original but not its English-named reprint.
   Fixed by PR 110, `RANK_UNMATCHED_NAME`:
   - development half: right first 621 → 625, wrong first 5 → 4, 0 right-to-wrong;
   - matched on a wrong card unchanged everywhere.
2. A twin-held original (no vector) is not offered when its number is read but truncated (Umbreon V
   `S6a-047` behind `S8b-100`; probably Pikachu `DPP-048`). Next fix.
3. Two hard photos: a slab with no name read, and a name strip that read "LV.24".

## Second scanner fix: PRINTING_TITLE_FAMILY (PR 112), 2026-11-09

**Cause.** Umbreon V `S6a-047` (development photo `dev-ja-modern-009`, footer read "047/06") is a
vectorless same-art twin of ブラッキーV `S8b-100`, but it is named "Umbreon V". The printing
review matched by exact name, so the twin was never offered. Pikachu `DPP-048` is not this case: it
has its own vector, different artwork, and loses on the picture. It stays a hard photo.

**Fix (flag, off).** The printing family also gathers same-language rows that share the English
title, still gated by the artwork correlation. Members found only by title are offered and never
choose the card shown first. Coverage is judged on the same-name group.

**Replays on JAREC8 + seven flags + `RANK_UNMATCHED_NAME`:**
- Development half: wrong first 4 → 3 (0.6% → 0.4%), right first 625 unchanged, 0 right → wrong.
- Main panel (98): 0 changes.
- Uploads:
  - 9 wrong → right card offered;
  - 2 right first with a printing choice added;
  - 1 wrong → wrong (logged).
- Vintage: 3 right first with a printing choice added.
- The first build showed two disallowed changes (CLL-003 displacing M6a-137; PMCG3-009 matched →
  uncertain). Both were traced, fixed and re-traced.

**Sealed run held.** Sealed run 1 (staging) was 2.6% wrong first [1.6, 4.3]. The development half is
now 0.4%, with 3 wrong answers left: two hard photos and DPP-048. The two fixes together remove 2 of
the development half's 5 wrong answers. Nothing on the development half points at the rest of the
sealed failures, so a sealed run now would fail the ≤1% bar and only spend the sealed half's
information. The next step is to learn the remaining causes without opening the sealed half:
collect a second development set in the three worst sealed cells (modern Japanese, English vintage,
Japanese promos), with labels eye-checked the same way. Then fix what it shows, and spend one sealed
run on the combined candidate.

## Set totals in replays, two more fixes, and sealed runs 2 and 3, 2026-11-09

**Replay fidelity.** Staging's `/data/catalog.sqlite` holds a `set_totals` table (577 sets). Local
replay datadirs had none, so earlier replays, including sealed run 1, skipped the printed-total
check that staging applies. Every replay below loads staging's table. On the development half this
made staging 5 wrong first (0.7%), not 4.

**Two more flags, both off by default:**
- `OCR_TRAINERS_BANNER` (PR 113): the Sun & Moon "TRAINER'S" banner is not read as a name. It fixed
  Judge SR `SM7a-066`, which had been shown as Gym Trainer.
- `SET_TOTAL_ALIASES` (PR 114): 22 Japanese half-set ids (`XY1-By` and others) find their TCGdex
  total under TCGdex's id (`XY1b`), and SM7a is corrected to /060 (TCGdex lists 50; cards 51–60 are
  commons and uncommons).

**Replays with all four candidate flags (JAREC13, set totals loaded):**

| Panel | Staging wrong first | Candidate wrong first | Right → wrong |
|---|---|---|---|
| Development half (673) | 5 (0.7%) | 3 (0.4%) | 0 |
| Second development set (238) | 3 (1.3%) | 1 (0.4%) | 0 |

The gate panels (98 photos, uploads and vintage) show 41 changes, all allowed by the change table.
They are identical to the PR 112 run, so the two new flags change nothing there.

M Blastoise `XY1-By-015` is still wrong. The photo's full "015/060" is read but not used to look up
cards: only "060" is used as the number. On the picture alone, M Glalie-EX `XY8-Bb-015` comes out on
top, and the right card is not in the top eight.

**Sealed half (535 photos).** Run 2 is the staging baseline with set totals; run 3 is the
candidate. Both are logged in `sealed/runs.log`. Only per-cell counts were read.

| | Right first | Wrong first (95% Wilson) |
|---|---|---|
| Staging (run 2) | 504 (94.2%) | 14 (2.6%) [1.6, 4.3] |
| Candidate (run 3) | 508 (95.0%) | 8 (1.5%) [0.8, 2.9] |

Wrong first per cell, staging → candidate:

| Cell | Staging | Candidate |
|---|---|---|
| Modern, Japanese | 4 | 1 |
| Promo, Japanese | 2 | 1 |
| Unnumbered vintage, Japanese | 3 | 1 |
| Unnumbered vintage, English | 3 | 3 |
| Promo, English | 1 | 1 |
| Numbered older, Japanese | 1 | 1 |
| All other cells | 0 | 0 |

Right first is not lower than staging in any cell, and nothing goes from right to wrong. The upper
bound (2.9%) is under 3%, but wrong first (1.5%) is above the 1% bar, so the candidate **fails**. It
is not merged and not switched on. Set totals do not explain the sealed gap: staging is 2.6% with
them, the same as run 1 without them. The largest cell left is English unnumbered vintage (3), which
none of the fixes touches.

## Owner decision and switch, 2026-11-09 20:04Z

**Decision (owner).** Ship the candidate. It beats staging in every cell, is worse in none, and has
no right → wrong changes. 1.5% wrong first is accepted for this release.

**Spot check first.** Before shipping, 30 random sealed photos (seed `sealed-spotcheck-20261109`)
were shown with their labels and references, and no scan results. The owner and Claude both found
all 30 labels correct, so no relabel or rerun was needed.

**New per-release gate** (replaces the 1% bar as a release gate):
- zero right → wrong;
- no cell lower than staging;
- wrong-first upper bound under 3%.

The 1% wrong-first bar is unchanged as the **Phase E completion criterion**.

**Sealed-panel rules, amended:**
- one sealed run per candidate;
- at most three sealed runs on a panel in total, then refresh the sealed half with new photos before
  any further run;
- before the final Phase E run, grow the sealed half to about 1,000 photos so that 1% can be
  measured.

**Shipped:**
- PRs 109, 110, 112, 113 and 114 merged; main is at `2b0c103` and passes the API suite (1,296;
  the one failure is the existing webp test).
- Staging auto-deployed `2b0c103`. The release env then turned on `RANK_UNMATCHED_NAME`,
  `PRINTING_TITLE_FAMILY`, `OCR_TRAINERS_BANNER` and `SET_TOTAL_ALIASES`, on JAREC13.
- Live check:
  - the flags resolve on;
  - `set_total` on staging's database gives XY1-By 60, XY8-Bb 59, SM7a 60;
  - health ok, no restarts, no OOM kills.
- Rollback: `/etc/scanapp-staging/catalogue-rollback/flags14-20261109/catalogue-release.env.before`,
  archived to `data/catalogue-completion/20261004-01/rollback-archive/flags14-20261109/`.
- Logged as `scanner-flags14-switched` in `data/catalogue-completion/20261004-01/events.jsonl`.

**Next:**
1. Retire the 8 wrong-first sealed photos into the development half and inspect each.
2. Collect replacements, plus 50 more English unnumbered vintage photos for the sealed half.
3. Build the number-led lookup (M Blastoise) and whatever the English vintage misses show.

## The 8 retired sealed photos: inspection and traces, 2026-11-09

The 8 wrong-first photos from sealed run 3 moved to the development half as `dev-r8-*` (sealed now
527, dev 681; logged in `sealed/runs.log`). Inspection found **0 label mistakes and 8 genuine
misses**: each label is confirmed by the photo, and the five slabs by their grading labels too.
Traces use staging's current flags.

**A. A number-confirmed top card is displaced by its same-artwork twin (3).** Re-ranking puts the
right card first, but the decision step promotes the twin that local artwork verification
confirmed. The reasons are `family_verified, local_artwork_used`.
- Professor Oak: read 88/102, Base Set 88 first, then Base Set 2 116/130 shown.
- Vaporeon: read 12/64, Jungle 12 first, then the non-holo 28/64 shown.
- Giratina (Japanese): read 051/096, DPt1-051 first, then English Platinum 10/127 shown.

Fix: verification must not promote a card whose number contradicts a clean full-fraction read.

**B. The fraction's total is used as the collector number (2).**
- Empoleon V SR: "074/070" is filed as unknown and "070" is used as the number, so S10D-070 is shown.
- M Blastoise (second development set): "015/060" filed as unknown, "060" used as the number.

**C. Name and number are read but never used to fetch candidates (2).**
- Flygon: reads "Flygon" and "BW53"; `bwp-BW53` is not shortlisted.
- Pikachu DPP-048: reads "048"; the promo is not shortlisted.

This is the number-led lookup.

**D. Misreads (2).**
- Mew, English Southern Islands: "1/18" read as 18 and 6; shown as the Japanese twin.
- Hitmonchan, PMCG1: the damage "40" is read as the card number; shown as the 20th Anniversary
  reprint.

Also seen: a `base1-88` row without a language prefix appears next to `en:base1-88` in the
shortlist. To check.

## Phase C correction: JAREC14 failed the twin rule, rebuilt as JAREC15, 2026-11-10

**Owner's correction.** Every newly imaged card gets vectors through the JAREC6b gates, and stays a
printing alternative only when its artwork is already indexed. So every card that Phase B imaged and
held back by era was checked again.

**JAREC14 (first build).**
- 383 held cards: 312 got vectors and 71 stayed alternatives under the existing rule (pad cosine ≥ 0.95
  to an indexed card).
- Gate replay against staging (same flags): 0 changes on the main panel (98) and uploads (203).
- Vintage (135, run as 95 + the 40 a stopped container missed): **one change the table does not
  cover.** A Neo Genesis Feraligatr photo (label checked by eye) went from matched to
  `printing_ambiguous`, still first, grouped with two HP 120 Feraligatr cards with different artwork.
  Treated as never accepted.

**Cause.** The new intro-pack Feraligatr (u05) shares its artwork with an indexed premium-file card at
pad cosine 0.922, under the 0.95 cut, so it got vectors. A cosine cut cannot decide "artwork already
indexed": same-art reprints sit as low as 0.80, mostly Energy and Trainer cards reused across deck kits
and the Dawn Dash / Moonlit Pursuit reprints.

**Fix: the twin rule decided by eye.**
- Every vectored card was checked by eye against:
  - its nearest indexed card (cosine ≥ 0.80);
  - every indexed card with the same name (cosine ≥ 0.70, up to three per card).
- Total: 484 pairs (144 + 57 nearest-card pairs, 272 same-name pairs, 11 using staging's reference images).
- 145 cards share artwork with an indexed card. Two Nidoran♀ prints twin only each other: one keeps
  vectors.
- Holding those freed 29 more cards that had been alternatives only through a held batch twin. All
  were checked by eye and are the same art.
- Result: a hold list of 174 cards, `docs/ja-recovery-jarec15-twin-holds-20261110.json`, used through
  `HOLD_FILE`.

**JAREC15.**

| | |
|---|---|
| Schema | `pokesingle_completion_20261110_jarec15` |
| Import | `PS-CATALOGUE-EN-JA-REC15-20261110` |
| Cards that get vectors | 168 |
| Pad vectors | 51,431 |
| New artwork rows | 336 |
| Printing alternatives left | 3,970 |
| Feature manifest | img6 (`96a81264…`) |
| Artwork bundle | `20261110-ja-recovery-vec15` (hashes match on staging) |
| SQL sha256 | `a465199e…` |

The SQL is applied as an inactive candidate. Its gate replay is running.

## JAREC15 on staging, 2026-11-10

Staging switched to `pokesingle_completion_20261110_jarec15` (artwork `20261110-ja-recovery-vec15`) at
about 04:07Z, code unchanged (main `71302d0`), same 11 flags. Health ok, 0 restarts. Rollback files:
`/etc/scanapp-staging/catalogue-rollback/jarec15-20261110` (archived locally); rollback is
`staging_switch_jarec15.sh rollback`.

Gate, replayed against staging JAREC13 with the same code and flags:

| Set | Photos | Changes | Right first | Wrong first |
|---|---|---|---|---|
| Main panel | 98 | 0 | same | same |
| Uploads | 203 | 0 | same | same |
| Vintage | 135 | 0 | same | same |
| Dev | 673 | 59 | 92.7% → 93.3% | 5 → 3 |
| Dev 2 | 238 | 12 | 93.7% → 94.5% | 3 → 1 |

No right → wrong. Every change was wrong → right, uncertain → matched on the right card, a same-art
printing choice, or wrong → wrong. The 8 wrong → wrong (logged): dev-ja-modern-019, -vintage-054,
-vintage-075, -modern-020, -vintage-043, -modern-009, dev2-ja-modern-004, -modern-038. Most now list
the right card as a same-art printing.

### Five-flag candidate: Emolga regression found and fixed

On the dev set the candidate moved `dev-ja-promo-044` (slabbed Emolga BW-P 236) from right first to
PokéPark's Pikachu 004 first. Not covered by the change table, so never accepted. Bisect:
`OCR_DAMAGE_NUMBER_GUARD`. The footer read "60" and "4"; dropping "60" as damage left "4", which named
Pikachu 004. Fix (`e4b9b27`, PR 116): damage-shaped reads are dropped only when they are the footer's
only bare numbers. Emolga is right first again; the 8 retired photos are unchanged (Hitmonchan still
fixed). The candidate is re-gated on every set against staging JAREC15.

## Sealed run 4 and the five-flag staging switch, 2026-11-10

**Candidate re-gate** (JAREC15 + 16 flags on `e4b9b27`, against staging JAREC15 + 11 flags):
- Gate panels (98 + 203 + 135): 8 changes, all accepted.
- Development set, 673 photos: right first 93.3% → 93.5%, wrong first 3 → 3, no cell lower.
- Development set 2, 238 photos: right first 94.5% → 97.5%, wrong first 1 → 0.
- Across both development sets, 33 changes: 25 uncertain → matched on the right card, 8 uncertain
  photos now lead with the right card instead of a wrong one. 0 right → wrong.

**Sealed run 4** (the last run on the 585 composition; staging and candidate each ran once):

| Part | Photos | Right first, staging | Right first, candidate | Wrong first (95% upper bound) |
|---|---|---|---|---|
| Carried over | 527 | 508 (96.4% [94.4, 97.7]) | 509 (96.6% [94.7, 97.8]) | 0 → 0 (0.7%) |
| Never run | 58 | 55 (94.8% [85.9, 98.2]) | 55 (94.8% [85.9, 98.2]) | 0 → 0 (6.2%) |
| All | 585 | 563 (96.2% [94.4, 97.5]) | 564 (96.4% [94.6, 97.6]) | 0 → 0 (0.7%) |

- 13 changes, all accepted: 12 uncertain → matched on the right card (modern JA), 1 uncertain photo
  now leading with the right card. 0 right → wrong; no cell lower than staging. **Gate passed.**
- Carried vs new: 96.6% vs 94.8%, intervals overlap. Not a clear tuning signal; 53 of the 58 new
  photos are unnumbered vintage EN, so the new part is not a like-for-like sample.

**Shipped:**
- PR 116 merged (`2ff2597`) after merging main (shipped-flag defaults); API suite: same 7 existing
  failures as main, 30 more tests passing.
- Staging auto-deployed `2ff2597`; the release env then turned on `RANK_FRACTION_CONFIRMED`,
  `OCR_FRACTION_TOTAL_GUARD`, `NUMBER_LED_LOOKUP`, `OCR_DAMAGE_NUMBER_GUARD` and `LATIN_NAME_TWIN`.
  Health ok, 0 restarts, no OOM kill, 16 flags resolve on.
- Rollback: `/etc/scanapp-staging/catalogue-rollback/flags16-20261110/catalogue-release.env.before`,
  archived to `data/catalogue-completion/20261004-01/rollback-archive/flags16-20261110/`.
- Logged as `scanner-flags16-switched` in `data/catalogue-completion/20261004-01/events.jsonl`.
