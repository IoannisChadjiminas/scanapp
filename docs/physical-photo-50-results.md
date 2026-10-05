# Frozen 54-photo physical-card benchmark

2026-10-01. Completed locally. No deployment, PlanetScale, mapping or vector writes.

**The correct printing was returned in 18/54 raw photos with the artwork pilot,
versus 17/54 without it. All eight automatic confirmations were correct, but
the large number of retakes means full-art/holder handling is not ready.**
This is a diagnostic sample result, not representative scanner accuracy or a
guarantee against wrong printing claims.

## Sample and method

83 candidate images were manually screened; 54 were selected before scoring.
The sample contains **15 printing identities**, not 54 different cards or
independent photographers: 47 English photos and 7 Japanese photos. There are
38 Pokémon full-art/illustration photos, 7 full-art trainer photos, 6 e-Reader
photos and 3 energy photos. Twenty photos contain graded slabs. Other conditions
include sleeves, glare, stands, large backgrounds and low resolution.

Visible names, collector numbers and language were reviewed independently of
search captions. Gold Mew's unproven paper/metal distinction, custom jumbo
products, multi-card frames, reference-like product images and suspected reused
captures were excluded. Finish, authenticity and grading are not ground truth.
Slab labels can assist OCR, so slab/non-slab results are separated.

Each unmodified photo ran through decoding, automatic card detection,
orientation, retrieval, OCR, geometric verification, local mapping enrichment
and printing review with language `auto`. The same frozen recognition code and
thresholds were used in both runs; only the optional artwork artifact changed.
No forced card crop or truth label was supplied to the recognition pipeline.
These are not Flutter camera/UI or live network/API tests. No artwork-only
physical-crop accuracy or finish-classification accuracy is claimed here.

The full index contains all 15 expected IDs among 37,755 rows. The unchanged
837-card artwork pilot covers 17/54 photo labels (Charizard, Pikachu families),
not the complete sample. It was not rebuilt to include the test cards. Labels,
code/model/index checksums and thresholds are retained in the results.

## Paired outcomes

| Metric | Artwork off | Frozen artwork pilot on |
| --- | ---: | ---: |
| Correct printing in returned choices | 17/54 | 18/54 |
| Correct internal top-ranked printing | 33/54 | 37/54 |
| Automatic confirmations | 8/54 | 8/54 |
| Wrong automatic printing confirmations | 0/8 | 0/8 |
| Retake requests | 34/54 | 34/54 |
| Correct printing in full-stream shortlist | 35/54 | 35/54 |

Internal rank-one is not user-visible success: retakes expose no guessed
printing. There are ten uncertain responses, one printing-ambiguous response
and one no-match in each run. Nine uncertain responses contain the correct
printing with the pilot; one does not. Blank/noise negative controls expose no
suggestions and make no automatic claim in either mode.

The pilot improved one returned-choice outcome, `ereader_6`, from an incorrect
uncertain result to the correct uncertain Expedition Pikachu. No returned-choice
recall regressions occurred. Among pilot-covered labels, returned recall rose
7/17 to 8/17; the artwork shortlist retrieved the correct printing in 16/17.
Retrieval coverage is therefore only one bottleneck—verification and framing
still block many candidates. Uncovered labels stayed at 10/37 returned recall.

| Subgroup: correct printing returned | Off | On |
| --- | ---: | ---: |
| Pokémon full-art / illustration | 12/38 | 12/38 |
| Trainer full-art | 1/7 | 1/7 |
| e-Reader | 3/6 | 4/6 |
| Energy | 1/3 | 1/3 |
| English | 13/47 | 14/47 |
| Japanese | 4/7 | 4/7 |
| Slabs | 4/20 | 5/20 |
| Non-slabs | 13/34 | 13/34 |

These small, repeated-identity subgroups are diagnostic—not population estimates.

## Failure findings and review queue

All **36 cases without the correct returned printing** are preserved in the
machine-readable `failures` queue, with source URLs, labels, checksums, OCR,
pilot coverage and outcomes. This includes the wrong uncertain suggestion, not
only retakes.

- Framing is unreliable. The detector reported a quadrilateral in only 15/54
  images; this is a detection count, not verified detection accuracy. The
  inspected `umbreon_0` output retained the holder/background and became an
  approximately square 899×789 query instead of isolating the card.
- A separate, oracle-assisted diagnostic forced the correct reference into
  geometric verification. Only 11/54 passed existing geometry checks on detector
  output. Three failed returned-recall cases passed forced geometry:
  `trainer_5`, `trainer2_7`, `jpgraded_7`. These are diagnostic proofs, not
  additional recognition successes. Failing geometry does not prove a wrong
  card or bad source label.
- OCR often reads the slab label, HP or `Supporter` as the name. Strong identity
  constraints then receive the wrong text region. For `trainer2_7`, OCR reads
  `201/202`, but the uncertain result suggests rainbow Professor's Research
  `209/202` without including the true printing. This needs a collector/region
  conflict regression test, not relaxed confidence thresholds.
- Four correct automatic matches report a missing Cardmarket link: the three
  Gengar photos and Japanese Mew. Correct printing recognition is not proof of
  complete market mapping or correct finish selection.
- Japanese Mew `ja:SV4a-347` has an incorrect local display set name (Raging
  Surf). Its visible SV4a/347 label was used as truth. The official
  [SV4a product page](https://www.pokemon-card.com/ex/sv4a/index.html) identifies
  Shiny Treasure ex. This was flagged, not silently corrected in the database.

The next implementation priorities are inner-card/holder segmentation,
layout-aware OCR name regions, the Professor's Research number conflict, and
validated full-art/trainer artwork coverage. Preserve this run as the baseline;
once tuning uses these photos, they are a regression set, not a fresh holdout.
Add a new independently captured app-camera holdout before claiming accuracy.

## Timing and verification

Local sequential median: **3.26 s off / 3.77 s on**. Sample nearest-rank P95:
**4.00 s / 4.41 s**; enabled maximum 5.16 s. This is not a server SLO or a
randomized performance experiment: off always precedes on, and scheduling,
caches and the separate diagnostic can affect timing.

Enabled stage medians: OCR 2.22 s, mapping enrichment 1.02 s, initial embedding
257 ms, extra artwork embeddings 253 ms, artwork search 0.69 ms, local verifier
25 ms. Stage medians do not sum to the end-to-end median. OCR and enrichment,
not artwork matrix lookup, are the main measured costs.

Python verification: **321 passed, 1 skipped**, one existing Starlette warning.
The new summary tests preserve retake/uncertain failures, report recall gains
and regressions separately, reject incomplete runs and strip printed OCR rules.
Recognition source hashes match the preceding pilot; no recognition tuning was
performed during this benchmark.

## Evidence and reproduction

- [Reviewed labels and exclusions](internet-photo-50-sources.json)
- [Paired results, strata and failure queue](physical-photo-50-benchmark.json)
- Raw third-party photos: private `/tmp/scanapp-photos50.2ENkL6/photos`, outside
  Git. Source URLs may change; rights and broader pretraining overlap are unknown.
  Selected photos have unique byte hashes and no exact-byte overlap with pilot
  references; this does not prove independence from every catalogue asset.
- Frozen artifact: `/tmp/scanapp-artwork-pilot.YybpeB/index`. Temporary files are
  not durable deployment dependencies.

Run `api/scripts/benchmark_artwork_pilot.py --pilot-dir /pilot
--artwork-dir /artwork --photos-only --sources
/workspace/docs/internet-photo-50-sources.json` in the pinned local API image,
with network disabled and data/workspace/photos/artifact mounted read-only.
Results use in-memory SQLite. Generate the report with
`api/scripts/summarize_photo_benchmark.py`; optional separate framing and
full-index coverage audits are retained without counting them as successes.

**Staging, PlanetScale, existing vectors and mappings remain unchanged. The
artwork pilot remains default-off and was not deployed.**
