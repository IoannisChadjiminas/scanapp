# Likely-card presentation and confidence evidence

2026-10-02. Local implementation and read-only regression testing; not deployed
to staging. PlanetScale, mappings, catalogue records, reference images and
existing full/artwork vectors are unchanged. Tests use the previously frozen
opt-in artwork artifact, not evaluation photos added to the index.

## Policy change

Previously, the English Umbreon VMAX 215/203 photo `umbreon_2` already ranked
correctly, but the framing/rejection policy hid the candidate. Full-card cosine
similarity was 0.770661, artwork similarity 0.709755, and name OCR confidence
0.99416. The number was unreadable; local keypoints did not verify the frame.

The new review-only path requires agreeing full/artwork retrieval and a strong
meaningful name, with both similarities above the existing OCR-assisted floor.
Missing collector text is unknown printing evidence, not a reason to hide a
likely card. Readable structured contradictions, known language conflicts,
weak visuals, metadata-only guesses and quality retakes still block rescue.
Automatic thresholds remain 0.78 visual, 0.70 OCR-assisted, 0.04 gap.

Umbreon now returns `printing_ambiguous`, a visible suggestion and an explicit
printing choice; it is **not automatically confirmed**. Its finish remains
unconfirmed. The printing-selection guard in the feedback endpoint still requires explicit
printing selection and an offered printing/compatible finish URL.

The additive scan/history `confidence` object reports raw similarities, OCR
confidence, ambiguity, confirmation/retake guidance and reasons. Actual
`probability` is null with `calibration_status: uncalibrated`; cosine and OCR
scores are not percentages of correct card recognition. Contract and example:
[recognition-confidence.md](recognition-confidence.md).

Tiny collector regions may receive one bounded OCR interpolation retry. Only
strong structured identifiers are retained; first-pass observations remain
unchanged. A contributed retry cannot introduce automatic `matched` status.
Two exploratory issues were caught and rejected: incidental `2N` text on Lugia
and a weak `200/1` fraction on Blastoise. Both have regression tests.

## Validation

Correct-printing returned recall is **69/69**, up from 68/69, with no returned
recall regressions. There are **zero wrong automatic claims among 22 automatic
claims**. Statuses: 22 matched, 40 uncertain and seven printing-ambiguous; no
physical-photo retakes remain in this frozen sample. Internal exact-printing
Rank 1 is still **68/69**, not 69/69: review choices matter for the remaining
Professor's Research printing ambiguity (209 ranked first instead of 201/202).

| Frozen regression sample | Before: correct printing returned | After | Wrong automatic claims |
| --- | ---: | ---: | ---: |
| Original 54 photos | 53/54 | 54/54 | 0 of 19 |
| Additional 12 photos | 12/12 | 12/12 | 0 of 1 |
| Additional 3 photos | 3/3 | 3/3 | 0 of 2 |
| Total | 68/69 | 69/69 | 0 of 22 |

Evidence: [54-photo report](physical-photo-likely-final.json),
[12-photo report](physical-photo-likely-identity12-final.json), and
[3-photo report](physical-photo-likely-extra3-final.json). Recognition/runner
hashes agree across all three reports; every new confidence payload has null
probability and the uncalibrated marker. The earlier selected boundary reports
remain unchanged as baselines.

Across 69 photos, observed local median latency was **4.32s**, sample
nearest-rank P95 **5.29s**, maximum **10.05s**. Previous selected sample median
was 4.15s and P95 8.25s: the collector retry adds some median cost while likely
presentation avoids some expensive retake/boundary recovery. Umbreon fell from
9.57s to **5.06s** in these runs. These shared-machine measurements are not a
staging latency guarantee or an improvement in every case.

Runs use network-disabled Docker, read-only source/data/artifact mounts, a
read-only in-memory catalogue copy and in-memory scan results. Source labels,
download hashes, model/full-vector hashes and thresholds are checked before
evaluation. Source hashes are recorded and must agree across the selected runs.

**415 Python tests passed, one skipped**, with the existing Starlette warning.
Tests cover the likely-card gate, wrong name/number/language and weak visual
rejection, printing-family expansion, one-choice explicit printing review,
bounded OCR retries, preserving first-pass failures/evidence, no automatic
retry upgrade, JSON confidence/history persistence, and existing finish/URL
guards.

Command: `PYTHONPATH=api .venv/bin/python -m pytest -q -c api/pytest.ini api/tests scraper scripts/tests`.

## Crop and negative controls

The same frozen revision completes all thirty reference-derived crop probes and
two blank/noise controls. Correct-printing returned recall remains **19/30**,
with **zero new recall regressions** and zero false specific/automatic claims.
All **5/5 artwork-only** inputs return printing-review choices; none is
automatically confirmed. Blank and noise are rejected. Printing-ambiguous
statuses rise from thirteen to fourteen without changing recall.

Evidence: [crop audit](crop-recognition-likely-final.json). The audit verifies
current source hashes against the physical-photo report before summarizing.
Existing difficult partial/central/bottom-only crop misses, including Fuecoco
central-patch and Japanese Victini cases, are not resolved by this presentation
change. Full-photo returned recall must not be used to claim those are fixed.

Private raw runs are retained under
`datasets/review/physical-20261002/likely{54,12,3}-final.jsonl` and
`likely-crops-final.jsonl`; evaluation photos and raw OCR rule text remain
Git-ignored. Public reports omit OCR rule lines. No evaluation containers are
left running; ordinary local services remain unchanged.

## Interpretation limits

These 69 internet-listing photos cover 21 printing identities and are now a
tuning/regression set, not independent camera holdouts or calibrated population
accuracy. Repeated identities, grading labels, unknown photographic origin,
authenticity, editing, pretraining overlap and finish all limit interpretation.
Returning the correct printing among explicit review choices is not equivalent
to exact printing Rank 1 or an automatic correct claim. Reference crop controls
are synthetic and do not establish real-camera crop accuracy.

No artwork-index build, database change, app rebuild, API image build or staging
deployment is included in this local validation. Policy revision is
`rank-v7-likely-identity-review`; an enabled compatible artwork index is needed
for the new dual-stream rescue.
