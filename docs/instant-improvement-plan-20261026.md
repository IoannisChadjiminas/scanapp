# More instant answers without losing accuracy (plan, 2026-10-26)

Goal: as many scans as possible answered early (stage 1 / 1b, about 20 to 350 ms of server time) instead of by the full pipeline (about 7 s), with **0 wrong early answers and 0 background-check disagreements**. The phone is not available, so every step is measured offline on stored real scans.

## Where we are

- Android (A55, manual): about 2 early answers of 11 per live run. The outline fix, full-resolution still, 900 ms text budget and the embedding are now on by default (PokeSingle #169, #172, #176 to #178).
- Offline, with a correct whole-card outline, the vector agrees with the right card on 90 of 201 stored Android uploads; 61 more have no contradiction; **50 still contradict and 33 agree with too small a margin**, mostly because a reprint or another-language print of the same card leads (Pikachu Evolutions vs Base Set, Comfey vs its Japanese print). Source: `docs/experiments/android-abstain-reasons-20261026.md`.
- Abstain reasons seen live: `visual_contradiction`, `no_unique_text`, `no_server_frame`, `printing_twins` (correct), `artwork_miss`.

## Data for testing

- Staging `/data/review` (read-only): 463 stored scans from 25–26 Oct; 226 Android manual uploads (142 at 1363 x 1904 or 1432 x 2000, 80 at 641 x 896), about 200 with the card known from the owner's list (Comfey 30th-077, Zorua 30th-095, Toxel mep-078, Capsule sv04-159 / PPS5 twin, Brute Bonnet sv04-123 / PPS5 twin, Charmander xy12-9, Charmeleon base1-24, Pikachu xy12-35), plus the iPhone scans.
- The frozen 157-photo A55 panel with its ML Kit capture (`/tmp/a55-fastpath-ocr-157.json`) and `api/scripts/android_fastpath_replay.py`.
- Server index and model on the Mac: `data/android-embedding-research-20261023` (`catalogue/vectors/pad`, `catalogue/catalog.sqlite`, `teacher/dinov2_small.onnx`); helpers in `api/scripts/instant/`.
- Photos and OCR text never go into git. Labels and per-scan results go only into scratch folders; committed reports use scan ids.

## Steps

### 1. Offline stage 1 benchmark (needed by everything else)

A script under `api/scripts/stage1_bench/` that, for each stored upload with a known card:

- builds the phone's inputs: the vector from a whole-card crop (server DINOv2 ONNX, the phone's model matches it at cosine 0.998), and the text from the server's own OCR of that upload as a stand-in for the phone's text (name, number, set total);
- runs the **real** stage 1 / 1b decision code (`api/app/recognition/stage1_gate.py`, `stage1_answer.py`) with the staging flag set from `compose.dokploy.yaml`;
- compares the early answer, if any, with the known card and with the stored full-pipeline result.

Output per run: early answers by path, wrong early answers (must be 0), would-be disagreements with the full pipeline, abstain reasons. Also run it on the 157 panel. This is the baseline every change below must beat.

### 2. Family-aware vector rules (largest gain)

Behind a new default-off flag (for example `STAGE1_FAMILY_VECTOR`): when the vector's leader is in the same family as the card the text names (same name and collector number, or a same-artwork other-language twin with cosine at or above the existing twin threshold), it does not count as a contradiction, and the stage 1 margin is measured against the best card **outside** that family. The text's number and set total still choose the printing; twins and reprints still go to `printing_ambiguous` and the twin guard stays.

Gate: on the benchmark, 0 wrong early answers, 0 new disagreements, and a clear gain in early answers (target: most of the 50 contradictions and 33 low-margin cases that belong to the right card's family).

### 3. Stage 1b frame fallback

Behind a default-off flag: when the server's frame finder fails (`no_server_frame`) on a manual guide crop, use the phone's outline if it passes the server's card-shape check, else the whole upload. Gate: same as step 2.

### 4. Faster full pipeline when the text already names one card

For scans that still go to the full pipeline but whose text names exactly one card: skip or shorten the passes that only help when the card is unknown (extra OCR passes, grading on raw cards, wide visual search). Behind a default-off flag. Gate: no status changes towards a wrong card on the benchmark and the 157 panel; server time per scan reported.

### 5. Later, needs the owner's phones

iPhone live text (TestFlight build 154, `IOS_LIVE_TEXT`), the iPhone embedding on TestFlight, Android embedding through Play and on an older phone, and a live rescan of the same cards to confirm the offline numbers.

## Rules for every step

One flag per change, default off until measured; staging may turn it on after the gate passes. Open draft PRs, do not merge without the owner. Full API suite green. Read-only on staging.
