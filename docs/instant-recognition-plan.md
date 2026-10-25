# Plan: near-instant card recognition on the phone (iOS first, then Android)

**Goal:** when a card stops in front of the camera, show the likely card in about **0.3 s or less**, then confirm it in the background. Do it **without lowering the hard rule: no wrong card is accepted automatically.** The phone's fast answer is a "likely" suggestion. Only agreement between independent signals, or the user's tap, confirms it.

**Repos:** PokeSingle (`~/StudioProjects/PokeSingle`) for the app. ScanApp (`~/WebstormProjects/scanapp`) for the index builder, a logging-only server change, and the offline measurements.

**Rules for every phase:** one switch per piece (`/config` or a build flag), default off until measured; open PRs, don't merge; no store publishing; photos and OCR text never in git; `flutter analyze` clean, `flutter test` passing (the two known failing tests, `inapp_cardmarket_reader_test` and `match_sheet_test`, fail on main too); diagnostics compiled out of release builds.

## Where we are (facts)

| Piece | iPhone | Android (Galaxy A55) |
|---|---|---|
| Phone embeds the card | ✅ DINOv2-small, Core ML 8-bit, 22 MB, downloaded after install (ODR). **27 ms** warm on an iPhone 15 (the 3 ms figure was the Mac) | ⚠️ LiteRT GPU fp16 **132 ms** median, accurate (cosine 0.998). Not shipped (the speed guard and model ID are not finished) |
| Card outline | ✅ Vision, live | ❌ No live card finder. The camera has an aiming box; gallery detection is weak (43 of 157 photos get none) |
| Phone reads name and number | ✅ Vision (10 of 11 vintage numbers right) | ⚠️ ML Kit reads about 45% of numbers. PP-OCRv6 on the phone is being tested (offline: 89 of 102) |
| Server answers from phone embedding + text (stage 1 / 1b) | ✅ working, 0 wrong, background check agrees | ✅ the server side is the same |
| **Card index on the phone** | ❌ | ❌ |
| **Embedding live frames while aiming** | ❌ (only the outline is live) | ❌ |
| **"Likely" card shown by the phone** | ❌ (provisional results come from the server stream) | ❌ |

Index size for the 44,021 indexed cards × 384 numbers: float32 **67.6 MB** (the server's `vectors/pad/embeddings.npy`), float16 **33.8 MB**, int8 **16.9 MB**, product-quantized about **8–17 MB** (to be measured).

The phone's vectors match the server's model closely: cosine ≥ 0.9967 on the golden fixtures, and the phone's top card equals the server's top card on 233 of 258 test crops (the rest are same-artwork English/Japanese pairs and near ties). So the phone's top-1 is a **good guess, not an authority**.

## Design

```
LIVE CAMERA (phone, on device)                           BACKGROUND (confirm)
  frame ─► card crop (outline / aiming box)                ┌─ upload photo + corners + text + embedding
        ─► embed (DINOv2, 27 ms iPhone / 132 ms A55)       │   (stage 1 / 1b on the server, 20–300 ms)
        ─► search local index (top 5, ~10 ms)              ├─ phone number read (Vision / PP-OCR)
        ─► stable for N frames + margin?                   └─ agree? ─► "matched" ; disagree ─► full pipeline
              yes ─► show "Likely: <card>" at once
```

Rules:
- **"Likely" is a suggestion.** It carries a label, shows provisional price info from the server when available, and **never saves or adds to a collection** without confirmation (agreement from the server, or the user's tap).
- **Confirmation uses the gate we already have:** image top-1 equals the card named by the number and name, margin ≥ 0.02 (stage 1), or text names one card and its artwork verifies (stage 1b). The server stays the arbiter for `matched`.
- **Twins:** same-artwork English/Japanese (and Prize Pack) candidates are shown together. The text's language, or the user, decides.
- **Slabs:** out of scope for the first version (embed the card window inside the slab later).
- **Version safety:** the index pack carries the model hash, catalogue version and index hash. The phone shows "likely" only when its index and model match the server's `/config` versions. Otherwise it behaves as today.

## Phase 0: offline feasibility (ScanApp + a Mac script, about 1–2 days)

Use the 157-photo panel, the 312-photo eBay corpus labels, and the simulated phone vectors (`api/scripts/simulate_client_embedding.py`, the Core ML model from branch `claude/device-hints-13ebd5`, or the shipped one):
1. For each photo, take the phone-style crop, embed it, and search the **fp16, int8 and product-quantized** indexes built from the server's `embeddings.npy` (collapse the 561 duplicate IDs, and keep the English/Japanese twin pairs as one "card group").
2. Report **top-1 and top-5 accuracy against the labels** for each index format, and the **margin** distribution for correct and wrong top-1s.
3. Choose the **"likely" rule**: a minimum margin and N stable frames, chosen so the **wrong-likely rate is under 1% of shown likelies** on the panel, and report the share of photos that would show a likely.
4. Pick the index format: smallest that keeps top-5 within 1 point of fp32. Report the final pack size.

**Gate:** top-5 contains the label on ≥ 97% of photos, and a margin rule exists that gives wrong-likely < 1% while showing a likely on ≥ 60% of raw-card photos. If not, stop and report.

## Phase 1: ScanApp, index pack builder and log fields (about 2–3 days)

- `api/scripts/export_phone_index.py`: from the server's index and catalogue, build `index.bin` (chosen format), `ids.json` (card ID, with duplicate groups and twin groups), and `manifest.json` (model sha `2ddf6ec7…`, catalogue version / import ID, index sha256, format, dim, count, build date). Deterministic, with a test.
- Also build `cards.json` (compact): per card ID, name, set name, collector number, set total, language, image URL, for the "likely" screen. Target ≤ 4 MB gzipped.
- `GET /config` returns `phone_index: {version, url, sha256, size}` behind `APP_PHONE_INDEX` (default off).
- **Logging only:** accept `client_likely` (top-3 card IDs, scores, frames-to-stable, time-to-likely) in `stage0`, and log whether the server's final card equals the phone's likely. No behavior change.

## Phase 2: iOS (PokeSingle, about 1–1.5 weeks)

1. **Download and verify the index pack** as an ODR resource, like the embedding model. Verify the sha256 and the version match.
2. **Search:** load the index into memory-mapped storage. Compute dot products with Accelerate (`vDSP`/BLAS, convert fp16 to fp32 in chunks). Return the top 5. Target ≤ 15 ms for 44k × 384.
3. **Live loop:** while a card is in the outline, embed the straightened crop at ≤ 4–5 Hz (27 ms each, plus search), only when the outline is stable and the app is foreground. Pause during capture. Track the **battery and thermal state**: back off the rate when the phone is hot.
4. **Stability rule from Phase 0:** a card becomes "likely" when it's top-1 with the margin for N consecutive frames. Clear it if the outline is lost or the top changes.
5. **UI:** a "Likely: <name> · <set> <number>" chip at once (the thumbnail from the card image URL, cached), the same chip then updates to "Confirmed" when the server and number agree, or switches to the server's answer on disagreement. Never auto-save from "likely" alone.
6. **Start the normal upload in parallel** at the shutter or auto capture, as today. The server's confirmation arrives in about 0.3–1 s.
7. **Diagnostics:** `likely.shown` (time from card-stable, top-3 IDs), `likely.final` (agrees with the server: yes/no). Compiled out of release except the logging fields the server accepts.

**Gate:** on the iPhone 15, time from card stable to likely ≤ 300 ms (median), wrong-likely rate < 1% of shown likelies on 100 real scans (10+ physical cards, varied conditions), and **0 wrong automatic confirmations**. Battery: no more than +10% over a 10-minute scanning session versus today.

## Phase 3: Android (about 1–2 weeks, after the Android pieces below)

Prerequisites, in parallel with iOS:
- **Embedding on the phone:** the LiteRT GPU fp16 model (cosine 0.998, 132 ms median on the A55). Add the speed guard from the earlier review: 20–30 timed runs after warmup, enable only if p90 ≤ 200 ms, and give Android its own model ID (`2ddf6ec79e37/litert-fp16`). At 132 ms, the live loop runs at about 2–3 Hz, so "likely" arrives about 300–600 ms after the card stops.
- **A crop to embed:** Android has no live card finder, so the live loop reads the **aiming box**, which means the card must sit in the guide. For free-form placement, a small corner-finding model (prototype-first plan in the earlier Android discussion) comes later.
- **Number confirmation:** the whole-photo PP-OCR reader (being tested now) or ML Kit.

Then:
1. **Search on Android:** the same index pack (via Play Asset Delivery). Search with a tiny constant-matrix LiteRT model (dot products on the GPU or XNNPACK), or a NEON loop in native code. Target ≤ 30 ms.
2. The same stability rule, UI chip, parallel upload and diagnostics as iOS, with rates and thresholds from the A55 measurements.
3. Measure on 2–3 phones, including an older one. Ship the live "likely" only on devices that pass the speed guard.

**Gate:** same wrong-likely and confirmation rules as iOS; time to likely ≤ 600 ms median on the A55.

## Phase 4 (optional): phone-side confirmation and offline mode

Ship the compact catalogue, and port the server's stage 1 gate (set totals, duplicate collapse, twin rule, number repair) to the phone so it can confirm locally when the vector, number and name agree. Keep the server as the final arbiter for `matched`. This gives offline recognition and removes the wait for the upload.

## Measurement, protocol and success

Per phase, report on the same labeled sets (panel, eBay corpus, and the owner's 10 physical cards with 4–5 scans each):
- time to likely (card stable → chip), time to confirmed, and the full-pipeline time for the scans that still need it
- shown-likely rate, **wrong-likely rate** (must stay under 1%), and **wrong confirmed rate (must be 0)**
- top-1/top-5 accuracy, by raw/vintage/modern/Japanese/slab
- pack sizes, memory, battery, and thermal

**The headline success measure:** the median time from "card stops" to a correct likely card, versus today's median of 4.1 s (p90 7.9 s).

## Risks and open questions

- **Wrong-likely and trust:** a flickering or wrong chip hurts more than a slow answer. The stability rule and a conservative margin are the main defense, and the likely is never auto-saved.
- **Same artwork, many printings:** English/Japanese twins, Prize Pack and reprints. The chip shows the group; the printing choice stays with the text or the user.
- **Index freshness:** each catalogue release needs a new index pack. Define who builds it (a ScanApp release step), how the app updates it (silent background download), and what happens during a mismatch.
- **Android quality:** the 132 ms embedding and no card finder limit the live loop. Expect Android to lag iOS in speed and coverage at first.
- **Battery, heat and memory:** continuous embedding is the main cost. Rate-limit and measure before enabling by default.
- **Slabs and sleeved cards:** lower accuracy; excluded from the first version.
- **Estimates** (days and weeks above) are rough and unvalidated; Phase 0 is the cheap way to learn whether the whole idea works.

## Order of work

1. **Phase 0** (offline, ScanApp): feasibility and the likely rule.
2. **Phase 1** (ScanApp): index pack builder and log fields. In parallel: finish the Android pieces (embedding with the speed guard and model ID, PP-OCR number reader).
3. **Phase 2** (iOS): the index, the live loop, the "likely" chip.
4. **Phase 3** (Android).
5. **Phase 4** (optional): local confirmation and offline mode.
