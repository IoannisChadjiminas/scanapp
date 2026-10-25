# Plan: simulate stage 0 on the frozen panel and estimate stage 1

**Repo:** ScanApp (`~/WebstormProjects/scanapp`). Work on a new branch from latest `origin/main`.
**Rules:**
- **Local only:** no deploys, and staging is **read-only**.
- **Never copy credentials** or container environments.
- **Open a PR, but don't merge it.**

## Goal

Before real phone data arrives, estimate **how many scans a cheap stage 1 could answer correctly**, using the frozen photo panels and a simulated phone.

The cascade:

| Stage | Where | What happens |
|---|---|---|
| **0** | Phone | Sends corners, text, slab label fields, photo quality and its own image embedding |
| **1** | Server | Answers in about **0.1–0.5 s of CPU** when the image, the number and the name agree |
| **2–3** | Server | Today's full pipeline, at about 9–12 s of CPU on x86 |

Read first:
- `docs/stage0-on-device-plan.md`: what stage 0 sends
- `docs/experiments/ondevice-embedding-phase0-20261020.md`: on branch `claude/device-hints-13ebd5`
- `docs/experiments/device-text-hints-20261020.md`
- `docs/experiments/slab-text-identity-20261021.md`, `slab-label-identity-20261021.md`, `slab-text-recovery-20261021.md`, `slab-label-language-20261021.md`: these contain the local full-catalogue replay kit

## Tools that already exist (reuse them)

| Purpose | File |
|---|---|
| Phone text (Apple Vision) | `api/scripts/simulate_client_text.py`, `api/scripts/vision_text.swift` |
| Phone embedding (Core ML 8-bit, model id `2ddf6ec79e37/coreml-pal8`) | `simulate_client_embedding.py`, `ondevice_embed_check.py`. Both are on branch `claude/device-hints-13ebd5`: cherry-pick or copy, don't merge the branch |
| Slab label parsing | `api/app/recognition/label_identity.py` (the app's `lib/data/label_text.dart` mirrors it) |
| Stage 0 log line | `api/app/stage0.py` (merged in #63) |
| Replay and compare | `api/scripts/cpu_replay.py`, `api/scripts/compare_replay.py` |
| Catalogue export (public card data, 50,270 cards, 44,021 indexed) | `api/scripts/export_cloud_snapshot.py`. An export from staging is at `auctaro-staging:/root/bench/export` (read-only) |

Panel:
- **The 155-photo frozen panel:** the `staging-reference027` cases used in `docs/experiments/ocr-grading-cpu-20261019.md`.
- **The slab extras:**
  - Lugia auction screenshot: `/Users/ioannischadjiminas/.claude/uploads/43ee8635-fa88-4116-86c8-adb95df4186a/1299f40e-image.png`
  - Charmander CGC screenshot: `/Users/ioannischadjiminas/.claude/uploads/43ee8635-fa88-4116-86c8-adb95df4186a/e1a30482-image.png`

## Steps

### 1. Simulate the phone for every photo

- **`card_quad`:** the server detector's corners with small jitter (≤ 0.5% of the card's short side). For slabs, send the **slab outline**, as the app's build 147 does.
- **`client_text`:** name and number from Vision `.accurate` on the card crop, applying the app's rules (`docs/device-hints-app-plan.md`, section 4).
- **Label fields (slabs):** grader, label name, number (`#17HOLO` → 17, keeping letters like `18a`), set line and language (`2023 POKÉMON JP` → ja).
- **`client_quality`:**
  - sharpness: the variance of the Laplacian on the greyscale card crop at about 512 px
  - card fraction: quad area divided by image area
  - glare: the share of near-white pixels inside the card
- **`client_embedding`:** the Core ML 8-bit vector of the **straightened card crop**. For slabs, use the card window inside the slab for the embedding only. Use the server's `prepare_full_card(..., 'pad')` and `to_nchw` preprocessing, then L2-normalise.

Save the simulated fields next to the panel, so later runs reuse them.

### 2. Replay

Replay the panel with **main's production flags** plus the simulated fields, using the full local catalogue and reference images. Collect the `stage0` log lines and the final answers.

### 3. Estimate stage 1

For each photo, compute what a cheap stage 1 would see:
- **The phone vector's top-1 and margin,** searched against the exported 44,021-card index with brute-force cosine.
- **A catalogue lookup** by the phone's number + name, or by the label's name + number + language for slabs.
- **The agreement rule:** stage 1 answers only when the vector's top-1, the number and the name point to **the same card**, with a clear visual margin.

Report:
- the **share answered at stage 1**, the **share of those that are correct**, and **every wrong stage 1 answer, with photo IDs**
- breakdowns: raw vs slab vs phone photo, and by quality bucket
- for each disagreement, the reason: text misread, number misread, vector wrong, or same-artwork twins (EN/JA)

### 4. Propose a stage 1 gate

- **The thresholds:** suggest the margin, confidence and quality thresholds that give **0 wrong answers** on the panel, and the share of scans they still keep.
- **CPU per stage 1 answer:** estimate the server CPU per stage 1 answer (vector search + database lookup + a light check) against today's full pipeline, on the Mac. Note that x86 costs about the same for search.
- **Slabs:** say whether they should always skip stage 1 and go to the existing slab paths.

### 5. Limits (state them in the report)

- **The simulated phone is a Mac,** using Vision and Core ML. Real iPhone camera photos and the app's real corners differ.
- **The panel is small and hand-picked:** 155 photos, about 100 raw, 50 slabs and 5 phone photos.
- **Android isn't covered.**

## Round 2: rerun with two fixes (added 2026-10-21, after PR #65)

PR #65 (`cursor/stage0-simulation`, `docs/experiments/stage0-simulation-20261021.md`) gave **13 of 157 (8.3%)** at stage 1 with 0 wrong answers. Most of the misses came from two causes that aren't real disagreement. Rerun the **same simulation on the same branch** with both fixes, and compare against round 1.

### Fix A: duplicate card IDs count as one card

The catalogue has **561 cards stored twice**: a legacy ID without a language prefix and an `en:` ID for the same card. For example, `sv01-210` and `en:sv01-210` are both Drowzee, `sv01`, `210`, `en`, with different `image_path`s (`/data/reference-images/sv01-210.webp` vs `/data/reference-images/en/sv01-210.webp`). The vector side already treats these as one card. The **text lookup** didn't, so about 35 photos were marked `ambiguous_text`.
- In the stage 1 lookup, **collapse** `X` and `en:X` (same name, set, number and language) into one card, preferring the `en:` ID. Apply the same rule wherever a candidate list is counted.
- Then report how many `ambiguous_text` photos remain, and why: real reprints, or different sets with the same number and name.
- **Separately, don't change the catalogue in this task.** List the 561 pairs in the report as a catalogue cleanup to do later (which ID the index, prices and Cardmarket links use).

### Fix B: same-artwork EN/JA twins agree

About 15 photos were `vector_wrong` only because the vector picked the **other language of the same artwork**, e.g. `en:sv02-204` Marill vs `ja:SV2P-073` マリル, or `en:sv03.5-181` vs `ja:SV2a-182`.
- **Define twins:** two cards whose reference vectors are almost identical (cosine ≥ about 0.98 in the 44,021-card index), in different languages. Check the threshold on the panel and report it.
- **Rule:** when the vector's top card and the text's card are twins, they **agree**, and the **text's card wins**. The language comes from the text: an English name read means `en`, a Japanese read means `ja`, and for slabs the label's language decides.
- The margin is then measured between the twin pair and the next **non-twin** card.
- Never accept a twin whose number contradicts the text's number (a different set total).

### Report for round 2

- **The same tables as round 1:** answered, correct and **wrong** at margins > 0 and ≥ 0.02, by kind (raw, slab, phone, screenshot).
- **Round 1 vs round 2,** and the share each fix contributes on its own (A only, B only, A + B).
- **Every new stage 1 answer,** with photo ID, card and margin, and **every wrong answer** if there are any. The gate must stay at **0 wrong**.
- **The remaining non-agreeing photos,** grouped by reason. Focus on `no_text` and `text_misread`, and say which could be fixed by better phone reading.
- **The 561 duplicate pairs**, as an appendix or a CSV next to the report.

Update `docs/experiments/stage0-simulation-20261021.md` (add a "Round 2" section) and PR #65. **Don't merge it.**

## Round 3: better collector-number reading on the phone (added 2026-10-21)

Round 2 (PR #65) gave **36 of 157 (22.9%)** at stage 1 with 0 wrong answers (margin ≥ 0.02, Fix A + Fix B, twin cut cosine 0.84). **30 of the 35 photos with nothing to look up had no collector number,** and slab misses were mostly the label read as the card name. Round 3 changes **only the simulated phone's text reading**. Keep everything else from round 2 the same: catalogue, flags, gate, Fix A, Fix B.

Work in the simulation scripts first (Vision on the Mac stands in for iOS). Every rule must be portable to the app: Swift for the Vision calls, Dart for the parsing.

### What to change in the simulated phone's reading

1. **A separate footer read at high resolution.** From the straightened card crop, cut the bottom **12–15%** and upscale it **2–3×**, then run Vision `.accurate` on that strip only. Today the whole card is read at about 1,200 px, so the number is only a few pixels tall.
2. **Corner crops.** Also read the **bottom-left** and **bottom-right** ~35% × 15% of the card separately, since the number sits in one corner depending on the era.
3. **A smaller minimum text height.** Lower `minimumTextHeight` for the footer crops, and keep `usesLanguageCorrection = false`.
4. **Number-aware cleanup, only inside number patterns:** `O→0`, `I`/`l`/`|`→`1`, `S→5`, `B→8`, `Z→2`, and remove spaces around `/`.
5. **Every number format:**
   - `\d{1,3}[a-z]?/\d{1,3}` (`017/032`, `18a/147`)
   - `TG\d{2}/TG\d{2}`, `GG\d{2}/GG\d{2}`, `SV\d{1,3}/SV\d{2,3}`, `RC\d{1,2}/RC\d{1,2}`
   - promos: `SWSH\d{3}`, `SM\d{2,3}`, `XY\d{2,3}`, `BW\d{2,3}`, `SVP ?\d{3}`, `SVP EN ?\d{3}`
   - Japanese promos like `001/S-P` and `123/SV-P`
6. **Check against the catalogue.** Accept a number candidate only if a card with that `printed_collector_number` exists, or with that collector number in a set whose total matches the denominator. Otherwise try the next candidate. So `017/012` is rejected and the strip is re-read. Rank surviving candidates by Vision confidence and position: the corner is preferred, attack-damage positions are rejected.
7. **A second try within the budget.** If neither the footer nor the corners give a valid number, re-read the footer strip once with a **contrast boost** (CLAHE or a simple levels stretch) and a slight sharpen.
8. **Slabs:** apply the server's label filter (`api/app/recognition/ocr.py` `grading_label_line`, plus the `SLAB_TEXT_RECOVERY` rules) on the phone side too. Then:
   - label words are never the card name: PRISTINE, GEM MINT, `2023 POKÉMON JP`, `CLASSIC COLLECTION`, `#17HOLO`, grader names
   - attack damage is never the number
   - when the card footer gives no valid number, use the **label number** (`#17` → 17, `18a/147`) with the label's language
9. **Time budget:** record the simulated phone time per photo (the Mac stands in for an iPhone, so report it as an indication). The footer and corner reads should add **≤ 150 ms** on the Mac.

### Report for round 3

- **Number-read rate:** photos with a valid collector number, round 2 vs round 3, by kind (raw, slab, phone, screenshot).
- **Stage 1 share** at margin ≥ 0.02 and > 0, round 2 (36 and 50 of 157) vs round 3, with **wrong answers (must stay 0)**.
- **The contribution of each change** (footer strip, corners, cleanup, catalogue check, contrast retry, slab label rules), at least as a cumulative table.
- **Every newly answered photo,** with ID, card and margin. Every photo still without a number, with a one-line reason (holo glare, cut off, tiny, unusual format…).
- **The phone-side time added,** median and p90.
- **A short "port to app" list:** which Swift and Dart functions to add or change in PokeSingle (`ios/Runner/CardWarp.swift` `recognizeText`, `lib/data/card_text.dart`, `lib/data/label_text.dart`, `lib/data/text_pass.dart`).

Add a **"Round 3"** section to `docs/experiments/stage0-simulation-20261021.md`, update PR #65, and **don't merge it**.

## Round 4: text-first stage 1b (added 2026-10-21)

Round 3 (PR #65) gave **40 of 157 (25.5%)** at the stage 1 gate with 0 wrong answers. Numbers were read on 113 photos (72%), but **56 photos had a valid number and still didn't agree**, mostly because the vector disagreed or its margin was too small (slabs, glare, same-set look-alikes). Round 4 tests a second cheap path. Keep everything from round 3 unchanged, including stage 1 (round 3 rules).

### Stage 1b rule

Run it only for photos where stage 1 didn't answer:
1. **The text gives exactly one card.** The phone's collector number (catalogue-checked, as in round 3) + the phone's name (for slabs, the label's name, number and language) narrow the catalogue to **exactly one card**, after collapsing duplicate IDs (Fix A). If EN/JA twins remain, pick by the text's language (Fix B). Otherwise stage 1b abstains.
2. **One artwork check on that card only.** Use the existing local artwork verifier (`api/app/recognition/local_match.py` `LocalArtworkVerifier.verify`, plus `propose_frame` projection, as in PR #62) on the uploaded photo, with the phone's corners, against that card's reference.
3. **Answer** only if the artwork **verifies** (the verifier's own inlier threshold; report inlier counts). Otherwise go to the full pipeline.
4. **Never** answer when the vector's top card has a margin ≥ 0.05 over the text's card **and** is a different, non-twin card. That's a strong visual contradiction, so it goes to the full pipeline.

### Report for round 4

- **Stage 1 + stage 1b together:** answered, correct and **wrong**, by kind (raw, slab, phone, screenshot). Stage 1b must add **0 wrong**.
- **Every stage 1b answer,** with photo ID, card, inliers and the vector's top card with its margin. **Every stage 1b near-miss:** verified with few inliers, or rejected by rule 4.
- **Inlier threshold sweep:** answers and wrong answers at several thresholds, and the recommended one.
- **Server CPU per stage 1b answer** (verifier time on the Mac, plus search and lookup), compared with the full pipeline on the same photos.
- **Slabs:** does stage 1b answer them safely with the slab-outline quad?
- **What still goes to the full pipeline,** by reason.

Add a **"Round 4"** section to `docs/experiments/stage0-simulation-20261021.md`, update PR #65, and **don't merge it**.

## Done when

- **Report:** `docs/experiments/stage0-simulation-<date>.md`, covering the numbers above, the proposed gate and every wrong or disagreeing photo.
- **Scripts:** simulation scripts in `api/scripts/` with **one reproducible command** in the report.
- **Tests:** the full API suite passes.
- **PR:** committed on a new branch with a **PR opened, not merged**.
