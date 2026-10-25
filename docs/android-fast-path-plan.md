# Plan: raise Android fast-path coverage using the ground-truth labels

**Repos:**
- **PokeSingle** (`~/StudioProjects/PokeSingle`): Android text, corners, model ID.
- **ScanApp** (`~/WebstormProjects/scanapp`): only the analysis scripts and the report. **No server recognition changes** unless step 1 proves a server-side cause.

**Device:** Galaxy A55, plus one older Android phone for the final check.

**Rules:**
- **One change per measured step.** Each fix goes behind a build-time or `/config` switch, so its effect can be measured alone.
- **0 wrong answers at stage 1/1b**, and **0 background-check disagreements**, at every step.
- **Open PRs, don't merge.** No store publishing. Photos stay out of git.

## Starting point (2026-10-24, A55, 157-photo frozen panel)

Data is in `data/latency/android-recognition-parity-20261023/`:
- `a55-fresh157-per-photo.json` (157 rows, with `expected_card_ids`, `android_stage`, `server_stage0`, `quad_sent`, `client_text_sent`, `client_embedding_sent`, `host_early_answer`…)
- `a55-fresh157-corpus-results.json`, `a55-text-results.json`, `a55-fresh157-staging-lines.log`

| | Android (A55) | Mac simulation (Vision, target) |
|---|---|---|
| Early answers (stage 1 + 1b) | **21** (17 + 4), all correct | 53 |
| Embeddings sent | 123 (78%), 0 late | — |
| Corners found | 123 | — |
| Full scanner top card correct | 148/156 | — |

**The losses against the host's 53:**
- **22 × `no_unique_text`**
- **11 × `no_embedding`** (no corners)
- **8 × `artwork_miss`**

**Gate reasons overall:** 83 `no_unique_text`, 34 `no_embedding`, 10 `artwork_miss`, 7 `ambiguous_text`, 2 `visual_contradiction`.

**Release gate (unchanged):** ≥ 50/157 early answers, 0 wrong, embedding p90 ≤ 200 ms on the device, live ≤ 300 ms and gallery/manual ≤ 600 ms end to end before upload.

## Step 1: error analysis against the labels (no code changes)

Script: `api/scripts/android_fastpath_analysis.py` (ScanApp). For every photo, compare the Android phone outputs with **the label** (`expected_card_ids` → the catalogue's name, collector number, printed number and set total).

**Classify each non-answered photo:**

| Class | Test |
|---|---|
| `no_corners` | `quad_sent=false` |
| `name_missing` / `name_wrong` | phone `name` absent / doesn't match the label's name or view_title |
| `number_missing` / `number_wrong` / `number_partial` | phone `number` absent / a different number / right numerator but missing or wrong total |
| `text_ok_lookup_failed` | name and number both match the label, but the gate still said `no_unique_text` or `ambiguous_text` (a lookup bug or catalogue gap: report the candidates) |
| `artwork_miss` | the text named the right card, but verification failed |
| `vector_disagree` | the vector's top wasn't the label's card or its twin |

**Also report, per class:** the counts by bucket (modern, vintage, Japanese, slab, phone) and **10 example photos** each, with crops of the footer and corners as the phone saw them (local images, not committed).

**Optional reference:** run the same photos through the Mac's Apple Vision simulation (`api/scripts/simulate_client_text.py`) and mark where **Vision reads the number and ML Kit doesn't**. That separates "the engine can't" from "the photo can't".

**Output:** `docs/experiments/android-fastpath-analysis-<date>.md` with the class table and the **top 3 fixable causes** ranked by photos recoverable.

## Step 2: Android number and name reading (expected biggest gain)

Fix the top text causes from step 1. Likely candidates:
1. **Bigger crops for ML Kit:**
   - the footer strip and corners at **3–4×** (ML Kit needs taller text than Vision)
   - a **minimum digit height of about 24–32 px** after upscaling
   - try greyscale and contrast-stretched variants of the footer only
2. **A dedicated number crop,** using the layout rules already in Dart:
   - modern cards: bottom-left 35% × 12%
   - vintage cards: bottom-right 35% × 10%
   - read it **in addition to** the full-card pass, within the same budget
3. **A name crop:** the top 15% of the card at 2×, with stage badges and HP removed (as the server does), if `name_missing` is common.
4. **If ML Kit still misses small digits,** evaluate a **number-only recognizer** on the footer strip: the PP-OCRv6 *rec* model the server uses (det is not needed), via ONNX Runtime Mobile or LiteRT.
   - Report the size cost (target ≤ 15 MB, as a downloaded pack like the embedding) and the time (≤ 60 ms).
   - **Ship it only if it clearly beats ML Kit** on the number-read rate.
5. **Parser fixes** that step 1 shows, in the shared Dart rules (they also affect iOS, so rerun the iOS text tests).

**Measure after each change:**
- **Read rates:** number and name read rates against the labels
- **Lookups:** `no_unique_text` count
- **Early answers:** stage 1/1b count, with **0 wrong**
- **Time:** text-pass median and p90

## Step 3: card corners on gallery and manual photos (34 missing)

1. Use `a55-no-quad-sample20.jpg` and the 34 photos to group the failure causes: background clutter, slab, several cards, low contrast, angle, a card touching the photo edge.
2. Fix the top causes in the Android detector (`CardQuad.kt`):
   - looser aspect and size limits
   - edge or contour fallbacks
   - **accept slab outlines** (as on iOS)
   - pick the largest card-shaped quad
3. **Check corner accuracy** against the server's own detected frame on the photos where both exist: the mean corner error as a % of card width. Large errors are a likely cause of `artwork_miss`.

**Measure:** quads found (target ≥ 140/157), and the effect on embeddings sent and early answers.

## Step 4: `artwork_miss` (8–10 photos)

For these photos, compare:
- **Android's corners** against the server's detection, and the corners after mapping to the uploaded JPEG
- **the uploaded JPEG** against the original: size, re-encode quality, EXIF rotation

The repo already has parity checks in `a55-gallery-jpeg-parity-results.json`, `a55-host-crop-parity-results.json` and `a55-stage1-paired-replay-geometry-fixed.json`. Fix any mapping or encoding difference. **Don't** lower the verifier's inlier floor.

## Step 5: Android model ID

Android sent `2ddf6ec79e37/coreml-pal8`, the iOS ID. Change it to **`2ddf6ec79e37/litert-fp16`**, so logs and stats separate the platforms. The server accepts any ID with the same model hash, so no server change is needed. Confirm in the `stage0` logs.

## Step 6: final measurement

1. **Rerun the 157-photo panel** on the A55 with all accepted fixes: early answers (target **≥ 50**), **0 wrong**, **0 disagreements**, and full-scanner top-card accuracy (keep ≥ 148/156).
2. **A fresh holdout,** for the release gate: about 150 newly collected full-size photos (internet corpus rules), labeled with the review sheet and **never used for tuning**. Report the same numbers.
3. **An older Android phone:** the speed guard result (20–30 timed runs after warmup), the text time, and early answers on a 50-photo subset.
4. **Live camera:** about 30 real camera scans on the A55 to confirm the 300 ms budget and that corners and text work in auto capture.

## Done when

- **Step 1's report exists,** and each fix shows its own measured gain.
- **The panel is at ≥ 50/157 early answers with 0 wrong**, and the holdout confirms it.
- **Timing budgets are met** on the A55 and the older phone.
- **The Android model ID is separate.**
- **PRs are open** in PokeSingle (app) and ScanApp (analysis and report), not merged.
