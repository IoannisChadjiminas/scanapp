# Instant recognition, Phase 0: offline feasibility gate (2026-10-25)

**Verdict: FAIL.** The on-phone index, as designed in `docs/instant-recognition-plan.md`, does not reach the gate on this Mac measurement. Image-only top-5 is 74% (gate: 97%). With the phone's own name and number used to narrow candidates, top-5 is 83%, still short. No likely rule tested keeps wrong-likely under 1% while showing a likely on a useful share of photos. Per the plan, Phases 1–3 should not start on this design.

No phone, app or server change was made. Numbers and card ids only; photos and OCR text are not in git. Machine-readable numbers: `docs/experiments/instant-recognition-phase0-20261025.json`. Scripts and tests: `api/scripts/instant/`, `api/tests/test_instant_phase0.py`.

## Inputs and where they came from

| Input | Source (local, read-only) | Used |
|---|---|---|
| Server card index | `data/android-embedding-research-20261023/catalogue/vectors/pad/` (server export, import `PS-CATALOGUE-EN-JA-ENID2-20261019`), with `catalog.sqlite` from the same export | 43,695 rows, 41,468 catalogue groups, 384 dims |
| Server model | `teacher/dinov2_small.onnx`, sha256 prefix `2ddf6ec79e377069` matches the export manifest; revision `ed25f3a3…` | Query embeddings (ONNX on CPU) |
| Frozen A55 panel | `panel-queries/queries.json` and the warped card crops it lists | 157 photos: 144 scored, 12 without a card quad, 1 label not in the index |
| Internet corpus | `data/photo-corpus-fullsize-20261023/raw/` (312 full photos) | Agreement and margins only (no card labels exist for it) |
| Vintage and real iPhone scans | **Not available as vectors** on this Mac (only the 8 golden fixtures) | Not measured |
| Reference features | `reference-features` bundles: per-card features used by the server's stage-1 matching, not the global index this measures | Not used |

Staging was not contacted. The index is the local export from the 2026-10-19/20 work, and I did not check it against staging's current index.

Index size note: the brief says 44,021 cards. The catalogue has 50,270 cards and the search index 43,695 rows; 44,021 is the count in `teacher/cards.json` (training list). The numbers below use the 43,695-row index.

## Index formats

| Format | In memory | Top-1 agreement with fp32 (corpus, 312) | Panel top-1 / top-5 (image only) |
|---|---|---|---|
| fp32 | 67.1 MB | 100% (reference) | 55 / 107 of 144 |
| fp16 | 33.6 MB | 99.4% | 55 / 107 (same) |
| int8 (per-row scale) | 17.0 MB (incl. 0.17 MB scales) | 95.8% | 55 / 107 (same) |

fp16 changes no panel answer. int8 changes no image-only panel answer, and one answer (+1 correct top-1) in the text-filtered run. The format is not what limits accuracy: the search itself fails at fp32.

Duplicate handling: rows are collapsed to catalogue groups by provider id. That collapses 2,227 rows: 561 English bare/`en:` duplicates, 1,652 Japanese/Traditional-Chinese pairs, and 14 English/Japanese pairs. Grouping is lenient: a top-1 that is the other printing in the same group counts as correct. Strict row-level scoring would give equal or lower numbers.

## Accuracy on the frozen panel (144 scored photos)

Phone-style card crops, six frames each (frame 0 used for accuracy). Image-only = search of the index with the crop's embedding. Text-filtered = the same search restricted to candidates whose name and number match the phone's own OCR read (cascade: name and number, then number, then name; no filter if none). The phone read a name for 127 of 144 photos and a number for 113.

| Search | Top-1 | Top-1 in the label's name-and-number family | Top-5 (95% lower bound) |
|---|---|---|---|
| Image only, fp32 / fp16 / int8 | 38.2% (55) | 39.6% | **74.3%** (66.6%) |
| Text-filtered, fp32 / fp16 | 77.1% (111) | 78.5% | **82.6%** (75.6%) |
| Text-filtered, int8 | 77.8% (112) | 79.2% | **82.6%** (75.6%) |

Panel labels by category: 141 unique cards, 3 reprint (same name and number, other set), **0 twins**. The panel cannot separate twins from reprints or English from Japanese twins. In the index, the same name-and-number analysis finds 114 English/Japanese twin groups (same artwork, cosine ≥ 0.9), 2,181 reprint groups and 39,173 unique groups; none of them has a labelled phone photo.

Server reference point, same panel: the staging replay of 2026-10-20 (`data/latency/ondevice-embedding-20261020/emb_primary.jsonl`) gives the expected card for 126 of 154 labelled photos (81.8%), counting `uncertain`, `retake` and `printing_ambiguous` as misses. That pipeline differs (OCR, reference features, status gating), so it is context, not a like-for-like comparison.

## Margins

Margin = top-1 score minus the best score of a different group.

| Search | Correct top-1: median (p25 – p75) | Wrong top-1: median (p25 – p75, p95) |
|---|---|---|
| Image only (fp32) | 0.028 (0.008 – 0.054) | 0.012 (0.005 – 0.028, p95 0.055) |
| Text-filtered (fp32) | 0.121 (0.057 – 0.173) | 0.011 (0.005 – 0.021, p95 0.065) |

The margins of wrong and correct answers overlap heavily. Margin alone cannot separate them at any useful threshold.

## "Likely" rule: wrong-likely and shown share

A likely fires on frame k if the same group is top-1 with margin ≥ m on the last N frames. Frames are jittered crops of the same photo (scale 0.97–1.03, shift ±2%). That is a stand-in for real camera frames, not a measured video stream, so stability here is optimistic.

Selected rows, fp32 (`wrong` = likely shown on the wrong card; `shown` out of 144 for image only, out of 144 for text-filtered):

| Search | m | N | Likely shown | Wrong likely | Wrong rate (95% upper bound) |
|---|---|---|---|---|---|
| Image only | 0.02 | 1 | 89 (62%) | 43 | 48% (59%) |
| Image only | 0.05 | 1 | 36 (25%) | 12 | 33% (50%) |
| Image only | 0.10 | 2 | 5 (3.5%) | 0 | 0% (43%) |
| Text-filtered | 0.02 | 1 | 130 (90%) | 18 | 14% (21%) |
| Text-filtered | 0.05 | 1 | 115 (80%) | 7 | 6.1% (12%) |
| Text-filtered | 0.10 | 1 | 101 (70%) | 3 | 3.0% (8%) |

Smallest-risk search: over the full grid (m ∈ {0 … 0.10}, N ∈ {1, 2, 3}) no rule has wrong-likely under 1% with a useful share shown. The image-only rule with 0 wrong (m = 0.10, N = 2) shows a likely on 5 of 144 photos, and its 95% upper bound is 43%. The text-filtered rules bottom out at 3% wrong. The plan's rule (wrong-likely < 1% and a likely on ≥ 60% of raw-card photos) is not met by any row.

Sample size: 144 photos cannot show a wrong-likely rate below about 2% even with zero errors, so a pass would still need a larger labelled set. This failure is far beyond that limit.

## Internet corpus (312 full photos, unlabelled)

No card labels exist for this corpus, so it gives no accuracy. It shows agreement and margins only:

- Top-1 agreement with fp32: fp16 99.4%, int8 95.8%.
- Share of photos with margin ≥ 0.02 (single frame): 32%; ≥ 0.05: 11%.

Full-photo embeddings, not card crops, so this does not stand in for the phone's input.

## Search time on this Mac and phone estimates

Brute force over 43,695 × 384, one query at a time, numpy on the Mac CPU (median and p90 of 200 queries):

| Format | Mac median | Mac p90 | Bytes scanned |
|---|---|---|---|
| fp32 | 0.62 ms | 0.77 ms | 67.1 MB |
| fp16 (converted to fp32 per query) | 1.70 ms | 1.91 ms | 33.6 MB |
| int8 (numpy int32 conversion) | 6.88 ms | 7.14 ms | 17.0 MB |

Phone (**estimate, not measured**): the scan is memory-bound at about 50 GB/s, so the floor is about 1.3 ms for fp32, 0.7 ms for fp16 and 0.3 ms for int8. The int8 dot product is 16.8 M multiply-adds, which a NEON or Accelerate kernel does in a few milliseconds. A realistic phone range is 2–10 ms for int8, inside the plan's 15 ms target. The Mac int8 figure is an unoptimised numpy path, so it is an upper bound, not a phone number.

Embedding on this Mac (ONNX CPU, same model): median 14.7 ms per frame. The plan's iPhone figure (27 ms) was measured on a device earlier and is not repeated here.

## Gate

| Criterion | Target | Result | Pass? |
|---|---|---|---|
| Top-5 contains the label | ≥ 97% | 74.3% image only; 82.6% with phone text | **No** |
| Wrong-likely | < 1% | 0% only at 4–5 shown (image only, m = 0.10, N = 2 or 3); otherwise ≥ 3% | **No** (no rule with a useful share) |
| Likely on ≥ 60% of raw-card photos at that rate | ≥ 60% | Not reached at < 1% wrong | **No** |

**Verdict: FAIL.** The gap is 23 points in top-5 (image only) and 14 points (text-filtered). Sampling error on 144 photos is about ±7 points, so the gap is real. Why: a global DINOv2 vector for each card separates visually similar cards poorly. Top candidates often sit close together, and sometimes another card scores higher than the label by 0.05 or more (one checked photo: label 0.823, other card 0.880). The server's pipeline does not rely on that vector alone; it uses text, reference features and gates the result.

## Checks on the pipeline

- Panel crops: in the first six photos checked by hand, the label scored 0.67–0.90 against its crop. The misses are other cards scoring higher, not low label scores, which points at the search rather than the crop.
- Reference images re-embedded with the server's preprocessing reproduce their stored index rows (cosine 1.0 on 30 cards, rounded to 5 decimal places). The index and the query path match.
- The 8 golden fixtures in `ondevice_golden.npz` have vectors identical to the server ONNX output (cosine 1.0), and their keys are not catalogue ids. They do not test the phone model. The earlier iPhone-to-server cosine (0.9967) is from `docs/experiments/internet-photo-test-fullsize-20261023.md` and was not re-measured here.

## What could not be verified

- **Vintage 11 and real iPhone 26 scans:** no vectors are on this Mac; not measured.
- **Twins and English/Japanese split:** the panel has no labelled twin photos. The index structure (114 twin groups) is described above; accuracy on twins is not measured.
- **Reprint accuracy:** 3 panel photos. Too few to say anything.
- **Stability over real frames:** frames are synthetic jitter of one photo.
- **Phone search time:** estimates only.
- **Corpus accuracy:** no labels.
- **Staging:** not contacted.

## Recommendation

Do not start Phase 1 (index pack and log fields) on this design. The lookup itself is the problem, not the format, and the phone's text does not rescue it (83% top-5).

Options to decide between (none tested here):

1. Measure the distilled MobileNet student models already in `data/android-embedding-research-20261023/` on the same harness. Their accuracy on this search is unknown; the harness makes that a cheap test.
2. Keep the phone's "likely" off the image index and show it only from server candidates, which is closer to how the server already works. That gives up offline speed.
3. Re-scope Phase 0 to a fixed-size candidate set (the phone's text plus set totals) before reconsidering the index. The 83% text-filtered result suggests the remaining errors come from number misreads and same-artwork printings.
