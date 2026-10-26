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

## Update: the reference features were the first cause (2026-10-26, later)

- Staging sets `REFERENCE_FEATURES_DIR=/data/reference-features/20261017-ja-sets` and `ARTWORK_BUNDLE_DIR=/data/artwork/PS-CATALOGUE-EN-JA-SETH3-20261017`. The stored scans' `reference_features` version (`6584853e7a22`) is the prefix of that bundle's `catalogue_sha256`. Neither bundle was on the Mac. Both are copied read-only into the scratch folder (3.8 GB and 39 MB).
- My catalogue's signature equals the bundle's (`6584853e7a228544`), so the catalogue is the same one.
- The bundle's processing contract is x86_64 with another OpenCV build; this Mac is arm64. The loader refuses it. The runner accepts it only with `--foreign-features`, which is approximate: the features are not byte-identical to the server's.
- The runtime attaches the feature store in `bind_card_languages(catalog)`, which the runner had not called. Now it does.

| Run | Same status | Same first card |
|---|---:|---:|
| before (no bundles) | 136 of 226 (60%) | 146 (65%) |
| bundles, first 20 | 17 of 20 | 16 of 20 |
| bundles, all 226 | **175 of 226 (77%)** | **164 (73%)** |

Still below the 95% gate. Remaining causes, in order of likelihood:

1. The approximate contract match (arm64 OpenCV versus the server's x86_64 build). Measure it by running the runner on the staging host itself (x86_64, same contract), with `persist=False`, off peak.
2. The phone's inputs the runner does not have: card corners, the phone's embedding and confidences.
3. Stored early answers (stage 1) are not separated from full-pipeline results in the stored data.

Runner: `api/scripts/full_bench/run_full.py` (the `--foreign-features` and `bind_card_languages` changes are committed with this note).

## Result on linux/amd64 (the server's platform), 226 uploads

Run in a local linux/amd64 container from the staging requirements (`api/requirements.txt`). The reference bundle's processing contract matches exactly (no override). Same status **175 of 226 (77%)**, same first card **164 (73%)**, the same as the arm64 run with the override. So the arm64 approximation was not the cause. The remaining gap is the inputs the runner does not have: the phone's card corners, embedding and real confidences, plus the stored data not separating stage 1 answers. Timings in the container are emulated and not representative.
