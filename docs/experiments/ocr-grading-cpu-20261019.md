# Server CPU per scan: grading hint, OCR pass budget, detector size, INT8, trusted warp

Date: 2026-10-19. Branch `claude/recursing-sanderson-6cd97d`. Nothing was deployed, pushed, or changed in any production compose file or default.

## Result in one table

Ranked by CPU saved among options that keep final answers. "Verified" means measured against staging's own catalogue on the staging host (x86, 2 vCPU).

| Rank | Change | CPU saved per scan | p50 / p90 latency | Final-answer changes (card_id, status) | Status |
|---|---|---|---|---|---|
| 1 | Grading only when the phone says slab (`graded=false` skips grading; needs `APP_SLAB_DETECTION=true` on the phone side) | **24.5%** mean (12.2 s to 9.2 s CPU; p50 -40%) | p50 5.2 s to 3.3 s; p90 9.7 s to 7.8 s | **0 of 149** | **Verified on staging** (149/155 photos; with an oracle hint, see caveats) |
| 2 | `OCR_DET_LIMIT_SIDE_LEN=640` (new flag, default 0 = off) | 9.3% | p50 -1.5%; p90 -5.5% | 6 changed, 2 regress against expected card | CPU-only. Answer safety NOT verified; do not enable |
| 3 | `OCR_SKIP_RETRY_PASSES=true` (new flag, default off) | 8.4% | p50 0%; p90 -20% | 3 changed, all 3 regress | CPU-only. Answer safety NOT verified; do not enable |
| 4 | Trusted warp (`TRUST_CLIENT_WARP=true`, photo pre-warped, `skip_detect`) | 8.2% mean, p90 CPU -24% | p50 -1.6%; p90 -28% | 21 changed, 11 regress | CPU-only. Answer safety NOT verified; do not enable |
| - | INT8 dynamic quantization of PP-OCRv6 det/rec | 3% to 15% | n/a | OCR text changes on 20 to 31 of 100 photos | Reject |
| - | `USE_CLIENT_QUAD` | 0 by construction | n/a | n/a | No effect on work done; skipped |
| - | Detector-skipping recognition on known regions (experiment 3) | not measured | n/a | n/a | Not run; see below |

Combinations were not measured; savings do not simply add up.

**Safe to enable now: only the grading hint**, and only as far as the phone's `graded` flag is reliable (see caveats). Everything else needs a full-catalogue, x86 replay before it is considered; on the replay here, every one of them lost correct answers.

## How this was measured

**Staging runs (rows verified).** A throwaway container (`bench-api`) built from a `docker commit` of the live staging API container, so it carries the same image and environment without reading them. It had its own fresh results database, the staging catalogue loaded the same way as the API (cloud backend), scrapers and price jobs off, `--cpus 2`. CPU per scan is the container cgroup's CPU time from just before the upload until it has been idle for 1.2 s, so background grading and OCR after the response are included. The 155-photo panel (`staging-reference027-20261003/regression-cached.jsonl` cases, 100 raw, 50 slab, 5 phone) went through one scan at a time. The live staging API was stopped during the runs and restarted unchanged afterwards (health ok, ready, 50,270 cards, same container and import ID `PS-CATALOGUE-EN-JA-ENID2-20261019`).

- Baseline: current staging flags, no `graded` hint sent.
- Grading hint: `graded=true` for the 50 slab photos, `graded=false` for all others (a perfect phone classifier). The run was stopped at 149 of 155; both runs are compared on those 149.

**Local runs (rows labelled CPU-only).** A native run on an M4 Pro Mac, four configurations in parallel with identical thread settings (`ORT_INTRA_THREADS=2`, `DINO_INTRA_THREADS=2`). It used staging's exact catalogue release, exported once with the API's own loader (50,270 cards, 44,021 indexed, embeddings checksum identical to the cloud's; public card data only) and staging's artwork bundle `PS-CATALOGUE-EN-JA-SETH3-20261017`. The reference-features bundle could not be used: its processing contract pins `architecture=x86_64` and an OpenCV build hash, so the runtime correctly rejects it on ARM. All local configurations therefore ran without reference features, and in a different numerical environment (ARM, different OpenCV/Pillow/NumPy builds). CPU here is the server process tree's CPU time.

Absolute local CPU-seconds are from an M4 Pro and mean nothing for the server; only ratios carry over. Even the ratios are indicative, because the local OCR/grading split differs from x86 (local grading is far cheaper).

**ARM versus x86 answer drift (important for reading the local rows).** The local baseline gives different final answers from the staging baseline on 27 of 155 photos (card_id or status), 7 of which are regressions against the expected card (143/154 correct locally versus 150/154 on staging). The cause is the missing reference features plus ARM numerics. So the local variant-vs-local-baseline counts below show direction and rough size of harm; they are not a prediction of staging answer changes. The IDs are in `data/latency/ocr-grading-cpu-20261019.json`.

## Per experiment

### 1. Grading only for slabs: verified on staging

- Recorded 155-photo panel (staging data, `staging-reference027`): over the 105 non-slab photos grading found a label on none (0 false positives). It cost a median of 2.9 s (p90 6.1 s) per raw photo and about a third of all scan time. It also missed 17 of the 50 slabs (mostly ACE; some PSA, Beckett, CGC, TAG), so grading recall is not complete today whatever the hint does.
- Replay with an oracle hint, 149 photos: CPU mean 12.2 s to 9.2 s (-24.5%), p50 10.4 s to 6.2 s (-40%), p90 20.0 s to 16.8 s (-16%). `grading_ms` mean 3.9 s to 1.3 s. No card_id or status change on any of the 149 photos.
- 18 photos differ in the grading block only: 16 raw photos report `is_graded=false` instead of unset, one slab (`freshextra_1_1957211138`) got an AGS 8.5 grade the baseline missed at the card deadline, and one raw photo (`holdout4_009`) went the other way. These are grading-deadline effects, not recognition changes.
- Caveats: the oracle hint is the best case. A real phone classifier that wrongly says `graded=false` on a slab would skip grading for that slab (the flag skips on false only; `true` or no hint still grades). The phone's false-negative rate on slabs is not measured here. Staging already runs `GRADING_REQUIRES_CLIENT_HINT=true` and `APP_SLAB_DETECTION=true`; the saving only appears for clients that send `graded`.

### 2. OCR pass budget

- Recorded panel: 113 of 155 scans use exactly 2 passes (title strip and footer strip). The 42 with more passes are mostly collector `footer_half` retries (about 1.3 s each) and `original`/`complete_frame` re-reads.
- OCR-only local replay, 100 raw photos: 17 photos use extra passes and account for 23% of OCR CPU. Capping at the first two reads changes the name or collector text on only 2 of them (`freshraw_0_1807925107` loses its collector number; `holdout4_105` changes one glyph). That suggests a targeted early exit could be nearly free, but the blunt "skip every retry" flag tested here (`OCR_SKIP_RETRY_PASSES`) did cost answers in the full replay: 3 card/status changes, all regressions (`freshextra_1_1957211138`, `fresh100_146365926690`, `fresh100_196323744191`). A selective rule (stop only when title and collector number agree with the visual top-1 by a clear margin) was not built or measured.

### 3. Recognition-only on known card regions

Not run. The pipeline already crops fixed title (top 22%) and footer (bottom 18%) strips from the warped card, so the remaining detector cost is the text detector on those strips. Skipping it means feeding line crops straight to the recognizer, which needs new layout code and its own accuracy replay. No measurement of the detector/recognizer split was made, so there is no CPU estimate here.

### 4. Detector input size and INT8

Local OCR-only replay on 100 raw photos, one thread, text compared with baseline (name same / collector same):

| Variant | CPU saved | Name same | Collector same |
|---|---|---|---|
| Det side 640 | 14.6% | 94 | 84 |
| Det side 512 | 32.3% | 93 | 86 |
| Det side 384 | 46.6% | 90 | 83 |
| INT8 det | 3.3% | 91 | 88 |
| INT8 rec | 10.2% | 78 | 75 |
| INT8 det+rec | 15.5% | 80 | 69 |
| Cap at 2 passes | 7.0% | 99 | 99 |

RapidOCR's default is `limit_type=min`, `limit_side_len=736`, which scales the strips up to a short side of at least 736 px; lowering the target is a real CPU lever but changes OCR text. INT8 dynamic quantization saves little and corrupts a fifth to a third of reads; reject it. DINOv2 was not quantized (the indexes are bound to its checksum).

Full replay, side 640: 9.3% less CPU, 62 photos with any change in OCR text or printing evidence, 6 with a card/status change, 2 of them regressions against the expected card (`fresh100_135586143350`, `holdout4_004`).

### 5. USE_CLIENT_QUAD / TRUST_CLIENT_WARP

- `USE_CLIENT_QUAD` does not reduce work. In `api/app/recognition/pipeline.py` the server still runs its own detection and builds the alternative frames; the phone's quad only supplies a fallback. It was not benchmarked.
- `TRUST_CLIENT_WARP` with `skip_detect` skips the alternative frames: mean `frame_hypotheses` 3.0 to 1.2, `embed_ms` 114 to 72 ms, detect 13.6 to 4.4 ms. Total CPU saving is only 8.2% on average (p90 -24%), because OCR dominates. Simulated here by warping the photo with the server's own detector and uploading a re-encoded JPEG, which is not what a real phone sends. With that input the answers got worse: 21 card/status changes, 11 regressions. Whether a phone-warped image behaves differently is untested.

## Recommendations

1. **Enable the grading hint path** (app `app_slab_detection` plus `GRADING_REQUIRES_CLIENT_HINT=true`, both already on in staging env) once the phone's slab classifier has a measured false-negative rate. It is the only change that saved real CPU with zero answer changes on the staging replay.
2. Do not enable `OCR_DET_LIMIT_SIDE_LEN`, `OCR_SKIP_RETRY_PASSES`, or trusted warp. If a lower OCR cost is wanted, try a selective early exit and a side length of 640 only after a replay on x86 against the full catalogue and reference features shows no lost answers.
3. Do not use INT8 quantization of the OCR models.
4. Next measurements worth doing: the phone's actual `graded` accuracy; an x86 replay of the two OCR flags with reference features; the detector/recognizer CPU split to size experiment 3.

## What was changed in the repo

- `OCR_DET_LIMIT_SIDE_LEN` (default 0, off) and `OCR_SKIP_RETRY_PASSES` (default false, off) in `api/app/config.py`, wired through `api/app/recognition/ocr.py` and `runtime.py`. Both change nothing unless set.
- Scripts in `api/scripts/`: `ocr_cpu_bench.py` (OCR-only CPU and text comparison), `cpu_replay.py` (panel replay with CPU from cgroup or process tree), `compare_replay.py` (CPU, latency, answer changes), `export_cloud_snapshot.py` (exports the API's loaded cloud catalogue to a local-backend data directory).

## Housekeeping and risks

- The live staging API is running again, unchanged. `/root/bench` on the staging host still holds the bench data and an export of public card data (about 135 MB) and can be removed.
- No credentials were read, written to files or printed in this work. One earlier command printed the staging API container's environment to the terminal, including database passwords; those should be rotated.
- Limits: one pass over a 155-photo frozen panel (not unseen photos); single runs, no repeat to measure run-to-run noise; staging is 2 vCPU, production target 4 vCPU.
