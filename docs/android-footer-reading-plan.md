# Plan: read the collector number on Android (footer reading)

**Repo:** PokeSingle (`~/StudioProjects/PokeSingle`). Start a new branch from latest `origin/main`, which already includes #161 (raw number candidates).
**Device:** Galaxy A55, plus one older Android phone for the final check.
**Rules:**
- **Every change goes behind a build-time or `/config` switch,** measured on its own.
- **0 wrong numbers** (a read that names a different card than the label), and later **0 wrong early answers**.
- **The text pass must stay within the deadline** (300 ms Android live, 600 ms gallery/manual).
- **Open PRs, don't merge, don't publish.** Photos stay out of git.

## Why

On the A55 157-photo frozen panel (labels in ScanApp `data/latency/android-recognition-parity-20261023/a55-fresh157-per-photo.json`), **70 photos had a readable card name but no valid collector number**, so stage 1/1b couldn't answer.

Two server fixes are already merged, so the remaining gap is **on the phone**:
- **ScanApp #69:** number repair, plus stage 1b on the server's frame.
- **ScanApp #70:** raw `number_candidates` from #161.

They helped little (25 → 27 on the replay), because **most of those photos have no number-like text in the footer at all**. ML Kit doesn't see the number. It's tiny (a few pixels tall at the current crop scale), low-contrast, or sits next to glyphs.

The captured OCR (2,833 ML Kit lines) is at `/tmp/a55-fastpath-ocr-157.json` on the Mac (copy it somewhere safe), and the photos are in ScanApp `data/latency/android-recognition-parity-20261023/frozen-panel/`.

## Step 1: measure the number-read rate against the labels (baseline)

Add a diagnostic mode to the existing harness (PR #157), or a unit benchmark, that runs **only the number reading** on the 157 panel photos, using the app's own corners or the gallery detector. Report against the labels' collector number:
- `number_ok`: the catalogue-valid number equals the label
- `number_wrong`: a valid number that **differs** from the label. **This must stay 0.**
- `number_none`: no valid number
- `candidate_repairable`: no valid number, but one of the raw candidates repairs to the label's number (as ScanApp's `stage1_text_repair.number_variants` would)

Break these down by era (modern bottom-left, vintage bottom-right, TG/GG, promo, Japanese) and record the time per photo (median and p90).

## Step 2: crops that ML Kit can actually read

ML Kit needs characters roughly **≥ 16–24 px tall** to read them reliably. Collector numbers are often under 10 px at the current crop scale.
1. **Footer number crops sized by the card, not by a fixed factor:** scale each crop so the expected number height (about **2.2–2.6% of card height**) becomes about **28–36 px**.
   - modern: bottom-left 40% × 12%
   - vintage: bottom-right 40% × 11% (from the vintage era signals in `card_text.dart`)
   - Japanese: bottom-left with the set-code row
   - TG/GG and promo layouts
2. **Two or three variants per crop, cheapest first, stopping at the first valid number:**
   - greyscale
   - contrast-stretched (levels, or CLAHE-like)
   - a binarized variant (adaptive threshold) for holo and dark foil
3. **Small tiles:** if a crop still has no number-like line, split it horizontally into 2–3 overlapping tiles and read each. ML Kit sometimes skips short text when it's mixed with a long line.
4. **Reuse the decoded, straightened card:** decode and warp once, then crop in memory, so there's no re-encode between crops.

Measure each sub-step's gain in `number_ok` and its cost in ms. Keep only the ones that pay.

## Step 3: a number-only recognizer (if step 2 isn't enough)

If `number_none` is still high after step 2, evaluate a **text-recognition-only** model on the footer crops. There's no detector: the crop is already the number's line.
- **Candidate:** the PP-OCRv6 *rec* model the server already uses (`PP-OCRv6_rec_small.onnx`). Run it through ONNX Runtime Mobile (XNNPACK) or LiteRT, fp16 or 8-bit weight-only, on a 320×48 line crop.
- **Ship it only if:** it reads the number on clearly more photos than ML Kit after step 2, with 0 wrong, at **≤ 60 ms** on the A55 and a size **≤ 15 MB**, delivered as a downloaded asset pack (Play Asset Delivery) like the embedding. Report memory too.
- **Use it only for the number line,** never for names (ML Kit stays the main reader).

## Step 4: send it

The best catalogue-valid number goes in `number` as today. Raw reads that didn't validate go in `number_candidates` (#161). Don't change the deadlines.

## Step 5: measure end to end

1. **Rerun the 157-photo panel on the A55** through staging (the validation runner, with `/config` switches on): stage 1/1b early answers, **0 wrong**, **0 background-check disagreements**, and text-pass median and p90.
2. **A fresh holdout set** of about 150 new full-size labeled photos (internet-corpus rules), never used for tuning. Report the same numbers.
3. **The older Android phone:** a 50-photo subset, plus timing.

## Done when

- **Step 1's baseline and each change's gain** are in the PR description, with `number_wrong = 0` throughout.
- **The A55 panel** shows clearly more early answers than **21** (the live baseline), with 0 wrong and 0 disagreements, and **the holdout confirms it**.
- **Timing budgets hold** on the A55 and the older phone.
- **The PR is open in PokeSingle,** not merged. The recognizer is either measured and rejected, or measured and shipped behind a switch.
