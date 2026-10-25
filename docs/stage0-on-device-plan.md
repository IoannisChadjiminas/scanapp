# Stage 0 plan: everything the phone does before upload

**Goal:** every scan (camera and gallery) reaches the server with the phone's own evidence, so the server can stop early (stage 1) when that evidence agrees. Stage 0 only **collects and sends**. Stage 0 changes no server answers.

**Repos:**
- **PokeSingle** (`~/StudioProjects/PokeSingle`): most of the work.
- **ScanApp** (this repo): accepting and logging the new fields only.

**Budget:** all phone work runs in parallel with JPEG encoding, inside **≤ 300 ms** after the still is ready. **The upload never waits past a deadline.** A late or unsure result is simply left out, and the scan works exactly as today.

## What stage 0 sends

| Field | Today | Stage 0 target | Used later by |
|---|---|---|---|
| `card_quad` + `quad_source` | Live camera only | Camera **and gallery**. Raw card → card corners. Slab → **slab outline** (as build 147 does; the card window tested worse) | Server framing |
| `graded` | When the 300 ms slab check answers | Answers on more scans (one recognizer instance, no temporary files) | Grading skip (−24.5% CPU) |
| `client_text` v1 (`name`, `number`, confidences, `engine`, `ms`) | Camera, when `/config client_text` is on | Camera **and gallery** | Footer skip (−7% CPU), stage 1 agreement |
| `client_text` v2: **label fields** (`label_name`, `label_number`, `label_set`, `label_language`, `label_grader`, `label_grade`) | — | For slabs, read from the same text pass | Stage 1/3 slab identity |
| `client_embedding` (384 numbers, float16, base64, ~1 KB, plus `model` id) | — | **iOS first.** The card crop's embedding from the server's own model, converted for the phone | Stage 1 search with no server embedding |
| `client_quality` (`sharpness`, `card_fraction`, `glare`) | — | Measured on the card crop | Retake on the phone; stage 1 gate |

## 1. Card corners everywhere (in progress)

This is already planned in [mobile-gallery-card-detection-plan.md](./mobile-gallery-card-detection-plan.md), and your agent is on it. Keep its rules:
- **Slab → slab outline** with `holder=true`.
- **Raw card → card corners.**
- **The corners must refer to the uploaded JPEG,** after any resize or rotation. Add a test for this; staging showed this is where things break.

**Done when:** at least 95% of camera scans and at least 80% of gallery imports of card photos arrive with `quad_valid=true` (from the server log `scan_summary`).

## 2. One text pass for slab check, card text and label text

This builds on PokeSingle PR #150 (`lib/data/scan_pipeline.dart` `_finalizeJpeg`, `startTextPass`).
- **One recognizer instance kept alive between photos.** Pass bytes, not a temporary file.
- **One recognition pass per photo** feeds:
  - the slab check (all lines)
  - the card text (lines inside the card quad; for slabs, inside the card area below the label)
  - **the label text** (lines inside the slab's top band, for slabs only)
- **Label parsing** in Dart, mirroring the server's `api/app/recognition/label_identity.py`:
  - grader (CGC, PSA, BGS, ACE, Pi…), grade
  - label name ("LUGIA EX", "Charmander")
  - number, keeping letters (`#17HOLO` → `17`, `18a/147`, `SV59`, `TG01`)
  - set line ("Burning Shadows", "CLASSIC COLLECTION")
  - language ("2023 POKÉMON JP" → `ja`)
- **Never** send label words ("PRISTINE", "GEM MINT", "#17HOLO") as `name`, or attack damage ("20", "200") as `number`.
- **Engines:** Apple Vision `.accurate` on iOS; ML Kit Latin on Android (add the Japanese model only if the size cost is small).
- **Deadlines:** 250 ms on iOS, 300 ms on Android.

**Done when:** `client_text` arrives on at least 80% of raw-card scans. On staging, the logged agreement between phone and server name/number is at least 90% on confident reads.

## 3. Quality check on the phone (new)

Bad photos cost the server the most (frame retries, 8–15 s). Catch them before upload:
- **Sharpness:** variance of the Laplacian on the card crop (greyscale, ~512 px).
- **Card fraction:** quad area divided by image area.
- **Glare:** the share of near-white pixels inside the card.
- **Thresholds:** tune them from the staging panel and real scans. **Don't** block the upload at first. Log the values and send them as `client_quality`.
- **Phase 2:** once thresholds are proven, show "Hold steady / move closer / tilt to avoid glare" **before** upload, and skip the upload for clearly unusable photos (live camera only; gallery imports always upload).

**Done when:** the values are logged for every scan and the thresholds are chosen from data. Don't block anything yet.

## 4. Image embedding on the phone (iOS first)

Phase 0 already passed: `docs/experiments/ondevice-embedding-phase0-20261020.md` on branch `claude/device-hints-13ebd5`.
- **Model:**
  - the server's `dinov2_small.onnx` converted to Core ML with **8-bit palettized weights**: **21.9 MB**, **~2.6–3.2 ms** on the Neural Engine (M4 Pro)
  - every crop gave the server's card, or a card the server scores within 0.01 of it
  - model id `2ddf6ec79e37/coreml-pal8`
- **Preprocessing must match the server exactly:**
  - `prepare_full_card(..., 'pad')`: bicubic into 224×224 with black padding
  - ImageNet mean and std
  - NCHW layout
  - L2-normalise in code

  Test it against the golden fixtures `data/latency/ondevice-embedding-20261020/ondevice_golden.npz` (in the ScanApp main checkout, not in git). The palettized model must reach **cosine ≥ 0.995** on each.
- **What to embed:**
  - raw card: the **straightened card crop** from the quad
  - slab: the card window inside the slab (embedding only; keep sending the slab outline as `card_quad`)
- **Delivery:** don't put the model in the install. Download it after install (iOS Background Assets or On-Demand Resources) and send no `client_embedding` until it's there.
- **Android:** convert to LiteRT (or ONNX Runtime Mobile with NNAPI/GPU), and measure speed and cosine on 2–3 real phones, including an old one. Ship Android only if it's under ~50 ms and cosine ≥ 0.995.
- **Expectation, from phase 1 of the experiment:** with today's server pipeline, a phone vector alone saves only ~2.5%. **The value comes in stage 1,** when the server can skip its own work entirely if the phone's vector, number and name agree. Stage 0 sends and logs the vector; it doesn't change answers.

**Done when:** iOS sends `client_embedding` on at least 80% of raw-card scans (once the model is downloaded). The server logs whether the phone vector's top card equals the final answer.

## 5. Server side for stage 0 (ScanApp, small)

- **Accept and log only. Every new field must stay off for answers:**
  - Merge the `client_embedding` parsing and validation from `claude/device-hints-13ebd5` (`api/app/recognition/client_embedding.py`, 1 KB, base64 float16, model id checked), but keep `CLIENT_EMBEDDING=off` for answers.
  - Add `client_text` v2 label fields to the validator (at most 512 → about 768 bytes).
  - Add `client_quality`.
- **New log line `stage0` per scan:**
  - what arrived: quad, text, label, embedding, quality
  - agreement with the final answer (phone name/number, phone label, phone vector's top-1 and its margin)
  - which stage *would* have answered, for planning stage 1
- **`GET /config` switches** for each piece (`client_text`, `client_label`, `client_embedding`, `client_quality`), so each can be turned on per environment without an app release.

## Order

1. **Corners everywhere** (in progress).
2. **One text pass, with label fields.**
3. **Server: accept + log + `stage0` line + `/config` switches.**
4. **Quality values** (log only).
5. **Embedding, iOS:** model download, golden-fixture test, send and log.
6. **Android embedding** after measuring on real phones.

## Measure before stage 1

After a week of staging and early users, report from the `stage0` lines:
- coverage of each field (camera vs gallery, iOS vs Android)
- phone text vs final answer agreement (name, number, label)
- **phone vector top-1 = final answer**, by margin bucket
- **the share of scans where image, number and name all agree.** That's the share stage 1 can answer for about 0.1–0.5 s of server CPU.

## Out of scope for stage 0

- Changing any server answer (that's stage 1).
- Moving recognition fully to the phone (the app would grow to 150–250 MB and lose the 3.4 GB of reference-feature verification).
- Arm servers (re-test after stage 1).
