# Regulation-mark collector OCR fix

2026-10-02. Implemented and verified locally, not deployed to staging.

## Cause and correction

The Professor's Research photo `trainer2_0` shows a boxed regulation D beside
collector number 201/202. OCR read `D201/202` at confidence 0.95546. The parser
treated D as a collector namespace and penalized both 201 and 209, leaving
visually near-tied printing 209 first. The normalized text displayed publicly
was 201/202, but its strong collector-region evidence still contained D.

The fix separates a single D–J regulation letter immediately before a numeric
fraction during **OCR token extraction only**. It preserves original confidence
and region and keeps raw OCR observations unchanged in diagnostics. No general
catalogue identifier parser, vectors, model, image files, mapping or threshold
is changed. Real/unknown multi-letter namespaces and bare alphanumeric numbers
remain intact, including TG/GG/SM/SWSH/SVP. This is a bounded rule, not arbitrary
alphabetic-prefix removal.

A read-only audit found no D–J single-letter numeric fractions among the
current catalogue's collector/printed identifiers. That audit is not a claim
that arbitrary future catalogues cannot introduce such a namespace.

## Actual photo result

`best_match.card_id` now equals **`en:swsh1-201`**, name Professor's Research
(Professor Magnolia), collector 201, rather than `en:swsh1-209`. OCR-supported
metadata retrieval also proposes 201. Collector/name/language conflict flags
are false. Status is `uncertain`, `match_state` is `likely`, printing evidence
is `metadata_supported`, and finish remains unconfirmed. The raw visual score
is 0.797670; the wrongly preferred 209 retains its higher 0.800450 visual score.
OCR breaks the tie without changing or fabricating embedding similarities.

The five-photo diagnostic includes this photo, another Professor's Research,
Umbreon, Charizard and Lugia. Correct first choices and returned-printing recall
are both 5/5, with no recall regressions. Evidence:
[diagnostic report](recognition-regulation-smoke.json).

## Verification

**452 Python tests passed, one skipped**, with the existing Starlette warning.
Added cases cover regulation D–J numeric fractions, preservation of TG/GG and
promo/unknown prefixes, unchanged generic ID parsing, actual OCR confidence and
region, 201-versus-209 ranking, metadata retrieval, printing resolution and
wrong-denominator rejection. An explicitly observed `D209/202` selects 209;
the correction does not hardcode 201 or silently discard contradictory digits.

Command: `PYTHONPATH=api .venv/bin/python -m pytest -q -c api/pytest.ini api/tests scraper scripts/tests`.

The full **69-photo** rerun now has **69/69 correct first/best matches**, up
from 68/69; returned-printing recall stays 69/69. There are no first-choice or
returned-recall regressions and **zero wrong automatic claims among 23 automatic
claims**. Statuses are 23 matched, 40 uncertain and six printing-ambiguous.

| Frozen regression sample | Before: correct first choice | After | Correct printing returned |
| --- | ---: | ---: | ---: |
| Original 54 photos | 53/54 | 54/54 | 54/54 |
| Additional 12 photos | 12/12 | 12/12 | 12/12 |
| Additional 3 photos | 3/3 | 3/3 | 3/3 |
| Total | 68/69 | 69/69 | 69/69 |

Reports: [54 photos](physical-photo-regulation-final.json),
[12 photos](physical-photo-regulation-identity12-final.json) and
[3 photos](physical-photo-regulation-extra3-final.json). Their source hashes
agree; every explicit `best_match` equals the selected leader. The only changed
first printing is Professor's Research. Gengar `gengar_2` also loses a false
collector-prefix conflict: OCR `E271/264` at 0.94466 becomes 271/264; its already
correct lead (visual 0.914852, margin 0.114567, detected primary frame) moves from
uncertain to matched under the unchanged thresholds. Finish stays unconfirmed.

Evaluations use network-disabled Docker, read-only source/data/artifact mounts,
read-only in-memory catalogue copies and in-memory scan results. Download/label
hashes, full vectors, model, artwork artifact and thresholds are checked against
the previous selected reports. Those reports remain unchanged as baselines.

## Scope and limits

The same frozen revision completes all thirty synthetic reference crop controls
and two blank/noise negatives. Correct-printing returned recall remains **19/30**
with **zero new regressions** and zero false specific/automatic printing claims.
All five artwork-only controls return review choices and no automatic claims;
blank and noise remain rejected. Existing difficult partial/central crop misses
are not fixed by this number-parsing correction. Evidence:
[crop control report](crop-recognition-regulation-final.json), which checks the
current source hashes against the selected physical-photo report.

Private raw runs remain Git-ignored under
`datasets/review/physical-20261002/regulation{54,12,3}-final.jsonl` and
`regulation-crops-final.jsonl`. Public summaries omit OCR rule lines.

The photos are an existing 69-photo tuning/regression set with 21 printing
identities, not a fresh camera accuracy study. Correct best matches on these
photos cannot establish 100% real-world accuracy or calibrated probability.
Finish is not proven by a single photo; existing printing/finish/URL feedback
guards remain unchanged. Probability stays null/uncalibrated.

Policy version: `rank-v8-regulation-mark-ocr`; presentation stays `best-match-v1`.
PlanetScale and staging services were not mutated. No Flutter rebuild or API
image build/deployment is part of this local correction.
