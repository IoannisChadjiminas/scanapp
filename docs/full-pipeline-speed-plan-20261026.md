# Faster full pipeline when the phone's text already names the card (plan, 2026-10-26)

Step 4 of `docs/instant-improvement-plan-20261026.md`. Steps 1 to 3 (printing reorder, narrow footer rule, frame fallback) are on in staging. They answer more scans early, but most scans still go to the full pipeline. This plan makes that path faster without changing what it answers.

## Where the time goes

Full-pipeline scans in the staging log since the last container restart (61 scans, so a small sample):

| Stage | Median | p90 |
|---|---:|---:|
| **total** | **5.5 s** | **9.8 s** |
| OCR (`ocr_ms`) | 3.1 s | 5.7 s |
| embeddings (`embed_ms`) | 0.70 s | 1.47 s |
| frame proposals | 0.25 s | 0.52 s |
| artwork embedding | 0.19 s | 0.40 s |
| local artwork match | 0.17 s | 1.21 s |
| text identity | 0.02 s | 1.32 s |
| detect, retrieve, decode, prices | under 0.05 s each | |

OCR is more than half the time. It runs 2 passes on most scans and up to 9.

The pipeline already has ways to use the phone's text instead of its own OCR (`CLIENT_TEXT_OCR=footer` is on in staging and production; `CLIENT_TEXT_FAST_PATH` is off). In the logged scans the `client_text_ocr` and `client_text_fast_path` timing markers are 0, so the phone's text did not replace any OCR pass, even though the phone sent a name on most scans and the number on many. Why is not known yet; finding out is the first step.

Related earlier work: the idle session [Cut OCR and grading CPU per scan](#local_6a1c5156-8bc7-4514-a933-321342517a8d). Check its findings before step 2 so nothing is redone.

## Rules

Every change behind its own flag, default off; staging only after its gate passes; production off. No change may move a scan to a wrong card or turn an `uncertain` or `printing_ambiguous` result into `matched`. Read-only on staging. Photos and OCR text never in git. Draft PRs, not merged without the owner.

## Steps

### 0. Offline full-pipeline runner

A script under `api/scripts/full_bench/` that runs the real full recognition path on the stored Android manual uploads (226, about 174 with a known card) with the local catalogue, reference images and features, and the server's OCR models, and records per-stage timings, status and the shown card.

Before it is used for anything: check that it reproduces the stored results (same status and same first card on at least 95% of uploads). If it does not, list why and fix the runner, not the pipeline.

The phone's text for each upload: the server's own read as a lower bound and the owner's card as an upper bound, as in the stage 1 benchmark.

### 1. Why the phone's text does not skip OCR today

Log and count the reasons from `ocr_skip_decision` and `fast_path_decision` (`frame_selection['client_text_ocr']`, `frame_selection['client_text_fast_path']`) on the runner and on live staging scans. Expected outcomes: the text never qualifies (confidence, missing total, name mismatch), or it qualifies but OCR runs anyway, or the hint arrives too late. The fix in step 2 depends on which.

### 2. Candidate changes (each its own flag)

| # | Change | Expected saving | Main risk |
|---|---|---|---|
| a | Let the phone's name and number stand in for the server's footer OCR when they name exactly one card (set totals applied) and that card is in the visual top 20. Keep the title read. Extends `ocr_skip_decision`. | most of one OCR pass (about 1 to 1.5 s) | a misread phone number; the result stays reviewable, never `matched` from phone text alone |
| b | Stop OCR passes early once one pass agrees with a text that names one card | the 3rd to 9th passes on hard scans (p90) | losing a later pass that would have found a stamp or a damaged footer |
| c | Skip extra frame proposals and embeddings when the first frame's top 20 already contains the text card | part of the 0.7 s embedding and 0.25 s proposal time | a wrong first frame that still contains the card by chance |

Out of scope: slabs and grading (their label reading is a separate path), Prize Pack stamp checks (keep them on), iPhone-only paths.

### 3. Measure each change

On the runner, each flag off and on: median and p90 total time, time per stage, status changes, first-card changes, wrong first cards against the owner's card, agreement with the stored full-pipeline result. Also run the frozen 157-photo panel.

**Gate:** 0 first cards moved to a wrong card, 0 results moved to `matched` that were not, and a median total time cut of at least 30% on scans where the phone's text names one card. Report the time saved on all scans too.

### 4. Staging, then a live check

Turn on in staging only the changes that pass. Then a live rescan on the phones (Android and iPhone) and a read of the staging log: time to result, status mix, background-check disagreements (must stay 0).

## Not covered

The runner needs the server's OCR models and reference data on the Mac; if any are missing, step 0 says so and stops there. Live timings differ from the Mac (the server is a 4-vCPU Hetzner box); the runner gives relative savings, not absolute times.
