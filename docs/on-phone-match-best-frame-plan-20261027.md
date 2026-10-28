# Match on the phone from the best live frames (plan, 2026-10-27)

Goal: show the likely card about 1 s after the card is in view, on both phones, without waiting for the upload and the server. The server still checks every scan and its answer is final.

## Idea

While the user aims:

1. Keep the last second of preview frames and pick the 3 sharpest with the card in the guide (the fingerprint model takes a 224 px input, so preview frames are large enough; the still photo stays the input for the server's OCR).
2. Fingerprint those 3 frames on the phone (LiteRT on Android, about 72 to 132 ms each on the A55; Core ML on iPhone, about 27 ms) and average them. Glare and blur change between frames, so the average is steadier than one frame.
3. Search the fingerprint index on the phone. The server index is 43,695 vectors x 384 numbers (67 MB as float32; `data/android-embedding-research-20261023/catalogue/vectors/pad`). As one byte per number it is about 17 MB, and a full search is about 17 million multiply-adds: a few milliseconds, no approximate index needed.
4. Combine with the live text reader (PokeSingle #185) and apply the same rules as the server's stage 1 gate (`api/app/recognition/stage1_gate.py`): the text names the card, the vector top agrees with a margin of at least 0.02, no other card leads by 0.05 or more, the twin guard holds.
5. If it passes, show the card as provisional ("Zorua 095, checking…"). The photo is taken and uploaded as today; the server's answer replaces it. Prices come from the server.

## Rules

Every change behind its own flag, default off. Nothing the phone shows is final; the server's answer always wins and every disagreement is logged. Gate thresholds are the server's, sent to the phone, not copied by hand. Photos never in git. Draft PRs, not merged without the owner.

## Steps

### 0. Offline: does a compressed index give the server's answer? (Mac, no phone)

On the stored Android uploads (201 with a known card) and the frozen 157-photo panel: embed with the server model on the whole-card crop, search the float32 index and compressed versions (int8 per-dimension scale; int8 with the top 50 re-scored at float32 if needed). Report top-1 agreement with float32, change in margin, the stage 1 rule result per scan, and the file size.

**Gate:** same stage 1 decision as float32 on at least 99% of scans and 0 scans where the compressed index lets a wrong card pass.

### 1. Phone search speed and size

Ship the compressed index as a test asset (Play asset pack on Android like the model; on-demand resource on iPhone). Measure load time, memory, and search time p50/p90 on the A55 and the iPhone 15. **Gate:** search p90 under 20 ms, memory under 40 MB.

### 2. Best frames, log only

Android and iPhone: ring buffer of about 1 s of preview frames, sharpness per frame (the camera already computes `sharpness(frame)`), pick the 3 sharpest with the card in the guide, fingerprint them while aiming. Log: frames considered, sharpness chosen vs shutter frame, single-frame vs averaged margin, time from card in view to fingerprint ready. Nothing shown. Can share the test round with the live text reader.

### 3. On-phone decision, log only

Run step 4 of the idea on the phone and log what it would have shown and when, next to the server's final answer for the same scan. **Gate on a live round (owner's cards, about 40 scans across both phones):** 0 provisional cards that the server overturns, provisional ready within 1.5 s of the card being in view on at least 50% of scans.

### 4. Provisional answer on screen

Behind a flag: show the provisional card, replace it with the server's answer when it arrives, and show a correction if they differ (should be 0 by step 3). Live test again.

### 5. Index updates

The index changes when the catalogue changes. Version it with the model ID (`2ddf6ec79e37`) and the catalogue checksum; the phone uses on-phone matching only when its index version matches the server's, otherwise it behaves as today.

## Depends on

- The live text reader results (PokeSingle #185, round of 16 scans).
- The Android whole-card crop (on main since PokeSingle #176 and #177; on manual photos the guide crop).

## Risks

- App size: about 17 MB more as a download pack, not in the base app.
- Phone and server rules drifting apart: thresholds come from the server.
- Same-artwork twins (Pikachu Evolutions vs Base Set, other-language prints): the phone stops exactly where the server stops, so no early card is shown for them.
- Processor load while aiming: fingerprints only on the 3 chosen frames, paused at the shutter.
