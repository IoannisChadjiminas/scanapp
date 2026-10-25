# ScanApp and PokeSingle: master plan after the October 2026 experiments

Date: 2026-10-25. Replaces the earlier per-topic plans where they conflict. Those still hold detail: `docs/instant-recognition-plan.md`, `docs/android-fast-path-plan.md`, `docs/stage1-build-plan.md`, `docs/android-number-recognizer-plan.md`, `docs/android-blur-fix-plan.md`, `docs/production-single-server.md`.

**Repos:** ScanApp (`~/WebstormProjects/scanapp`, FastAPI server) and PokeSingle (`~/StudioProjects/PokeSingle`, Flutter app).
**Rules that never change:** no wrong card is accepted automatically (0 wrong early answers, 0 background-check disagreements); every behavior change sits behind its own switch, default off until measured; open PRs, merge only after review; no store publishing; photos and OCR text never in git; secrets never printed or copied.

## 1. Goals

1. **Fast:** median time from card stopped to a correct card, today **4.1 s (p90 7.9 s)** measured on the phone, down to well under 1 s for most scans.
2. **Cheap:** server CPU per scan, today about 9 to 12 s on the full pipeline, down by 5 to 20 times on the fast path.
3. **Correct:** 0 wrong automatic confirmations. A phone-side "likely" card is a suggestion until the server or the user confirms it.

## 2. What we have (all merged unless noted)

**Server (ScanApp, PRs #52 to #70):**
- Production compose and runbook; scan lanes (`SCAN_LANES`, +57% throughput, default 1); grading only for slabs (**-24.5% CPU**, on by default).
- Cascade: the phone sends corners, text, slab label fields, quality and an embedding. **Stage 1** answers when the phone vector and the text name the same card (margin >= 0.02). **Stage 1b** answers when the text names one card and one artwork check passes. Otherwise the full pipeline (3 to 9 s) runs. Every early answer gets a background re-check. Production keeps stage 1 off.
- Slab fixes (label filter, number+name lookup, label language, label set+number, whole-image fallback), set totals, duplicate-id collapse, reprint groups, promo numbers, number repair, `number_candidates` (default on), stage 1b on the server's own frame.
- Suite: 969 API tests pass.

**App (PokeSingle, PRs #150 to #166):**
- Shared text pass (slab check, card text, label), photo quality, vintage and footer number reading, set-total table, iPhone Core ML embedding as a downloaded pack, startup-config race fix, manual-photo card detection, Android DINOv2 behind a flag, Android gallery quad improvements, raw number candidates, **#164** (release crash fix, blur diagnostics, fixes A to E off) and **#166** (PP-OCRv6 number reader, off).
- **Open:** **#165** (steady gate, burst, footer voting; off, unmeasured) and draft #162 (not to merge). ScanApp #65 (stage 0 simulation) and #44 (older) are open.

## 3. Key measurements

| Area | Result |
|---|---|
| iPhone, real scans (26) | Stage 1/1b answered **6**, all correct, all background checks agreed, 18 to 285 ms on the server. Embedding **27 ms** on iPhone 15 |
| A55, 157-photo panel, live run | **21** early answers (17 + 4), 0 wrong; full scanner top card **148/156**; embedding sent on 78%, none late |
| Mac replay, simulated phone | 53 to **58** early answers of 157, 0 wrong |
| A55 camera scans in the wild (193, build 153) | Text sent 53%; the phone's number matched the final card on 21%, disagreed on 4%; outline found **96%**; embedding 0% (not in that build); fast path 7%; 29% ended as retake or no match; server median 3.5 s |
| Number reading, A55 gallery path | ML Kit 46 of 102 correct, 3 wrong. **ML Kit + PP-OCR: 64 correct, same 3 wrong**, 18 gained, 0 lost; reader median **0.92 s**, p90 1.07 s, about 220 MB while loaded |
| Offline Mac, number reading | PP-OCR whole photo **89 of 102**, ML Kit 47; PP-OCR on footer crops from the app's quad only 31 (the quad is the problem) |
| A55 replay, what the phone sends | PP-OCR number + ML Kit name only: **21** early answers, 0 wrong, 0.32 s server CPU each. Same text **plus outlines and embeddings: 45**, 0 wrong, 18 ms each |
| Android embedding | LiteRT GPU fp16: cosine **0.998**, **132 ms** median on the A55. ONNX fp16 XNNPACK: wrong output. NNAPI: hangs. The trained MobileNet student reached only 35 of 157 |
| Blur (A55 manual shots) | The shutter click plays **330 to 750 ms before** the exposure; fix B adds about 350 ms; fix C (quality mode) is too slow (about 1.9 s) |
| Android outline | Gallery imports: 43 of 157 get none, 28 of 114 match the server's outline. Live camera: **96% found** |
| Index for a phone-side search | 44,021 cards x 384: fp32 67.6 MB, fp16 33.8 MB, int8 16.9 MB |
| Infra | Production target: Hetzner **CPX32** (4 vCPU / 8 GB, about EUR 42/mo). Arm (CAX) rejected: 2.2x the CPU per scan |

## 4. What the data says

1. **The server is cheap when the phone does its half.** A fast answer costs 18 ms with the phone's embedding, 0.32 s without it, 3 to 9 s on the full pipeline.
2. **Android needs the embedding** (45 vs 21 early answers). The text-only shortcut helps, but gets less than half.
3. **ML Kit is the Android number-reading limit,** not just the photos. PP-OCR fixes most of it, at a cost of about 1 s and a downloaded model.
4. **Footer crops, burst and voting tricks are second-order** now. The weak Android gallery outline made crops fail, and PP-OCR on the whole photo avoids it.
5. **Blur has a clear cause:** the click is early. Cheap fixes A (click at the exposure) and D ("hold still") need no extra time.
6. **Every figure above is from a small, tuned panel.** Release decisions need a fresh holdout.

## 5. Workstreams

### A. Android fast-path coverage (biggest gain)

1. **A1. Android embedding on, behind a speed guard.** LiteRT GPU fp16 (already in #159), own model ID `2ddf6ec79e37/litert-fp16`. On first use run 5 warm-up and 20 to 30 timed inferences; enable only if p90 <= 200 ms and the GPU path is healthy (re-check after OS or app updates). Run it **in parallel** with the text pass as soon as corners exist; budgets: live 300 ms, gallery/manual 600 ms end to end. Check cosine against the golden fixtures on 2 to 3 phones including an older one. **Gate:** replay the 157 panel through staging with the real validation runner: **>= 45 early answers**, 0 wrong, 0 background disagreements, embedding delivered on >= 70%.
2. **A2. Validate PP-OCR (#166) before enabling.** The staging validation replay, the 10-card live test (below), one older phone, memory and battery, the Play asset pack delivered through Play (not only a local file), ONNX Runtime kept under R8 in a **real release build**. **Gate:** a fresh holdout shows 0 wrong numbers and a gain over ML Kit alone. Keep `ANDROID_NUMBER_RECOGNIZER` off until then. Decide the live-camera policy: it runs only on gallery and manual photos today.
3. **A3. Cheap blur fixes.** Turn on fix A and D after a short in-hand A55 check (30 shots before, 30 after, same cards). Keep B and E only if they raise sharpness without adding more than about 300 ms. Drop C. Decide what to do with #165: park it (keep unmerged) unless the measurements show a gain over PP-OCR.
4. **A4. Outline for gallery imports (lower priority).** Only if gallery coverage matters after A1. Prototype first: a tiny corner model trained on synthetic composites of the catalogue's card images plus the real panels, scored by "outline found and overlaps the reference outline >= 0.9"; fallback is porting the server's detector with a trimmed OpenCV.
5. **A5. The 10-card live-camera test,** with the owner's list: 4 to 5 scans per card (auto close and far, manual, tilt, sleeve). The agent `android-live-camera-numb` already holds the plan; with `STORE_CAPTURES=true` on staging it also measures the number's pixel height. Turn `STORE_CAPTURES` off afterwards and delete the saved test photos.

### B. iPhone

1. **B1. Vintage and slab coverage.** Rescan the owner's cards on the current build and read `stage0` / `stage1_check` lines: answer rate by era, disagreements (must be 0), anything the phone misreads. Fix the app's dropped-leading-digit class (a number whose numerator looks cut off goes only into `number_candidates`).
2. **B2. Fresh holdout** (below) before turning stage 1 on in production.

### C. Near-instant recognition (iPhone first, then Android)

Follow `docs/instant-recognition-plan.md`: **Phase 0** offline feasibility on the Mac (index formats, top-1/top-5 accuracy, the margin and stability rule for showing a "likely" card, target: top-5 contains the label on >= 97% and wrong-likely < 1%); **Phase 1** ScanApp index-pack builder and log fields; **Phase 2** iPhone local search, live loop and "Likely" chip, with the upload running in parallel (gate: <= 300 ms median from card stable to likely, 0 wrong automatic confirmations); **Phase 3** Android after A1 (embedding 132 ms means about 2 to 3 live frames per second, aiming-box crop); **Phase 4** optional local confirmation and offline mode. PP-OCR is the Android confirmation step, not the live step.

### D. Server (ScanApp)

1. **D1. Catalogue cleanup:** merge the 561 duplicate id pairs (`docs/experiments/stage0-duplicate-pairs-20261021.csv`) after checking prices, Cardmarket links and index entries that point to either id; add reprint-group and twin metadata to the index build.
2. **D2. Production rollout path for stage 1:** turn it on with the background check at a 10% sample and "needs confirmation" first; watch `/api/v1/health` counters and the `stage1_check` lines; switch off confirmation only after a few hundred real scans with 0 disagreements.
3. **D3. Keep the safety nets:** the full pipeline for everything that doesn't agree, scan lanes at 2 on the CPX32 once measured (it adds about 0.9 GiB per extra lane), the always-on SQLite lock.
4. **D4. The ScanApp backlog:** review or close #65 and #44; the load-test card (1, 2, 4 concurrent users, lanes 1 and 2, with a realistic mix of fast and full-pipeline scans).

### E. Release and infrastructure

1. **Server:** resize or create the CPX32 (x86), 4 GB swap, firewall (22, 80, 443), snapshot first; follow `docs/production-single-server.md` (dedicated database roles, private env files, models and reference features seeded, health checks, a test owner for `/internal/portfolio/products`, then the PokeSingle API's `SCAN_API_BASE_URL`).
2. **Deploy tooling:** decide Dokploy or plain Docker with GitHub Actions (the automation plan exists as a task card). Images built in CI, not on the server.
3. **Secrets housekeeping (now):** rotate the PlanetScale passwords exposed earlier (catalogue read-only and portfolio) and update the staging env files; keep the eBay keyset private; switch `STORE_CAPTURES` back to false on staging; delete `/root/bench` (about 226 MB, public card data) and the test captures; confirm the Arm test server (CAX31) is deleted in Hetzner.
4. **Android release:** the crash fix is merged; verify a **real release build** launches on the A55 before any Android build goes out; fix or quarantine the two flaky Flutter tests (`inapp_cardmarket_reader_test`, `match_sheet_test`).

### F. Measurement that every decision needs

1. **A fresh labeled holdout** of about 150 full-size photos (internet corpus rules and the review sheet), plus the owner's 10 physical cards, never used for tuning. Every "ready" claim for A1, A2, B2, C and D2 is judged on it.
2. **One staging log joiner:** a script that joins `scan_summary`, `stage0`, `stage1_check` and phone events by scan id and reports by platform, capture type and era. It replaces ad-hoc log reading.
3. **A weekly report** of: early-answer share, wrong answers, background disagreements, median and p90 time (phone-measured), server CPU per scan, and the share of retakes.

## 6. Order, dependencies and rough effort (all estimates are guesses)

| # | Work | Depends on | Effort |
|---|---|---|---|
| 1 | E3 housekeeping (rotate, STORE_CAPTURES off, cleanup) | none | an hour |
| 2 | A1 Android embedding + speed guard + replay | #159 merged | 3 to 5 days |
| 3 | A5 10-card live test, then A3 cheap blur fixes | owner's cards | 1 to 2 days |
| 4 | F1 fresh holdout + F2 log joiner | none | 2 to 3 days |
| 5 | A2 validate PP-OCR (staging run, holdout, Play pack, R8) | #2, #4 | 3 to 5 days |
| 6 | C Phase 0 (offline index feasibility) then Phase 1 and 2 (iPhone) | none for Phase 0 | 1 day, then 1.5 to 2 weeks |
| 7 | D1 duplicate cleanup, D2 rollout, D4 load test | #4 | 1 to 2 weeks, in parallel |
| 8 | E1/E2 production server and deploy tooling | D4 | 2 to 4 days |
| 9 | C Phase 3 (Android likely), A4 outline | #2, #6 | 1 to 2 weeks each |

Items 1 to 4 can start now. Item 6's Phase 0 does not depend on the Android work.

## 7. Global gates

- **Correctness:** 0 wrong early answers and 0 background disagreements on the panel, the holdout and real scans; a phone "likely" never saves anything unconfirmed.
- **Time:** embedding p90 <= 200 ms on devices that enable it; live <= 300 ms, gallery/manual <= 600 ms for the hint pass; PP-OCR within its 1.2 s cap.
- **Coverage targets** (to track, not blockers): A55 >= 45 of 157 early answers; iPhone at least as good on the same photos.
- **Quality:** `flutter analyze` clean, tests passing except the two known flaky ones, release builds launch on the device, diagnostics compiled out of release.

## 8. Risks and open questions

- **Small tuned panels.** Mitigation: the fresh holdout (F1) before anything goes to production.
- **Android speed and memory:** the embedding at 132 ms and PP-OCR at about 1 s with 220 MB; older phones may fail the guards, so every Android piece must degrade to today's behavior.
- **Same-artwork twins and reprints** (English/Japanese, Prize Pack): shown as a group, decided by text language or the user.
- **Index and catalogue drift:** each release needs a matching phone index pack and version check.
- **Slabs and sleeves:** out of scope for the phone-side likely card in version 1.
- **Server frame cost:** the text-only fallback costs about 0.3 s of CPU per answer, about 10 to 30 times cheaper than the full pipeline but not free.
- **Open decision:** whether PP-OCR may also run in live auto capture, or only on gallery/manual photos as built.
