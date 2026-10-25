# Superseded: Internet photo corpus test — 23 October 2026

> **Invalidated by an image-size audit on 23 October 2026.** The original
> `data/photo-corpus` panel was mostly eBay thumbnails: 343/350 images had a
> 225px long edge (median 225px). The number-read and card-boundary rates below
> are not valid evidence for the algorithm. A separate `s-l1600` full-size
> panel is being collected and will be reported in
> `internet-photo-test-fullsize-20261023.md`. Do not use the metrics below for
> model or rollout decisions.

## Result

The 350-photo corpus completed the local iPhone text-diagnostics pass in seven
batches of 50. The measured end-to-end phone text pass had **59.5 ms median,
186 ms p90, 201 ms p95, 231 ms p99, and 284 ms maximum**. The phone detected a
card boundary in **109/350 (31.1%)**, returned a parsed card name in **60/350
(17.1%)**, and returned a collector number in **4/350 (1.1%)**.

This was a phone-side text and card-boundary test only. The photos were not
submitted to the staging scanner. Therefore **stage 1/stage 1b answer counts,
server accuracy, server timing, and background-check disagreements were not
measured**. No zero-wrong claim can be made from this run.

The first attempt to process all 350 in one app run was terminated by iOS after
174 photos. The complete result below comes from the subsequent seven 50-photo
batches; every batch reached its complete state and produced 50 result rows.

## Corpus and method

- **Photos:** 350 eBay Browse API primary listing photos, retained locally for
  this internal evaluation. No photos, listing titles, seller details, or
  source URLs are included in this report or committed with it.
- **Buckets:** modern raw (112), vintage WOTC raw (82), slabs (73), hard cases
  (43), Japanese raw (33), and same-artwork reprints (7).
- **Phone:** iPhone 15 running the PokeSingle diagnostic build, with Apple
  Vision and the production Dart text/footer pipeline. The local harness used
  the full-image/card-shaped path with `full_edge=1200`; it did not upload
  photos or invoke server recognition.
- **Timing:** per-photo `elapsed_ms` from the diagnostic harness, including the
  text/footer path. The 300 ms spacing between photos is excluded. The cold
  recognizer warm-up is recorded separately by the harness and is not included
  in these per-photo quantiles.
- **Labels:** 104 photos had a simple collector-number guess parsed from the
  listing title. These are unverified guesses, not ground truth. There were no
  reviewed card labels for this run.
- **Privacy:** the detailed local photo inputs and per-photo diagnostic output
  remained outside Git. The iPhone diagnostic folder was empty after testing;
  the app was restored to a release build without diagnostic flags.

## iPhone results by bucket

| Bucket | Photos | Card boundary | Name parsed | Number read | Title-number guesses* | Read matched guess* | Median ms | p90 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Hard case | 43 | 6 (14.0%) | 1 (2.3%) | 1 (2.3%) | 1 | 0 | 48 | 154 |
| Japanese raw | 33 | 11 (33.3%) | 0 | 0 | 9 | 0 | 50 | 164 |
| Modern raw | 112 | 42 (37.5%) | 52 (46.4%) | 0 | 64 | 0 | 73.5 | 196 |
| Same-artwork reprint | 7 | 6 (85.7%) | 1 (14.3%) | 1 (14.3%) | 3 | 1 | 165 | 177 |
| Slab | 73 | 33 (45.2%) | 3 (4.1%) | 0 | 23 | 0 | 78 | 177 |
| Vintage WOTC raw | 82 | 11 (13.4%) | 3 (3.7%) | 2 (2.4%) | 4 | 2 | 49 | 150 |
| **Total** | **350** | **109 (31.1%)** | **60 (17.1%)** | **4 (1.1%)** | **104** | **3** | **59.5** | **186** |

`p90` is the nearest-rank 90th percentile. `Read matched guess` compares the
returned number with the title-derived guess; it is not a correctness score.
Three reads matched those guesses. The fourth read was `238/191` while the
title-derived guess included an `EX` prefix (`EX238/191`). Without reviewed
labels, none of these comparisons establishes a correct or incorrect card
identification.

## iPhone timing distribution

| Percentile / statistic | Elapsed time |
|---|---:|
| Median | 59.5 ms |
| p90 | 186 ms |
| p95 | 201 ms |
| p99 | 231 ms |
| Maximum | 284 ms |

The maximum exceeded the 250 ms target, and p99 was close to it. The median
and p90 were below the target. This is a seller-photo diagnostics result, not
a controlled manual-shutter or gallery-import benchmark.

## Earlier Mac pass

The same corpus was also run through the iOS `CardWarp.swift` Vision executable
and production Dart text pass on the Mac. It is reported separately because it
is not phone timing:

| Bucket | Photos | Card detected | Number read | Title-number guesses* | Read matched guess* |
|---|---:|---:|---:|---:|---:|
| Hard case | 43 | 6 | 1 | 1 | 0 |
| Japanese raw | 33 | 11 | 0 | 9 | 0 |
| Modern raw | 112 | 41 | 1 | 64 | 0 |
| Same-artwork reprint | 7 | 5 | 1 | 3 | 1 |
| Slab | 73 | 33 | 0 | 23 | 0 |
| Vintage WOTC raw | 82 | 10 | 3 | 4 | 3 |
| **Total** | **350** | **106** | **6** | **104** | **4** |

Mac per-photo time was **30 ms median, 91 ms p90, and 232 ms maximum**. As with
the phone run, the title guesses are not ground truth and the Mac results do
not measure server identification accuracy.

## Not measured

| Requested result | Status | Reason |
|---|---|---|
| Stage 1 / stage 1b answers | Not measured | No scan requests were sent to staging. |
| Correct / wrong server answers | Not measured | There are no reviewed ground-truth labels and no server responses. |
| Full-pipeline top-card accuracy | Not measured | The local text diagnostic does not invoke server recognition. |
| Background-check disagreements | Not measured | No server background checks were run for this corpus. |
| Server CPU / latency | Not measured | No recognition request reached the server. |
| Phone embedding coverage or timing | Not measured | This was a text-only run; the on-demand embedding download reported `failed:download` in the diagnostic build. |
| Slab label read rate | Not measured as a separate metric | The harness reports parsed name/number fields, not a validated slab-label field. |

## Next steps

1. Build the planned send-to-staging harness with a diagnostic run identifier,
   then send the corpus in batches of about 50 using the normal multipart scan
   fields. Keep those requests out of user analytics.
2. Produce a review sheet and label at least 90% of the corpus from the card
   images/catalogue. Listing-title guesses alone do not meet the ground-truth
   requirement.
3. Join reviewed labels, phone outputs, and staging `stage0`, `stage1_check`,
   and `scan_summary` records. Report every wrong answer and every background
   disagreement; keep stage 1/stage 1b disabled for production decisions unless
   the labeled replay shows zero wrong early answers.

The per-photo diagnostic results and photo files remain in the local temporary
test workspace and are not part of this report. This report is an aggregate of
the completed phone and Mac text passes, not the final server-accuracy report
specified by `docs/internet-photo-test-plan.md`.
