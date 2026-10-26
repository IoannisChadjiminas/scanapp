# Offline full-pipeline runner: reproduction check (step 0, 2026-10-26)

Plan: `docs/full-pipeline-speed-plan-20261026.md`, step 0. Runner: `api/scripts/full_bench/run_full.py` (the real `recognize_bytes`, `persist=False`, the staging environment from `compose.dokploy.yaml`, a scratch data directory that mirrors the server layout).

**Result: does not reproduce yet.** The gate is at least 95% of uploads with the same status and first card as the stored result. Measured on 226 stored Android manual uploads:

| Run | Same status | Same first card | Shown first card is the owner's |
|---|---:|---:|---:|
| no phone text | 136 of 226 (60%) | 142 (63%) | 117 |
| server's text, confidence 0.95 | 136 (60%) | 146 (65%) | 121 |
| server's text, whole-upload corners, first 20 only | 11 of 20 | 14 of 20 | 11 |

The runner is not used for step 1 or later until it reproduces the stored results.

## What the runs showed

- The runtime loads and is ready from the scratch directory: 50,270 catalogue rows, the 43,695-row research index, the research manifest's catalogue version and DINOv2 checksum (matching the stored scans' `versions`), PP-OCRv6 and rapidocr models, reference images (876 cards).
- The stored scans' `versions` record `reference_features: reference-features-v1:6584853e7a22`. The local reference-features copy (`staging-data-local-20261014`, 17 GB) could not be matched to that version, so this is the first suspect. Not confirmed.
- Skip reasons from the logs with no confidence on the phone text: `low_confidence` on 123 scans, a runner artefact. With confidence 0.95: `no_candidates` on 120 scans. The pipeline builds its candidates from the card's position in the photo; with no corners sent, most scans have none. Sending the whole upload as the card position did not close the gap on 20 uploads.
- `incomplete` (no number on the text) on 87 scans: the server's own read has no number on these uploads, so the phone's text cannot skip OCR on them either.

## Causes to check, in order

1. The reference features version (the stored results used `6584853e7a22`).
2. The phone's inputs the runner does not have: the card corners (the upload is already a guide crop), the phone's embedding and text confidences.
3. Stage 1 early answers, which the stored full-pipeline records do not separate from full runs (`versions.stage` is not written to the case file).

## What is not verified

- The stored results' exact phone inputs and the 25–26 Oct reference-features state.
- Any timing: the Mac timings (median about 2.9 s) are relative only.
