# Physical-photo boundary recovery

2026-10-02. Implemented and evaluated locally; **not deployed to staging**.
PlanetScale, catalogue records, Cardmarket mappings, images and vectors were not
modified. Evaluations use the existing opt-in artwork artifact.

## Verified physical-photo outcome

The correct printing is available in **68/69 returned results (98.6%)**, up from
64/69 in the previous selected revision. There are no returned-recall regressions
and no wrong automatic printing claims among 22 claims. Results that require
review or a printing picker are not automatic identifications.

| Frozen regression set | Before: correct printing returned | After | Correct internal first rank | Wrong automatic claims |
| --- | ---: | ---: | ---: | ---: |
| Original 54 photos | 50/54 | 53/54 | 53/54 | 0 of 19 |
| Additional 12 photos | 11/12 | 12/12 | 12/12 | 0 of 1 |
| Additional 3 photos | 3/3 | 3/3 | 3/3 | 0 of 2 |
| Total | 64/69 | 68/69 | 68/69 | 0 of 22 |

Statuses: 22 matched, 42 uncertain, four printing-ambiguous, one retake. Recovered
photos are Charizard `char_1`, Lugia `lugia_5`, Professor's Research `trainer2_3`
and Miriam `holdb_7`. The trainer remains printing-ambiguous; inferred boundary
recoveries remain unconfirmed.

Evidence: [54-photo report](physical-photo-boundary-final.json),
[12-photo report](physical-photo-boundary-identity12-final.json), and
[3-photo report](physical-photo-boundary-extra3-final.json).
Their recognition/runner code hashes agree. The previous selected reports remain
unchanged as baselines.

These 69 internet-listing photos contain 21 printing identities, including 48
Pokémon full-art photos, 12 trainer full-art photos, six e-Reader photos and three
energy photos. They repeat identities and have now been used for tuning. This is
**regression-set recall, not calibrated population accuracy or a 100% precision
guarantee**. Camera origin, authenticity, editing, pretraining overlap and exact
finish are not authenticated. Grading-label OCR may assist identification. The
earlier untouched holdout measurements remain in the previous recovery report.

## Changes and safeguards

- Line-supported quadrilaterals can join outlines broken by sleeves/glare.
  Geometry runs at a maximum 720-pixel side, with twelve lines per axis and up to
  eight output hypotheses. Landscape text panels and unsupported sides are
  rejected. Geometry alone is never printing proof.
- The normal pipeline runs first. Only a non-quality retake without an explicit
  user crop can try recovery. At most eight vector probes select one additional
  OCR/evidence evaluation. Useful first-pass results are never replaced.
- A qualified name that agrees with the first candidate can guide crop selection
  against that reference. This is a retrieval prior, not confirmation: the new
  frame still performs ordinary retrieval and every identity/printing guard.
  Near-tied crop scores preserve geometric order using the existing score gap.
- Confident first-pass name, language and structured collector contradictions
  veto a retry. An automatic retry claim is discarded. Failed retries preserve
  the original retake. Thresholds remain 0.78 visual, 0.70 OCR-assisted and 0.04
  gap; using the OCR-assisted floor for proposals does not bypass acceptance.
- Catalogue identity is preserved before Cardmarket display enrichment. The
  specific Professor's Research `(Professor ...)` descriptive suffix is excluded
  from fuzzy printed-title comparison. Arbitrary parentheses are not stripped;
  artwork, collector evidence and printing ambiguity remain separate.
- Evaluation precedes persistence: exactly one scan row and optional capture are
  saved. Diagnostics record proposals, score, retrieval prior, first-pass and
  retry outcomes, compatibility, selection and all wasted retry time.

**393 Python tests passed, one skipped**, with the existing Starlette warning.
The suite includes actual one-row/one-capture persistence, catalogue/display
suffix handling, name/number vetoes, explicit-crop/quality exclusions, bounded
queries, and existing mapping/finish guards.

Command: `PYTHONPATH=api .venv/bin/python -m pytest -q -c api/pytest.ini api/tests scraper scripts/tests`.

## Crop safety controls

The same frozen revision was also rerun on all thirty synthetic reference crops
and the two blank/noise controls. Correct-printing returned recall stays **19/30**,
with **no new regressions** against the immediately preceding selected crop
report. All five artwork-only fixtures return reviewable printing choices, with
zero artwork-only automatic claims. There are zero false automatic claims across
the thirty positive controls; blank/noise remain rejected.

These are reference-derived controls, not independent camera accuracy. The older
Fuecoco central-patch and Japanese Victini top/partial-crop weaknesses remain
unresolved; unchanged control totals do not mean those failures were fixed.
Evidence: [current crop audit](crop-recognition-boundary-final.json) and
[previous crop recovery audit](crop-recognition-recovery-final.json).

## Latency and remaining case

Across 69 photos, local median was **4.15 seconds**, sample nearest-rank P95
**8.25 seconds**, maximum **9.79 seconds**. The original 54-photo P95 rose from
4.99 to 8.25 seconds because difficult retakes now receive a second evaluation.
Successful first-pass scans skip this recovery. Different shared-machine runs do
not establish a median speed improvement or staging latency SLO.

`umbreon_2`, English Umbreon VMAX 215/203, still requests a retake. Its holder,
reflection and proposed framing do not provide verified artwork or sufficiently
reliable combined printing evidence. The correct internal guess is not surfaced
as confirmed. A clearer, straight-on image without glare is the appropriate
next input; thresholds were not relaxed to force a result.

## Reproduction and rejected trials

All data/source/artifact mounts were read-only, Docker networking disabled, the
catalogue copied into query-only memory, and scan results kept in memory. The
37,755-row full index and separate 4,834-card/9,668-region artwork artifact remain
unchanged. Source URLs/labels/checksums are the existing frozen manifests.
Raw photos and OCR traces stay private under `datasets/review/physical-20261002/`;
they were not trained on, indexed, published or added to Git.

The first line-first trial regressed two photos and crashed on a rounded
out-of-range edge sample; it was rejected, not counted as a completed audit.
Clipped sample coordinates fixed the crash. A subsequent single-pass revision
preserved 50/54 but gained nothing. Two- and eight-proposal retake trials reached
52/54 before the title/identity fixes. Diagnostic subsets are explicitly labelled
and never substitute for the final full audits.

Before staging rollout, still verify artifact/model compatibility, preserve a
rollback image/source, exercise client printing-review support, and run live
concurrency, latency and printing/finish URL tests. Recognition recall does not
certify Cardmarket URL correctness, foil/finish, authenticity, complete artwork
families or existing catalogue metadata warnings.
