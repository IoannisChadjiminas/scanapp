# Plan: how well does the Android camera read the collector number on real cards?

**Why:** on the A55 listing-photo panel, ML Kit read only **46 of 102** labeled collector numbers, and enhanced footer crops added nothing (PokeSingle draft PR #162, report in `/tmp/pokesingle-android-footer/docs/android-footer-reading-results.md`). Listing photos show a small card, so the number may be too few pixels tall to read in any case. **Real camera captures have far more pixels on the number.** This test measures the real scenario.

**Repo:** PokeSingle (`~/StudioProjects/PokeSingle`). New branch from latest `origin/main`.
**Device:** Galaxy A55 (USB debugging on, screen awake, Auto-Lock off, plugged in).
**Rules:** diagnostics only: **no recognition behaviour changes, nothing merged, nothing published.** Photos and OCR text stay out of git. Don't touch staging settings.

## What the owner provides

- **10 physical cards** (mix of vintage, modern, Japanese, promo or TG if available).
- **A list of the 10 cards:** a name and collector number for each. This is the ground truth. Put it in `docs/android-camera-test-cards.csv`: `card_label, name, collector_number, set_total, era`.
- **A phone stand or a stack of books,** a table, and normal room light.
- **Optional:** a card sleeve and a toploader, for the sleeve bucket.

## Capture buckets

For **each of the 10 cards**, take captures under these conditions (6–8 per card, about 70 in total):

| Bucket | How | Per card |
|---|---|---|
| `auto_close` | Live camera, auto capture, card fills about 70% of the frame | 2 |
| `auto_far` | Live camera, auto capture, card fills about 40% of the frame | 1 |
| `manual` | Manual shutter, card centered | 2 |
| `angle` | Tilted about 20–30° | 1 |
| `sleeve` | In a sleeve (and a toploader for 2–3 cards) | 1 |
| `lowlight` | Dim light, and one with glare from a lamp | 1 |
| `screen` (extra) | **A card photo on a monitor** (see below) | 1 |

**The monitor bucket is only a secondary check.** A screen shows moiré, glare and a pixel grid, so don't base decisions on it. Use it only to confirm the pipeline (corners, text, embedding) and compare the number-read rate with the real captures. Report it separately.

## Step 1: add the diagnostic (agent)

In the Android text pass (`lib/data/text_pass.dart`, `CardText.kt`, `lib/data/card_text.dart`), log one **debug-only** event per scan, `number.read`, with:
- `bucket` and `card_label` (set from a small debug UI or an adb intent, so each capture is tagged with the card and condition)
- `capture` (auto/manual/gallery) and the uploaded image size
- the card width in pixels in the **uploaded** image (from the corners), and the number's estimated height in px (≈ 2.4% of the card's height)
- `number_read` (the catalogue-valid number), the raw candidates, and ML Kit's confidence
- `result` against the CSV: `correct`, `wrong`, `none`, `candidate_only`
- time spent in the text pass (median and p90)

Make it **release-safe:** compiled out of release builds, or behind a debug-only switch. No recognition behavior changes.

## Step 2: scan session (owner)

1. Install the diagnostic build on the A55 (the agent does this over `adb`).
2. For each of the 10 cards, take the captures in the table above, tagging each one with the card and bucket. A tiny "tag next capture" screen or adb command is enough.
3. Do **not** retake a capture because it looks bad. Bad captures are data.

## Step 3: report (agent)

Write `docs/experiments/android-camera-capture-<date>.md` in **ScanApp** (aggregate counts only, no photos):
- **Number-read rate and wrong rate by bucket** and by era. A wrong read must be reported with the card, the read and the raw candidates.
- **Read rate against the number's pixel height:** a table of height bins (e.g. <10, 10–16, 16–24, 24–32, >32 px), so the threshold below which ML Kit fails is clear.
- **The same measurements for the listing-photo panel,** so the two can be compared.
- **Text-pass time** (median and p90) per bucket, against the 300 ms live budget.
- **Name read rate** (it matters for stage 1b).
- **The monitor bucket,** separately.
- **A recommendation,** one of:
  1. **Camera captures read well** (say ≥ 85% in the close and manual buckets, with 0 wrong): the problem was the listing photos, not the app. The Android fast path should be judged on camera data, and the footer work stops.
  2. **Reads fail below a pixel height:** the fix is capture-side. Auto capture waits until the card is large enough, or the footer is read from the **original full-resolution still** before the 2000 px downscale. Describe the work.
  3. **Reads fail even with enough pixels:** evaluate a number-only recognizer (PP-OCRv6 rec, as in `docs/android-footer-reading-plan.md` step 3).

## Done when

- **The diagnostic is in a PokeSingle PR** (draft, not merged), with `flutter analyze` clean and the release build free of the diagnostic.
- **At least 60 tagged captures** from the 10 cards.
- **The report is in a ScanApp PR** (not merged), with the recommendation.
