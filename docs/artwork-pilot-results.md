# Artwork retrieval pilot and public physical-photo audit

2026-10-01 — implemented and tested locally; **default off, not deployed**.

The correct catalogue printing was offered for review in **7 of 8 raw physical
photos**, and **3 of 3 manually annotated artwork patches**. Cropped Fuecoco was
recovered without lowering decision thresholds. The remaining wood-table
Pikachu photograph requests a retake, with no visible guessed printing.

This is a diagnostic convenience sample, **not an 87.5% scanner accuracy claim**.
There are only four distinct card identities. Physical-photo camera provenance,
authenticity and image editing are not established; they are visually inspected
photographs of physical cards, not independently captured app-camera holdouts.

## Paired results

Both columns use the same final safety/verification code and unchanged
thresholds. Only the optional artwork artifact is disabled/enabled. This
isolates its contribution from the additional fixes discovered during testing.

| Correct printing in returned review choices | Artwork disabled | Pilot enabled |
| --- | ---: | ---: |
| Raw physical photos, automatic detection and language | 5/8 | 7/8 |
| Manually annotated physical-photo artwork patches | 2/3 | 3/3 |
| Full catalogue references, synthetic control | 5/5 | 5/5 |
| Catalogue artwork crops, synthetic control | 4/5 | 5/5 |

No returned-choice recall regressions in these pairs. Blank returns `retake`,
noise returns `no_match`, and neither exposes suggestions. No wrong automatic
printing claim was observed. There was only **one automatic match among the
eight raw photos**, correctly identifying Alakazam ex; the other successes
remain uncertain or printing-ambiguous. No automatic claim on artwork patches.
The five reference controls are deliberately indexed-reference overlaps and
cannot establish independent physical-photo performance.

The full stream retrieved the correct printing in 4/8 raw shortlists; the
artwork stream did so in 7/8. Returned choices may additionally expand through
reference families beyond either shortlist. These are catalogue-printing
metrics, not certified artwork-family labels or foil/stamp detection metrics.

Machine-readable results: [artwork-pilot-benchmark.json](artwork-pilot-benchmark.json).
Sources/visual labels: [internet-photo-pilot-sources.json](internet-photo-pilot-sources.json).
Raw third-party images remain outside Git; no redistribution licence was
established. Source URLs and SHA-256 checksums are retained. Exact-byte overlap
with the pilot reference assets was rejected; broader duplicate/pretraining
overlap is unknown. Printed rules text has been omitted from the saved report.

## Physical-photo outcomes

| Photo | Pilot response | Correct printing offered? |
| --- | --- | --- |
| Fuecoco on dark stand | Uncertain | Yes |
| Fuecoco on playmat, tilted/reflective | Uncertain | Yes |
| Fuecoco on smaller clear stand | Uncertain | Yes |
| Pikachu in hard holder with glare | Printing review | Yes |
| Pikachu on wood table, tilted/darker | Retake | No |
| Bibarel with strong holographic glare | Printing review | Yes |
| Tight full-art Alakazam ex | Matched | Yes |
| Tilted full-art Alakazam ex on dark table | Uncertain | Yes |

The failing Pikachu also failed **forced correct-reference** geometric
verification. Its full-photo framing detector found no quadrilateral, and its
bottom copyright line was previously chosen as a fallback name. Fixing name
evidence did not establish a geometrically verified match. This remains a
framing/photographic-verification failure, not a reason to lower thresholds or
accept the visually leading 30th-printing guess. A tightly framed retake is the
current safe outcome; improving card/holder segmentation is further work.

## Implementation and safety

- Separate versioned artifact: `artwork-hypotheses-v1`. **837 cards / 1,674
  regions**, versus 37,755 unchanged full-card vector rows. Includes selected
  subject families and seeded random distractors, not full-catalogue coverage.
  49 selected references were unavailable and explicitly skipped.
- Two explicit reference crop hypotheses: conventional illustration window and
  broad centre. They are **not validated layout classes**. Full-art, trainer,
  e-Reader and energy coverage still need systematic layout validation.
- Query as supplied always; optionally two portrait crop hypotheses. No forced
  card-aspect warp in this new retrieval/verifier code. Existing automatic
  quadrilateral detection remains a separate, imperfect input stage.
- Reuse the selected full-stream embedding; union top-15 distinct card IDs per
  hypothesis with the full top-20, bounded at 65 IDs. Raw cosine scores are kept
  separate, not averaged, summed or interpreted as confidence probabilities.
  Duplicate profiles collapse by card ID, not by name; different printings keep
  their IDs, mappings and finish choices.
- Reserve verification slots for artwork-only candidates. At most eight
  distinct printing references, three query-region hypotheses and 1,000 SIFT
  features per region. Inlier, coverage, spatial-spread and reflection checks
  remain unchanged. Coverage is relative to the logged query patch.
- Geometry never overrides known-language/name evidence to promote a foreign
  printing. Collector mismatch can still verify a sibling's *art*, but that
  seed must expand into printing review or request a retake; it cannot become
  an isolated conflicting printing result. Missing/weak/bare-number evidence
  does not manufacture proof of a particular printing.
- Copyright/collector text used as a fallback name has no name-region confidence.
  Short OCR noise is not a strong name contradiction. A weak unrectified raw
  photograph that fails geometry now requests a retake rather than exposing
  a guessed printing.
- Artwork/SIFT rescue always abstains from automatic printing acceptance.
  Finish selection remains manual; glare is a test condition, not foil proof.
- Optional artifact validation checks full-vector/ID snapshot hashes, model,
  preprocessing, crop profiles, file checksums, dimensions, finite normalized
  vectors, unique card/profile rows, card counts and bound language metadata.
  An explicitly configured incompatible bundle fails readiness, not silently
  falling back. Provenance, bounded candidate union and verifier details are
  persisted in existing scan JSON, without a SQL migration.

## Performance and verification

Final Python suite: **316 passed, 1 skipped**, one existing Starlette warning.
This includes incompatible/corrupt artifact rejection, deduplication without
merging printings, vector reuse, empty-language searches, opt-in configuration,
artwork-only outside-top-K rescue, metadata-conflict handling, retake guards,
and actual SIFT recovery of artwork small within a larger constructed image.
Flutter/web were not changed in this pilot; their earlier contract tests are
recorded in [cropped-card-recognition.md](cropped-card-recognition.md).

Raw-photo local median end-to-end: about **3.33 s disabled / 3.77 s enabled**;
observed enabled maximum **4.15 s**. With only eight raw photos these are not a
stable P95 or server SLO. Additional portrait embeddings took about 252–262 ms;
pilot artwork matrix search stayed below 1.6 ms on the raw photos. Local
verification stayed below 201 ms. OCR and catalogue/variant enrichment still
dominate; no sub-200-ms end-to-end promise or network/vector-database timing is
implied. Cold caches/order and laptop/container scheduling affect these numbers.

## Reproduction and remaining gates

Scripts:

- `api/scripts/build_artwork_pilot.py --output /output/index --distractors 512`
- `api/scripts/download_photo_pilot.py --manifest docs/internet-photo-pilot-sources.json --output <new-private-directory>`
- `api/scripts/benchmark_artwork_pilot.py --pilot-dir /pilot --sources /workspace/docs/internet-photo-pilot-sources.json`
- `api/scripts/diagnose_photo_framing.py` for private detector/forced-reference previews.

The model benchmark/build ran in the pinned local API image with `/data` mounted
read-only, network disabled and result storage in memory. The public downloader
is separate, anonymous and bounded, without following redirects or bypassing
access challenges. The private artifact/photos are currently in
`/tmp/scanapp-artwork-pilot.YybpeB`; that temporary artifact is not a deployment
dependency and may be deleted by the OS. Code, labels, model/full-snapshot and
artifact checksums are recorded for reproduction; exact public image bytes may
become unavailable later.

**PlanetScale, mappings, existing vectors, live services and staging remain
unchanged.** Enabling this on staging would require a separately retained,
validated full-catalogue artifact and explicit rollout approval. The current
837-card seeded index must not be presented as complete coverage.

Next: a larger independent phone/app holdout, including Japanese and mixed
language shared-art pairs, actual cropped captures, negative/non-card inputs,
energy/trainers, e-Reader layouts and different glare/holder conditions. Freeze
it before further tuning; report abstention, exact-printing recall, false
specificity and measured latency separately. Expand reference indexing only
after this safety/coverage review, retaining existing mappings and full vectors.
