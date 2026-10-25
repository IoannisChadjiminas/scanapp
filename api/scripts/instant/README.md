# Instant recognition, Phase 0 (offline feasibility)

Scripts behind `docs/experiments/instant-recognition-phase0-20261025.md`. They
measure whether a card index searched on the phone can give a "likely" card
safely, before any phone or app code is written. Plan:
`docs/instant-recognition-plan.md`.

| File | What it does |
|---|---|
| `index_formats.py` | Builds the fp32, fp16 and int8 (per-row scale) indexes from the server's embeddings, and brute-force searches them. Duplicate rows of one catalogue card (`base1-1`, `en:base1-1`) collapse into one group before ranking. |
| `metrics.py` | Top-1 / top-5 accuracy, twin and reprint "family" tolerance, margin distributions, the stable-frames "likely" rule, and the smallest-risk rule search (Wilson intervals). |
| `embedder.py` | DINOv2-small through onnxruntime. Preprocessing is imported from `app/recognition/preprocess.py`, so it is the server's own code. Also makes six phone-like jitter frames per photo. |
| `phase0_run.py` | The run: builds the indexes, embeds the panel, golden fixtures, reference images and corpus, and writes the JSON numbers. |

Tests: `api/tests/test_instant_phase0.py` (index, collapse, int8 error, metric
and rule logic). Run from `api/`:

```bash
python -m pytest -q tests/test_instant_phase0.py
```

## Running the measurement

The inputs are not in git (photos, catalogue, vectors). They live in the local
`data/` directory of the main checkout. Index binaries and per-frame vectors go to
a scratch folder, not to git.

```bash
python api/scripts/instant/phase0_run.py \
  --data-root /path/to/scanapp/data \
  --scratch /path/to/scratch/phase0 \
  --out-json docs/experiments/instant-recognition-phase0-20261025.json
```

Needs `numpy`, `Pillow` and `onnxruntime` (the server pins 1.22.1; the run used
1.31.0 on Python 3.14). The run takes a few minutes on a Mac CPU.

## Method notes

- Index: `data/android-embedding-research-20261023/catalogue/vectors/pad`, the
  server's padded-resize export (import `PS-CATALOGUE-EN-JA-ENID2-20261019`).
  Model `dinov2-small`, sha prefix `2ddf6ec79e37`, checked against the export manifest.
- Queries: the frozen A55 panel (`panel-queries/queries.json`) using the warped
  card crops the panel already has. Six frames per photo: the crop itself plus
  scale and shift jitter (`embedder.FRAME_SPECS`). Frame jitter is a stand-in for
  real camera frames; it is not a measured video stream.
- Categories (label card, from the catalogue): **twin-en-ja** = same name and
  number, other language is ja, cosine of the two vectors ≥ 0.9. **twin-other** =
  other language. **reprint** = same language, other set, same name and number,
  cosine ≥ 0.9. **unique** = none of these.
- Accuracy is at catalogue-group level. A top-1 in the label's name-and-number
  family but not the label is a printing confusion, reported separately from a
  wrong card.
- A "likely" rule fires on frame k when the same group is top-1 with margin
  ≥ m on the last N frames (N = 1..3). Margin = top-1 score minus the best score
  of a different group.
- Search timing is numpy on this Mac, one query at a time, not a SIMD kernel.
  Phone numbers are estimates, labelled as such in the write-up.

## Files

- Output numbers: `docs/experiments/instant-recognition-phase0-20261025.json`
  (numbers and card ids only, no photo identifiers or images).
- Write-up: `docs/experiments/instant-recognition-phase0-20261025.md`.
