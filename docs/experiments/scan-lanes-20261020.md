# Scan lanes: several scans at once in one API process

Date: 2026-10-20. Branch `claude/keen-bohr-f210b8`. Nothing was deployed. `SCAN_LANES` defaults to 1, which keeps today's behaviour; the production compose file only passes the variable through, with default 1.

## Result

| 4 CPUs, production flags, phone grading hint | 1 lane (today) | 2 lanes |
|---|---|---|
| One user, scans back to back: p50 / p90 | 3.50 s / 7.32 s | 3.16 s / 7.05 s (second lane idle) |
| Two users at once: p50 / p90 | 6.84 s / 12.69 s (queued) | 4.22 s / 9.56 s (second lane busy) |
| Throughput, 2 or 3 scans in flight | 15.2 scans/min | 23.8 to 24.3 scans/min (+57%) |
| Resident memory after start | 607 MiB | 589 MiB |
| Peak resident memory (VmHWM), one at a time | 2,089 MiB | 2,562 MiB |
| Peak resident memory (VmHWM), two in flight | 2,091 MiB | 3,027 MiB (+936 MiB) |
| Container memory peak (cgroup), two in flight | 2,236 MiB | 3,165 MiB |
| Errors / server tracebacks over 150 scans | 0 / 0 | 0 / 0 |

- **Answers do not change.** With label reads drained (not cut off at the card deadline), every recognition response was byte-identical between 1 lane and 2 lanes, including when two scans ran at the same time. The comparison drops only the scan id and the `*_ms` timing values.
- **One user is not slowed down.** With the second lane idle, single-scan latency equals today's (the small difference is run-to-run noise).
- **A second lane costs about 0.9 GiB at peak, not ~2 GiB like a second uvicorn worker.** That is more than the "few hundred MB" estimate. The extra memory is the second scan's own working buffers: its decoded photo and frames, its ONNX Runtime activations, and its OCR and label reads running alongside the first scan. Models and indexes are loaded once.
- **With production deadline grading, only `grading` can differ, and it already differs today.** All card, status, OCR and printing fields were identical in every run. When a slab scan arrives while the lane's label worker is still finishing the previous scan's label, that scan reports `grading_worker_busy`. Back to back on 1 lane this already happened to 10 of 20 slab scans. On 2 lanes it happened to 3 of 20 one at a time, and to 9 or 10 of 20 with two in flight.

## What changed

- `SCAN_LANES` (1 to 8, default 1). The scan admission limiter admits that many scans and the scan executor gets that many threads. `SCAN_WAIT_LIMIT` still counts waiting scans.
- Lane 0 is the existing `Runtime`. Each extra lane (`LaneRuntime`) gets its own card OCR reader, footer-region reader, label reader, region and label worker threads, auxiliary work gate and label slot. All readers share lane 0's det/rec/cls ONNX sessions. The DINO session, snapshot, artwork index, verifiers, printing index and catalogue groups are shared. Each admitted scan takes a free lane for its whole recognition and returns it afterwards.
- Shared state audit:
  - `LocalArtworkVerifier` and `CardLayoutVerifier` held one lock around all SIFT matching. That was safe, but it would have serialized artwork verification across lanes. Now only their LRU caches are locked; the matching uses per-call OpenCV objects.
  - `ReferencePrintingIndex` already locks its cache (unchanged).
  - The two `lru_cache` template loaders, `card_positions`, `metadata_index`, `_sku_groups` and the artwork index are built once and only read during scans.
  - `DinoEmbedder.batchable` can only flip to False, the same way for every caller.
  - Per-request OCR caches and grading cancellation scopes (a context variable) are already per scan.
- **SQLite: the one real bug.** Python's `sqlite3` connections are not safe for simultaneous use from several threads, even with `check_same_thread=False`. In the 4-CPU run, two lanes reading the local catalogue at once failed with `sqlite3.InterfaceError: bad parameter or other API misuse` (2 HTTP 500s in 50 scans). A plain-connection hammer reproduces it on macOS and in the Linux image: hundreds of errors per 12,000 queries. The cloud catalogue (`CloudCatalogConnection`) already serialized every call. That serialization now lives in `app.db.SerializedConnection` and the cloud connection subclasses it unchanged. With `SCAN_LANES > 1`, the local catalogue and the results connection use it too. With 1 lane they stay plain connections, as before. Each scan's results insert and commit also run under one lock, so lanes never interleave inside each other's transaction.

## How this was measured

- **Panel.** The frozen speed-030 exact-match panel (`data/latency/speed030-paired.jsonl`), 25 of its 28 photos (10 raw, 10 slab, 5 phone captures). The 3 `recent_phone` captures exist only on staging. Each run sent the panel twice (50 scans) after a 2-scan warm-up, using `api/scripts/lane_replay.py`.
- **Catalogue.** Staging's exported catalogue (local SQLite backend, 50,270 cards) and staging's artwork bundle `PS-CATALOGUE-EN-JA-SETH3-20261017`, with production thread settings (`ORT_INTRA_THREADS=1`, `DINO_INTRA_THREADS=2`) and production recognition flags.
- **Byte identity, native.** Runs on an M4 Pro Mac, Python 3.14, with label reads drained (`GRADING_AT_CARD_DEADLINE=false`) and every scan graded (`GRADING_REQUIRES_CLIENT_HINT=false`), so grading is exercised on every scan:
  - 1 lane, one at a time, twice: 50/50 identical to each other.
  - 2 lanes, one at a time: 25/25 identical to 1 lane.
  - 2 lanes, two in flight, twice: 50/50 identical to 1 lane.
  - Repeated on the final code (serialized connections): 1 lane 25/25 identical to the earlier 1-lane run, and 2 lanes with two in flight 50/50 identical to 1 lane, with no server tracebacks.
- **Latency and memory.** The `docker/api.Dockerfile` image (Linux arm64, Python 3.12), run with `--cpus 4 --memory 7g`. Production flags, with the phone's slab hint sent (`graded=true` for slabs only), as the app does. Peak memory is the server process's `VmHWM` and the container's `memory.peak`.
- **Tests.** The full API suite passes with the default (733 passed, 3 skipped). New tests (`tests/test_scan_lanes.py`) cover:
  - lane wiring and session sharing;
  - lane checkout under contention;
  - the 2-slot limiter;
  - a 4-thread eviction hammer on the artwork reference cache;
  - a serialized-connection hammer;
  - a real-model test (runs when `SCANAPP_TEST_MODELS_DIR` points at the ONNX models) where two lanes read OCR and DINO concurrently and must equal one lane bit for bit.

## Limits

- Measured on ARM (M4 Pro, and Docker's Linux VM on it), not the x86 Hetzner host. `--cpus 4` is a CPU quota on a 14-core machine, not 4 dedicated cores, and the PokeSingle API and Dokploy were not running alongside. Before relying on these numbers, re-measure on the host itself.
- The local runs had no reference-feature bundle (it pins x86) and no reference images. So the SIFT artwork and layout verifiers and the feature store were barely exercised by the panel. Their thread safety rests on the code audit and the cache hammer test.
- The panel is 25 photos, not unseen traffic. 3 lanes were not measured.
- With production deadline grading, label results depend on timing, as they do today with one lane.

## Rolling out

1. Set `SCAN_LANES=2` on the production API service (memory limit at least 3.5 GiB) and keep `SCAN_WAIT_LIMIT` as is.
2. Watch `request_done` latency, 503s and the container's memory.
3. Roll back by removing the variable.
