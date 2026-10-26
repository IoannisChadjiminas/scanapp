# Android live card finder — step 1 bench (OpenCV), 2026-10-26

Step 1 of `docs/android-live-card-detection-plan-20261026.md`. No phone, no app change. Counts only; photos and per-photo results stay out of git (per-photo JSON is in the shared notes folder, keyed by corpus id).

## Verdict against the gate

**Not met.** The gate is at least 80% of corpus photos with the card found. Plain Canny finds a quad in 37% of photos (23% within 5% of the reference); a multi-threshold variant finds 57% (40% within 5%). False outlines on frames with no full card are 22–29%. Do not move to step 2 with this finder unchanged. The corpus is also a poor proxy for live frames (see Caveats), so the number understates what a phone might see, but nothing here supports the 80% gate.

## What ran

- `api/scripts/live_card_bench/bench.py` (OpenCV 5.0, numpy): the finder, the reference scoring, the negatives, the summary.
- `api/scripts/live_card_bench/vision_reference.swift`: runs the same Vision requests as `CardWarp.quads` / `quadsInImage` (rectangles 0.55–0.82, confidence ≥ 0.6, min size 0.2, up to 6, plus document segmentation; image shrunk to 1024 px) on macOS and dumps every candidate.
- Finder (as the plan and `CardWarp.swift` specify): frame shrunk to 320 px long edge, grey, Gaussian blur, Canny, dilate, contours, convex hull, polygon fit to four corners (epsilon 2–5% of perimeter), aspect (short/long side) 0.62–0.82, area at least 20% of the frame. Largest first.
  - `canny`: one Canny with median-based thresholds.
  - `multi`: three fixed Canny threshold pairs merged, then a 5x5 close.
- Reference: the gallery detector's quad for each photo, picked with a port of `pickGalleryCard`'s border and size rules (drops quads touching two or more borders, over 95% or under 8% of the photo; the largest wins). The slab-label and holder rules are not ported. 213 of 312 photos have a reference quad. For the other 99 the gallery detector found nothing usable (mostly the card fills the photo and its edge is the border).
- Corner error: mean distance of the four corners to the reference, as a share of the frame diagonal, best of four rotations.
- Frames without a full card, cut from the 213 photos with a reference: up to four background strips outside the card (at least 30% of each side; 116 frames) and, for every photo, a left half and a top half of the card (426 frames). 542 in total. Real table, hand and empty-box frames are not in the corpus.
- Run locally on the Mac. Finder time: 1.0 ms median (canny), 1.1 ms (multi), p90 1.5 ms at 320 px on the Mac; not an A55 number.

## Results (312 photos)

| | canny | multi |
|---|---:|---:|
| Quad found, all photos | 114 / 312 (37%) | 179 / 312 (57%) |
| Quad found, photos with a reference | 82 / 213 (38%) | 126 / 213 (59%) |
| Quad found, photos without a reference | 32 / 99 | 53 / 99 |
| Within 5% of the reference (best candidate) | 50 / 213 (23%) | 85 / 213 (40%) |
| Within 5% (first candidate) | 48 | 83 |
| Within 2% (best candidate) | 39 | 54 |
| Corner error, median / p90 (best candidate) | 2.4% / 17.5% | 2.4% / 27.3% |
| Corner error, median / p90 (first candidate) | 2.9% / 20.7% | 2.6% / 30.5% |

Found by bucket (found / photos): modern raw 39/80 and 70/80; vintage 21/95 and 45/95; Japanese 15/31 and 13/31; slab 33/70 and 27/70; hard cases 5/30 and 21/30 (canny and multi).

False outlines (frames with a quad, out of frames):

| Frame kind | canny | multi |
|---|---:|---:|
| Left half of the card | 31 / 213 | 22 / 213 |
| Top half of the card | 41 / 213 | 102 / 213 |
| Background strips (4 kinds) | 48 / 116 | 33 / 116 |
| All | 120 / 542 (22%) | 157 / 542 (29%) |

A quad inside a background strip or half-card frame is a false outline for auto-capture only if it would fire a photo; the gate is 0 automatic photos with no card in view, so any rate this high needs a stability and fingerprint check on top, as iOS has.

## Caveats

- The corpus is 312 eBay listing images, not camera frames. The reference quad's median area is 57% of the photo, 85 of 213 reference quads cover 70% or more and 51 cover under 30%. Listing photos have varied backgrounds, sleeves, slabs and multi-card layouts (harder than a card on a plain mat), but no motion blur or preview noise (easier than live).
- The reference is a stand-in for the correct card outline, not ground truth. Where the gallery detector missed (99 photos) there is nothing to score; those count only toward "found" rates.
- The iOS live path also runs document segmentation per frame; this bench's reference includes it, the Android finder has no equivalent. Part of the gap is that.
- The negatives are cut from card photos, so a quad found in a half-card frame can be a real edge of the card, not noise.
- Tuning was not attempted beyond the two variants. `multi` roughly shows that edge-map choice alone moves the find rate by 20 points.

## Against the plan

| Gate | Result |
|---|---|
| At least 80% found on the bench corpus | **Fail**: 57% best case (40% correct within 5%) |
| 0 automatic photos with no card in view | Not measured here; 22–29% of no-card frames had a quad |

Suggested next move before step 2: try a better finder on the same bench (colour/gradient edges instead of grey Canny, adaptive threshold, line-based quad fit, tracking across frames), then rerun. Reproduce:

```bash
swiftc -O api/scripts/live_card_bench/vision_reference.swift -o /tmp/vision_reference
/tmp/vision_reference data/photo-corpus-fullsize-20261023/raw > candidates.json
python api/scripts/live_card_bench/bench.py --corpus data/photo-corpus-fullsize-20261023 --candidates candidates.json --out results.json
```
