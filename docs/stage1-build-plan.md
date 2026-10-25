# Build plan: stage 1 early exit (app + server)

**Repos:**
- **PokeSingle** (`~/StudioProjects/PokeSingle`): parts A, B and B2.
- **ScanApp** (`~/WebstormProjects/scanapp`): part C.

**Background:** `docs/stage0-on-device-plan.md` and `docs/experiments/stage0-simulation-20261021.md`, rounds 1–3 on PR #65 (branch `cursor/stage0-simulation`). The simulation's stage 1 gate answered **40 of 157 photos (25.5%) with 0 wrong answers**. The search plus lookup costs about **2 ms**, against about 5–9 s for the full pipeline.

**Status:** not live yet. Staging is the test environment. **Production keeps stage 1 off** until the background check shows 0 disagreements over a few hundred real scans.

**Rules:**
- Every server change is behind a flag that's off by default in code.
- Staging turns it on through `compose.dokploy.yaml`.
- **The full API suite and `flutter test` must pass.**
- Open PRs; the owner decides on merges.
- **Never copy credentials** or container environments.

## Part A: app, better collector-number reading (port of simulation round 3)

Port exactly what round 3 measured (see the report's "port to app" list):

| Where | What |
|---|---|
| `ios/Runner/CardWarp.swift` `recognizeText` | A new mode to read a **sub-rectangle** of the straightened card at a given scale. It's used for the footer strip (bottom 14%, 2×), the bottom-left and bottom-right corners, and the footer again with a contrast boost. Lower `minimumTextHeight` for these, and keep `usesLanguageCorrection=false` |
| `lib/data/text_pass.dart` | The order is: full card → footer strip → (only if no valid number) corners → (only if still none) contrast retry. Stay inside the existing deadline (250 ms iOS / 300 ms Android). The added Vision time was a median of 52 ms and a p90 of 138 ms on the Mac |
| `lib/data/card_text.dart` `pickCardNumber` | Digit cleanup only inside number patterns (`O→0`, `I/l/|→1`, `S→5`, `B→8`, `Z→2`). Every format: `017/032`, `18a/147`, `TG01/TG30`, `GG38/GG70`, `SV59/SV94`, `RC29/RC32`, `SWSH020`, `SVP 053`, Japanese `001/S-P` and `123/SV-P`. Reject attack damage |
| **Set-total check (new)** | A small bundled table of valid collector-number totals and prefixes per language (from the catalogue: distinct `printed_collector_number` denominators and prefixes, a few KB). Keep a number only if its format and total exist, so `017/012` is dropped. **Don't** ship the full catalogue |
| `lib/data/label_text.dart` | The server's slab label filter: never take `PRISTINE`, `GEM MINT`, `2023 POKÉMON JP`, `CLASSIC COLLECTION`, `#17HOLO` or grader names as the card name. Use the **label number** (`#17` → 17, `18a/147`) and the **label language** when the footer gives nothing |
| Android | ML Kit Latin with the same crops and Dart rules. Report the read rate on 2–3 devices |

**Tests:**
- Dart unit tests for every number format and for the cleanup rules.
- Tests for the label filter on the Lugia and Charmander label lines.
- The simulation's recorded Vision lines as fixtures, where the repo allows.

## Part B: app, image embedding on iPhone (stage 0 step 4)

Phase 0 passed: `docs/experiments/ondevice-embedding-phase0-20261020.md` on branch `claude/device-hints-13ebd5`. Its conversion script is `api/scripts/ondevice_embed_check.py convert`.

- **Model:** the server's `dinov2_small.onnx` (sha256 `2ddf6ec7…`), converted to Core ML with **8-bit palettized weights**: **21.9 MB**, model id `2ddf6ec79e37/coreml-pal8`. Use the same conversion as phase 0 and the simulation (linear position-embedding resize; cosine 0.998 against the server).
- **Delivery:** not in the install. Download it after install (iOS **Background Assets** or **On-Demand Resources**), verify its sha256, and send no embedding until it's present.
- **Input:**
  - raw card: the **straightened card crop** from the quad
  - slab: the card window inside the slab outline, for the embedding only (keep sending the **slab outline** as `card_quad`)
- **Preprocessing must match the server exactly:**
  - `prepare_full_card(..., 'pad')`: bicubic into 224×224, black padding
  - ImageNet mean and std
  - NCHW
  - L2-normalise in code
- **Send:** `client_embedding` = base64 float16 (384 values, about 1 KB) plus `model` id. Do it only when `GET /config` returns `client_embedding: true`, and within the existing deadline.
- **Tests:**
  - golden fixtures `data/latency/ondevice-embedding-20261020/ondevice_golden.npz` (in the ScanApp main checkout, not in git): cosine ≥ 0.995 for each
  - timing on a real iPhone, reported
- **Android:** see Part B2.

## Part B2: app, image embedding on Android

Without a phone embedding, the stage 1 gate and stage 1b both abstain (`no_embedding`), so **every Android scan goes through the full pipeline**. B2 gives Android the same `client_embedding` as iOS.

- **Model:** the same server model (`dinov2_small.onnx`, sha256 `2ddf6ec7…`), prepared exactly as in phase 0: constant-folded, cut before the final L2 normalisation, and **the same linear position-embedding resize as the iOS conversion**, so iOS and Android vectors match each other.
- **Candidates:** try in this order and keep the first that passes the gates below.
  1. **LiteRT (TensorFlow Lite) fp16** with the **GPU delegate** (NNAPI where it's faster). Convert via `onnx2tf` or ai-edge-torch, whichever gives cosine ≥ 0.995.
  2. **ONNX Runtime Mobile fp16** with the NNAPI or XNNPACK execution provider. It passed accuracy on the Mac (cosine 0.99995 against the server), but its speed is unmeasured.
  3. **8-bit weight-only quantisation** (not dynamic activation quantisation, which **failed**: cosine 0.84 and 60 real answer changes). Use it only if it passes the same cosine gate.
- **Gates, measured on 2–3 real phones, including one older or mid-range device (e.g. 4+ years old):**
  - **cosine ≥ 0.995** against the server vectors on every golden fixture (`data/latency/ondevice-embedding-20261020/ondevice_golden.npz`)
  - **≤ 50 ms** median per card after warm-up, and ≤ 120 ms p90
  - app memory headroom: no OOM on the old device
  - Report the model size (fp16 about 43 MB; 8-bit about 22 MB if it passes).
- **Delivery:** not in the base app. Use **Play Asset Delivery** (fast-follow or on-demand asset pack), verify the sha256, and send no embedding until it's present. Report the base APK/AAB size before and after, which should be unchanged.
- **Input and preprocessing:** identical to Part B (straightened card crop; for slabs, the card window for the embedding only; 224×224 bicubic with black padding; ImageNet mean and std; NCHW; L2-normalise in code). Share the preprocessing in Dart where possible so iOS and Android can't drift.
- **Model id:** a new id per runtime and precision, e.g. `2ddf6ec79e37/litert-fp16`. **The server must accept it:** add the id to the `client_embedding` allow-list in ScanApp (`api/app/recognition/client_embedding.py`) once the gates pass, in a small server PR.
- **Send:** `client_embedding` exactly as on iOS, only when `GET /config` returns `client_embedding: true`, and within the existing deadline (300 ms on Android). On timeout, send nothing.
- **If no candidate passes the gates:** don't ship B2. Report the numbers. Android keeps the full pipeline, and we revisit later (e.g. a smaller distilled model).

**Tests:**
- golden-fixture cosine test, run on a device or emulator in CI where possible
- a timing report per device
- a test that a missing or late model sends no `client_embedding`

## Part C: server, stage 1 with a background check

Reuse:
- the merged stage 0 parsing (`api/app/stage0.py`, PR #63)
- `client_embedding` validation from branch `claude/device-hints-13ebd5` (`api/app/recognition/client_embedding.py`). Cherry-pick the parsing only.

**Flags (code default off):**
- `STAGE1_EARLY_EXIT`: answer at stage 1 when the gate passes.
- `STAGE1_BACKGROUND_CHECK`: after a stage 1 answer, run the **full pipeline in the background** on the same upload and log whether it agrees.
- `STAGE1_SAMPLE_RATE` (0–1): the share of stage 1 answers that get the background check. Use 1.0 on staging and e.g. 0.1 in production later.
- `STAGE1_REQUIRE_CONFIRMATION` (default true): stage 1 answers are shown as needing confirmation until it's switched off.
- Turn all of them on in `compose.dokploy.yaml` (staging), with sample rate 1.0 and require-confirmation true. **Don't change production.**

**Gate**, exactly the simulation's round 2/3 rule:
1. A valid `client_embedding` with the expected model id, and a valid `card_quad`.
2. **Vector top card:** brute-force cosine of the phone vector against the in-memory index (the same index the server already loads).
3. **Text card:** catalogue lookup by the phone's catalogue-valid collector number + name (for slabs, the label name, number and language).
   - **Fix A:** collapse duplicate IDs (`X` = `en:X`), preferring `en:`.
   - **Fix B:** EN/JA same-artwork twins (index cosine ≥ **0.84**) agree, the text's card wins, and the numbers must match.
4. **Answer** only if both give **the same card** and the visual margin to the next different, non-twin card is **≥ 0.02**.
5. **Otherwise** run today's full pipeline, unchanged.

**Stage 1b** (simulation round 4: +13 answers on the 157-photo panel, 0 wrong; flag `STAGE1B_TEXT_VERIFY`, code default off, on in staging). Only when the stage 1 gate above abstains:
1. **One card from the text.** The phone's catalogue-valid collector number + name (for slabs, the label's name, number and language) narrow the catalogue to **exactly one card**, after Fix A and Fix B. Otherwise abstain.
2. **No strong visual contradiction.** If the vector's top card is a different, non-twin card leading the text's card by **≥ 0.05** cosine, abstain (the round 4 near-miss `holdout4_084`).
3. **One artwork check.** Run `LocalArtworkVerifier.verify` on the uploaded photo with the phone's `card_quad`, against **that one card's** reference only, plus `propose_frame` projection as in PR #62. Accept at the verifier's own floor (**10 inliers**; round 4 was 0 wrong from 10 to 60, and the weakest accepted check had 33).
4. **Answer** with `stage: "1b"` and the inlier count in diagnostics. Use the same response, confirmation and background-check rules as stage 1. **Otherwise** run the full pipeline.

Cost on the Mac: median **53 ms** for the artwork check, against 1.7 s latency / 3.0 s CPU for the full pipeline on the same photos. Cards without a reference image abstain.

Replay target for Part C: **stage 1 answers 40 and stage 1b 13 of the 157 photos (53, 33.8%), with 0 wrong**, and every other answer unchanged.

**On a stage 1 answer:**
- Return the card with `status=uncertain` / requires confirmation while `STAGE1_REQUIRE_CONFIRMATION` is on, otherwise `matched`.
- Add `stage: 1` and the margin to the response diagnostics.
- **Skip** server OCR, frame guesses, boundary retries and grading, unless `graded=true`: slabs still get grading, so start it as today.
- Fill prices as usual.

**Background check:**
- Queue the full pipeline on the same bytes in a **low-priority worker** that never competes with live scans: one thread, and skip when the scan queue is busy.
- Log `stage1_check scan_id=… stage1_card=… full_card=… agree=true/false`.
- Store disagreements with the photo when `STORE_CAPTURES` is on.
- Expose a small counter in `/api/v1/health` (stage 1 answers, checks, disagreements).

**Logging:** extend the `stage0` line with `stage1=answered|abstained`, the abstain reason, the margin and timing.

**Tests:**
- Unit tests for the gate (agree, disagree, twin, duplicate ID, missing fields, wrong model id).
- A pipeline test proving the full pipeline is untouched when the gate fails.
- A test that the background check logs a disagreement.
- Replay the 157-photo panel with the simulated stage 0 fields (from PR #65): stage 1 must answer the same ~40 photos with **0 wrong**, and every other answer must be unchanged.

## Order and what each unlocks

1. **Part C (server):** can be built and replayed now with the simulated fields.
2. **Part A (app number reading):** improves stage 1 coverage on real scans.
3. **Part B (iOS embedding)** and **Part B2 (Android embedding):** one of them is required before stage 1 fires on that platform's real scans. They can be built in parallel.
4. **On staging:** scan a few hundred real cards (raw from the camera, slabs, gallery), then read the `stage1_check` disagreements.
5. **Production:** turn on `STAGE1_EARLY_EXIT` with a background-check sample rate of about 0.1, and require confirmation at first.

## Later (separate plans)

- **Slabs at stage 1/1b:** none were answered in round 4. Of the 43 slabs stage 1 left, 31 didn't name one card, 7 named several, and 5 had no reference image. Better slab label reading on the phone, and reference images for the missing cards, come first.
- **Catalogue cleanup** of the 561 duplicate IDs (`docs/experiments/stage0-duplicate-pairs-20261021.csv`). Check the prices, Cardmarket links and index entries that refer to either ID first.
