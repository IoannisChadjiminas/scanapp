# Android embedding with speed guard, live-camera test and blur fixes

Date: 2026-10-25. Covers master plan steps 2 and 3 (workstreams A1, A5, A3). Repos: PokeSingle (Flutter app, `~/StudioProjects/PokeSingle`) and ScanApp (server, `~/WebstormProjects/scanapp`).

**Rules:** no wrong card accepted automatically (0 wrong early answers, 0 background-check disagreements). Every behavior change sits behind its own switch, default off until measured. Open PRs, do not merge. No store publishing. Photos and OCR text never in git. Never print or copy secrets. Start work from latest `main` in a worktree.

## Track 1: Android embedding with speed guard (A1)

Goal: Android sends the embedding so the server can answer early. Measured: text alone gives 21 early answers of 157, text plus outlines and embeddings gives 45, 0 wrong. The LiteRT GPU fp16 path exists in PokeSingle #159 (cosine 0.998, 132 ms median on the A55). ONNX fp16 XNNPACK gives wrong output and NNAPI hangs: do not use them.

**Phase 1: Speed guard and model ID (1 day)**
- Model ID `2ddf6ec79e37/litert-fp16`, separate from the iPhone `coreml-pal8` ID.
- On first use run 5 warm-up and 20 to 30 timed inferences. Enable only if p90 <= 200 ms and the GPU path is healthy. Store the result; re-check after an OS or app update.
- If the guard fails, behave exactly as today (no embedding sent).
- Run the embedding in parallel with the text pass as soon as corners exist. Budgets: live 300 ms, gallery/manual 600 ms end to end.
- Unit tests for guard pass/fail/re-check. `flutter analyze` clean.

**Phase 2: Correctness on devices (1 day)**
- Check output against the golden fixtures (cosine >= 0.995) on the A55 and 1 to 2 other phones, including an older one.
- Record median and p90 inference time per phone, and memory.

**Phase 3: Staging replay (1 to 2 days)**
- Replay the frozen 157-photo panel through staging with the real validation runner (`api/scripts/android_fastpath_replay.py`, run `a55_fastpath_ocr_20261024` as the baseline).
- **Gate:** >= 45 early answers, 0 wrong, 0 background disagreements, embedding delivered on >= 70%.
- If below 45, report why before tuning (late embeddings, missing quads, gate rejections).

**Phase 4: PR (half a day)**
- Open the PR with results; flag default off. Report the release-build launch check on the A55.

## Track 2: Live-camera test and cheap blur fixes (A5, A3)

Runs in parallel with Track 1. Needs the owner's list of 10 physical cards and the phone in hand.

**Phase 5: 10-card live test (half a day)**
- 4 to 5 scans per card: auto close, auto far, manual, tilted, in a sleeve.
- Turn `STORE_CAPTURES` on for staging for the test only (the owner switches it in Dokploy). Measure the number's pixel height from the stored captures.
- Report per card: number read by the phone, final card, time, and failures.
- Afterwards: `STORE_CAPTURES` back to false and delete the saved test photos.

**Phase 6: Blur fixes A and D (half a day)**
- A: fire the shutter click at the exposure instead of 330 to 750 ms before it. D: a "hold still" prompt. Both add no time.
- Before/after on the A55: 30 shots each, same cards, same lighting. Compare sharpness.
- Keep B (adds about 350 ms) and E only if they raise sharpness without adding more than about 300 ms. Drop C (about 1.9 s).
- Behind flags, default off until the numbers are in.

## Order and exit
Phases 1 to 4 in order; Phases 5 and 6 any time after the owner provides the cards. Exit: both PRs open with measured results, and a short report of what moved.
