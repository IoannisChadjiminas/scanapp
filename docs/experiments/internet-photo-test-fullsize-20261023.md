# Full-size internet photo corpus test — 2026-10-23

## Status

The replacement corpus contains 312 verified full-size listing photos. The gallery-path sanity check and iPhone embedding golden check passed. The physical staging replay is incomplete: the iPhone became unavailable after 90 photos (batch 1: 50/50; batch 2: 40/50). Do not treat the partial stage rates as final corpus rates.

## Collection and image sizes

Images were collected from the eBay Browse API listing `image.imageUrl`, upgraded to the `s-l1600` variant, and checked from the downloaded image itself. `thumbnailImages` were not used. Images with a long edge below 1,000 px were rejected.

| Long edge | Count |
|---|---:|
| 1,000–1,199 px | 67 |
| 1,200–1,599 px | 71 |
| 1,600 px | 174 |

- Total: 312; unique listing pages: 312; missing local image files: 0; rejected for size: 39.
- Long-edge distribution: min 1,000; p10 1,024; median 1,600; p90 1,600; p95 1,600; max 1,600.
- Buckets: modern raw 80; vintage/WotC raw 95; same-artwork reprints 6; Japanese raw 31; slabs 70; hard cases 30.
- Local source manifest and images: `data/photo-corpus-fullsize-20261023/` (private local corpus; do not commit photos or listing text).

## Harness sanity check: 11 vintage iPhone photos

The harness used the real gallery-import path: still-photo `detectCardInPhoto` → corners → production footer/corner text reader. It reproduced the prior result: 10/11 collector numbers read correctly, 0 wrong, 1 abstention. The remaining abstention was Abra. Ten of eleven photos had a detected gallery quad. This is a small sanity fixture, not an estimate of general accuracy.

## iPhone embedding model

- Model: `2ddf6ec79e37/coreml-pal8`; pinned package verification passed using `tool/stage1/verify_ios_archive.py`.
- Golden fixture: 8 embeddings; preprocessing max absolute difference 0; minimum cosine 0.9967156 (gate ≥ 0.995).
- iPhone 15 inference p50 27.12 ms, p90 27.67 ms in the direct golden benchmark. Model state was `ready`.
- The debug diagnostic app loaded the model locally (`embedding.model: ready`) instead of failing its on-demand download.

## Full-size iPhone gallery replay — interim only

Two staging batches have been run with distinct `diagnostic_run` IDs:

| Batch | Diagnostic run | Completed | Stage 1 / 1b answers | Result stages so far |
|---|---|---:|---:|---|
| 1 | `ebay-fullsize-20261023-b01` | 50/50 | 0 | full pipeline 50 |
| 2 | `ebay-fullsize-20261023-b02` | 40/50 at disconnect | 0 | full pipeline 40 |

Interim totals over the 90 completed photos:

- Gallery detector quad: 40/90; a card quad was sent on 41/90; client text sent: 65/90 (name read 63, number read 51); client quality sent: 39/90.
- Client embedding sent: 0/90. The model was ready, but no embedding made the production 250 ms stage-0 deadline: 42 requests were late, 47 had no quad, and 1 quad was invalid.
- Result stages: full pipeline 90/90; stage 1 and stage 1b early answers 0. This is currently a feature-input/deadline limitation, not a measured stage 1 accuracy result.
- Statuses are ordinary full-pipeline outcomes, not ground-truth accuracy: matched 32, uncertain 28, retake 20, printing ambiguous 7, no match 3.
- Upload/recognition time median 4.23 s across these 90; one observed scan took 21.9 s, with 18.5 s in OCR.
- Background-check comparisons: none observed so far because no stage-1 answer was eligible to enqueue a check. The staging health snapshot after these 90 scans reported `stage1_answers=0`, `stage1_checks=0`, and `stage1_disagreements=0` (service ready).

Batch 2’s 40 completed rows were recovered after the device reconnected. The remaining 10 were exported as a separate `ebay-fullsize-20261023-b02tail` diagnostic run, but the app relocked during relaunch before producing results. This document still needs the tail and remaining batches, final review-sheet labeling, and final stage-answer accuracy. No claim of 0 wrong is justified until labels are reviewed.
