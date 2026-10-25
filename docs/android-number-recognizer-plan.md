# Plan: try the server's PP-OCRv6 recognizer on the phone for the collector number (Android first)

**Repos:** PokeSingle (`~/StudioProjects/PokeSingle`) for the app work; ScanApp (`~/WebstormProjects/scanapp`) only for reading files and the labels. New branch from latest PokeSingle `origin/main`. **Device:** Galaxy A55 (plugged in, screen on, Auto-Lock off).
**Rules:** behind a build/`/config` switch, off by default; **0 wrong numbers**; no store publishing; open a PR, don't merge; photos and OCR text never in git; diagnostics compiled out of release. This is independent of PR #164/#165 (capture changes). Don't touch auto capture, iOS or staging.

## Why

The server already reads these footers well with **PP-OCRv6** (its full pipeline gets the right card on about 95% of the panel). The phone's ML Kit reads only **46 of 102** labeled numbers on the A55 listing-photo panel, and extra footer crops added nothing (PokeSingle draft #162). If the problem is the reader and not the pixels, running the **same model** on the phone should help, with **no training**.

## Model files (local, read-only, do not commit)

`/Users/ioannischadjiminas/WebstormProjects/scanapp/data/catalogue-completion/20261004-01/runtime-models/`
- `PP-OCRv6_rec_small.onnx` (21.2 MB fp32): text line recognizer
- `PP-OCRv6_det_small.onnx` (9.9 MB fp32): text line detector
- the character dictionary the server uses with the recognizer: find it in the ScanApp `.venv` RapidOCR package (`rapidocr/…`) or in the model metadata, and check which keys file matches `PP-OCRv6_rec_small`. Restrict decoding to the characters a collector number can contain (`0-9`, `A-Z`, `/`, `-`, `#`, `.`).

The server's usage is in `api/app/recognition/ocr.py` (`CardOcr`), with the preprocessing RapidOCR applies: recognizer input height 48, width scaled to the line's aspect (cap about 320), normalization `(x/255 - 0.5)/0.5`, CTC greedy decode.

## Step 1: offline accuracy on the Mac (no phone yet)

Using the 157-photo frozen panel and its labels (`data/latency/android-recognition-parity-20261023/a55-fresh157-per-photo.json`, photos in `frozen-panel/`, labeled collector numbers via `expected_card_ids` and the catalogue export), crop the footer of each photo the same way the app does (still-photo card quad from `a55-fresh157-per-photo.json` or `comparison.json`, straightened card, bottom strip and corners) and run:
- **rec only** on tight line crops (the app's number-region crop trimmed to the ink with a simple horizontal projection), and
- **det + rec** on the whole footer strip, then pick number-like lines.

Compare, on the same crops, against the **ML Kit result** that was captured for the panel (`/tmp/a55-fastpath-ocr-157.json`; copy it to a safe place first) and against the labels. Report: number read rate, **wrong rate (must be 0)**, and the cases only one engine reads. This answers "is the engine the limit?" in about an hour, before any Android work.

**Gate to go on:** PP-OCR reads clearly more labeled numbers than ML Kit with 0 wrong. If not, stop and report: the limit is the photos.

## Step 2: make it phone-sized

- Convert to fp16 weights (or 8-bit weight-only; **not** dynamic activation quantization, which failed for DINOv2) and re-check accuracy against step 1's numbers.
- Pick the runtime: **ONNX Runtime Mobile** (XNNPACK, CPU) or LiteRT. Build the minimal runtime the app already bundles or can add; report APK/AAB size change.
- Delivery: a **downloaded asset pack** (Play Asset Delivery), as with the embedding, so the base app stays the same size. Send nothing until the model is present. Verify its SHA-256.

## Step 3: on the A55

- Implement the footer-strip reader in the Android text pass (`android/.../CardText.kt` + `lib/data/text_pass.dart`), behind `ANDROID_NUMBER_RECOGNIZER` (default off). It runs only when ML Kit gave no catalogue-valid number, on the card's footer crops, in parallel with other work, inside the 300 ms live / 600 ms gallery budget.
- Feed its read through the existing validation (set-total check). A valid number goes in `number`; an invalid but number-like read goes in `number_candidates`.
- Measure on the A55: model load time (cold and warm), inference ms per crop (median and p90), memory, and battery over a 2-minute aiming test.

## Step 4: measure end to end

1. **Listing-photo panel** (157 photos, labels): number read rate and wrong numbers, with the recognizer on and off. (Listing photos are a hard case; also report by bucket.)
2. **Live camera, owner's 10 physical cards** (card list `docs/android-camera-test-cards.csv`; the owner provides it): 30 captures with the recognizer on and 30 off, mixed distance and light. If the live-camera experiment's data (session `android-live-camera-numb`) already exists, reuse it as baseline.
3. **Early answers through staging:** run the panel through the validation runner and report stage 1/1b answers, **0 wrong**, **0 background-check disagreements**.

## Decision

- Reads clearly more numbers with 0 wrong, within budget, and with an acceptable size and memory cost: ship behind `/config`, still off until a holdout confirms.
- No gain: drop it and report. Next idea: the custom number-only model trained on the ~44,000 catalogue reference images (their collector numbers are known, so footers can be labeled automatically, then augmented with blur, glare, tilt and noise).

## Done when

- Step 1's offline comparison is in the PR description (or a short doc), with the go/no-go.
- If it goes on: fp16 accuracy, size, A55 timings, and the end-to-end results are in the PR.
- `flutter analyze` and `flutter test` pass; the release build still launches on the A55; a PokeSingle PR is open, not merged.
