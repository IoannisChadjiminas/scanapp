# On-phone index check: does a compressed index reach the same stage 1 decision? (step 0, 2026-10-27)

Plan: `docs/on-phone-match-best-frame-plan-20261027.md`, step 0. Script: `api/scripts/on_phone_index/check_compressed_index.py`. Offline, no phone, no server writes. Photos and the index stay outside git; only aggregate counts are here.

**Result: int8 passes the gate as written, but only just.** 312 of 315 scans (99.05%) reach the same vector decision as float32, with 0 new wrong passes. The three disagreements are all near a threshold (details below). int8 with the top 50 re-scored at float32, and float16, agree on 315 of 315 (100%).

## What was run

- **Index:** the server's 43,695 x 384 `pad` index (`catalogue/vectors/pad`), normalised rows. The model checksum matches the index manifest (`dinov2_sha256` prefix `2ddf6ec79e37`).
- **Embedding:** the server's `DinoEmbedder.embed(crop, 'pad')` (`api/app/recognition/embed.py`), one thread.
- **Android queries (201):** the stored Android manual uploads whose card the owner's list names (`stage1_bench/run_bench.OWNER`). The crop is the 98% centre crop of the upload (`run_bench.whole_card`), after EXIF orientation.
- **Panel queries (114 of 157):** the frozen A55 panel, cropped with the gallery quad exactly as `android_fastpath_replay.server_quad_vectors`. The label is the panel's expected card. 43 photos are skipped: 12 with no gallery quad, and 31 where the replay's crop returned nothing or the photo had no expected card.
- **Rule:** the vector part of `stage1_gate.decide`, using the constants `TWIN_COSINE 0.84`, `STAGE1_MARGIN 0.02`, `CONTRADICTION 0.05` and the `_top` / `_pair_margin` helpers. The text is assumed to name the labelled card, which is an upper bound on the text. The artwork check, printing groups, number repair and set-total rules are not run. This is the vector side only.
- **Wrong-text test (added):** for each query the text is also set to each of the float32 top-5 other cards, which is what a misread printing could look like. That gives 5 extra text cases per query (1,575 pairs in all). A new wrong pass is a variant that answers one of those wrong cards while float32 does not.

## Variants

1. **float32** (reference): `E @ q`.
2. **int8**: per-dimension symmetric scale (`max|E[:, d]| / 127`), the query scaled by the same per-dimension factor and quantised once per search, int32 dot product, then rescaled.
3. **int8 search, top 50 re-scored at float32**: computed, but not reported. The plan says to report it only if variant 2 fails the gate, and variant 2 passes.
4. **float16**: optional variant, run in full.

## Results (all 315 scans)

| Variant | Index size | Top-1 agrees with float32 | Top-5 overlap | Margin change median / max | Vector decision agrees | New wrong passes (of 1,575 wrong-text pairs) | Search, median / p90 (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|
| float32 (reference) | 67,115,648 B (64.0 MiB) | 100% | 100% | 0 / 0 | 315/315 | 0 | 0.56 / 0.58 |
| **int8** | 16,780,672 B (16.0 MiB) | 97.14% | 98.67% | 0.00050 / 0.00221 | **312/315 (99.05%)** | **0** | 5.83 / 5.91 |
| int8, top 50 re-scored (not reported, see above) | 83,896,320 B (80.0 MiB, float32 kept) | 99.37% | 99.87% | 0 / 0 | 315/315 | 0 | 6.13 / 6.26 |
| float16 (optional) | 33,557,888 B (32.0 MiB) | 99.37% | 99.87% | 0.00002 / 0.00008 | 315/315 | 0 | 15.53 / 15.80 |

The search times are numpy, single thread, on the Mac. They are a relative guide only, not phone numbers. Note that int8 is slower than float32 in numpy because of the int32 conversion per chunk.

Top-1 agreement is by card identity (printings of the same card collapse).

### Per set

| Set | Queries | int8 vector decision agrees | float16 vector decision agrees | int8 wrong-text pairs agreeing with float32 |
|---|---:|---:|---:|---:|
| Android whole-card | 201 | 199/201 (99.0%) | 201/201 | 993/1,005 |
| Panel, gallery quad | 114 | 113/114 (99.12%) | 114/114 | 564/570 |
| All | 315 | 312/315 (99.05%) | 315/315 | 1,557/1,575 |

Float32 vector decisions, all scans (the reference): answer 79, twin 28, too close 47, contradiction 70, no agreement 91 (the last includes labels whose card is not in the index, which is zero here). Android alone: answer 50, too close 23, contradiction 51, no agreement 76, twin 1. Panel alone: answer 29, twin 27, too close 24, contradiction 19, no agreement 15. The Android contradiction count (51) is close to the abstain-reasons doc (50), which used a slightly different rule for same-name printings.

## The three int8 disagreements

All three are close to a threshold. None is a wrong card answered.

1. **Android, owner's card sv04-159 (twin with its promo printing):** float32 too close (margin 0.0002), int8 no agreement. Neither answers.
2. **Android, owner's card 30th-077:** float32 answers at margin 0.0202, int8 gives too close at 0.0195. The margin is 0.0005 short of the 0.02 line. Same card either way; the phone would answer one scan later, not wrongly.
3. **Panel, owner's card sv01-212 (Japanese twin):** float32 too close (pair margin 0), int8 answers the labelled card as a twin (pair margin 0.0015 above the line). This is a new answer, but on the correct card, so it is not a wrong pass.

## What this does and does not show

- **Wrong text is not stopped by the vector rule in float32 either.** In the wrong-text test, float32 answers a wrong printing in 423 of 1,575 pairs. That is the vector side alone, so it is why the server's text checks and stage 1b are there. The gate here only asks that compression adds no wrong passes, and it adds none.
- **Vector side only, text as upper bound.** The artwork check, printing groups, set totals and number repair are not in this check. The plan's live text reader still has to supply a correct card name and number.
- **Panel is 114 of 157 photos.** The other 43 have no crop in the replay's rectangle path or no expected card; not reconciled with the replay's own count.
- **Floating-point warnings.** The float32 and float16 matmuls raised numpy RuntimeWarnings (divide by zero, overflow, invalid). The inputs and index are finite (index norms 0.99999988 to 1.00000012; all query vectors finite and non-zero). All 315 score vectors came out finite, and the top score agrees with a float64 recomputation on all 315 queries. The warnings are BLAS flag noise on this machine, not bad data.

## Gate

- Same vector decision as float32 on at least 99% of scans: **int8 passes (99.05%)**; int8 top 50 re-scored and float16 pass (100%).
- 0 new wrong passes: **all variants pass (0 of 1,575 wrong-text pairs)**.
- **Verdict:** int8 passes the gate as written, but with 3 disagreements out of 315 at the edge of the thresholds. The live round in step 3 of the plan should check it again before the phone relies on it. If the margin should be safer, the top-50 re-score (80 MiB including the float32 rows) gives 100% agreement here.

## Not done

- No phone measurements (step 1), no live scans, no server or staging changes. Staging was only read to copy photos; nothing was written there.
- The panel vectors are the replay's crop, stored in the scratch folder, not a fresh phone capture.
