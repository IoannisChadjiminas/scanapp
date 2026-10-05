# Scan grading evidence

The scan API and `/api/v1/session/results` now return an additive `grading`
object belonging to the **photographed copy**, not the catalogue card. The
card catalogue, vectors, Cardmarket URLs, prices and finish selection are
unchanged by grading extraction. Separate card-recognition improvements are
reported in the dated benchmark reports; label grades are never card-identity proof.

Example for a readable PSA label:

```json
{
  "grading": {
    "slab_detected": true,
    "is_graded": true,
    "grading_status": "graded",
    "company": "psa",
    "company_source": "label_ocr",
    "grade": 10.0,
    "condition_label": "GEM MT",
    "subgrades": {},
    "tag_score": null,
    "certification_number": "71772050",
    "qualifiers": [],
    "raw_condition": "not_assessed",
    "authenticity_verified": false,
    "source": "visible_label_ocr",
    "requires_confirmation": true,
    "label_text": [],
    "warnings": []
  }
}
```

The actual `label_text` includes the observed OCR lines; the example omits them
for brevity. `company` supports `psa`, `beckett` (including BGS), `cgc`, `tag`,
`ace` and `ags`. Company names must be confidently read or matched to a packaged
official logo shape within an independently supported label region;
a logo/company watermark alone is insufficient. Grade and descriptor remain
separate: a CGC Pristine 10 is not silently normalized to Gem Mint 10, and an old
CGC 9.5 stays 9.5. An explicitly read TAG `SCORE` is separate from its 1–10 grade.

## Unknown, ungraded and authentication-only

- No supported visible label: `slab_detected`, `is_graded`, `company` and `grade`
  are null, `grading_status` is `unknown`. This may be an ungraded card, a sleeve,
  an unfamiliar holder or a slab whose label is cropped/blurred out. **Absence of
  readable text does not prove ungraded.** The schema reserves `ungraded` for
  future explicit confirmation; this detector does not fabricate that status.
- Company readable but grade unreadable: `slab_detected: true`, company returned,
  `grade: null`, `is_graded: null`, status `unknown` and a review warning.
- A dated/numbered label, certification number and condition descriptor readable
  but logo unreadable: preserve the grade if independently readable, keep company
  null and warn `grading_company_unreadable_or_unsupported`. Never infer PSA from
  a red border, CGC from gold colouring or a company from the recognized card.
- An authentication-only label: status `authenticated_only`, `is_graded: false`,
  no numerical grade. This records the label's claim, **not verified authenticity**.
- Missing or conflicting fields stay null. Conflicting overall grades or
  condition descriptors cannot choose a grade. Multiple certificates in separate
  or unlocalized fields also block the grade. Conflicting OCR readings of the
  same localized certificate field instead make only the certificate null, with
  `certification_number_unreadable_or_ambiguous`; an independently read overall
  grade remains available.
- Raw-card physical condition is always `not_assessed`. No automatic NM/LP/MP/HP,
  inferred numerical grade or front-only damage assessment is offered. A useful
  raw-condition assessment needs front/back close-ups and a separate validated
  workflow, particularly for surface damage hidden by sleeves/glare.

All reads require confirmation. OCR confidence is not a calibrated probability
that the holder is genuine. No certificate verification or issuer lookup is
performed. Preserve the user's ability to correct/confirm the displayed evidence.
The six named graders have parser tests and a manually annotated 100-label
seller-photo diagnostic. It is now reused for tuning/regression, not independent
unseen accuracy. `verified_logo` means a shape match, not authentic-holder proof.

## Processing, diagnostics and storage

Read a label strip from the original request frame before recognition's automatic
card cropping, **once after selection**, including retake/no-match responses. An
explicit user crop/rotation is respected: do not read another card's label outside
that crop. EXIF orientation is respected.

At most ten grading OCR calls, counting failures: readable labels exit after
one; recovery can use portrait upright/upside-down or landscape rotations,
bounded geometric/text label proposals, perspective correction, contrast and
right-column digit retries. A central logo-only retry requires the same uniquely
read certificate and cannot replace grade/certification digits. Unknown
logos are never guessed from label colour or card identity. Separate numeric
overall grades require observed proximity to a condition descriptor and must
not be near subgrade headings. Dates, collector numbers, HP and attack values
cannot become grades. Label passes bypass the per-line orientation classifier
after whole-label orientation handling, so a standalone `9` is not silently
rotated into `6`. This uses the pinned RapidOCR engine without mutating shared
recognition flags. Numeric recovery requires two literal reads at different
scales from original pixels; an enlarged crop cannot create missing detail.
Logo geometry excludes confident OCR word boxes to prevent circular evidence.

Numeric grading evidence never enters card OCR ranking, collector extraction,
identity resolution or printing/finish confidence. The separate holder-header
review path described below only orders already supported printing choices.
Model failure is non-fatal and produces
`grading_ocr_failed`; unavailable/disabled OCR has explicit warning codes.
`timings_ms.grading_ms` includes grading work and `total_ms` includes its latency.
`versions.grading` is `slab-label-ocr-v3.3`; the version and evidence persist in the
existing scan `ocr_json`, requiring no database migration. Historical scans
without the field return unknown defaults, not retrospectively invented grades.
Session isolation and single-scan persistence remain unchanged.

`USE_GRADING=true` by default; set `USE_GRADING=false` to remove this extra OCR
cost. `USE_OCR=false` also disables it. The Flutter/web clients can ignore the
additive field until a grading display/confirmation UI is implemented.

## Sources used for scale semantics

Only printed values are read, never calculated from company grade descriptions
or subgrades. Reference documentation:
[PSA](https://www.psacard.com/gradingstandards),
[Beckett](https://www.beckett.com/grading),
[CGC](https://www.cgccards.com/card-grading/grading-scale/),
[TAG](https://taggrading.com/pages/scale),
[ACE's grading reports](https://acegrading.com/cert/380446),
[AGS](https://agscard.com/grading-standards).

This change is local; no staging deployment, catalogue/PlanetScale mutation,
credential creation or third-party certificate request was performed.

## Historical v1 validation on 2026-10-02

599 API tests pass, including 46 grading tests. Multipart `POST /api/v1/scans`
serialization, persisted session history, legacy history, explicit user crops,
enabled/disabled/failed grading OCR, rotation, subgrade isolation and the two-call
budget (including a failed logo retry) are covered.

The [physical-photo label report](grading-label-physical-probe-20261002.json)
uses 100 existing seller photos, with 20 manually inspected slab labels. Of 18
PSA/CGC labels, the company was readable/correct for 13 and the overall grade for
16. The other two grades (gold embossed CGC 10s) stayed null. There were **zero
wrong returned companies or grades**, and **zero slab claims on the 80 photos
without labelled slabs**. Two unsupported/unidentified holders stayed unknown.
These are tuned convenience-sample diagnostics, not a guarantee on new camera
photos or proof of grader/authenticity accuracy. Certification digits and real
subgrade extraction were not independently scored.

Extra OCR cost under concurrent local Docker test load: about 1.94 seconds
median / 2.37 seconds p95. This is not a staging latency measurement. Unreadable
logos stay null instead of using colour/layout as a company guess.

The completed [50-photo recognition regression](physical-photo-holdout4-grading-v1-audit.json)
retained 50/50 correct best matches, with identical best IDs and statuses to the
previous frozen run: 14 matched, 28 uncertain, 8 printing-ambiguous, zero wrong
automatic confirmations. Blank/noise controls stayed non-matches. All report
source hashes match the final code. This is an existing tuned regression, not
new-photo accuracy; the API's printing/finish safeguards were not relaxed.

## V2 recovery and residual review

V2 adds safe trademark normalization, historical CGC headings, plus-grade and
AGS native descriptors, equivalent descriptor formatting, dated set headers,
TAG alphanumeric certification strings and scoped official-logo matching.
Original orientation is tried first even for landscape photographs: wide
backgrounds do not imply a sideways holder. Side-rotation recovery shares the
same six-call budget. Localized text crops retain left-hand issuer marks.
It bounds label text below a uniquely located certificate to exclude card-body
suffixes such as `EX`. Independent views cannot silently disagree on the grade,
issuer or certificate; subgrades never supply an overall grade.

Thresholding can turn foil texture into a high-confidence wrong OCR digit.
Digits found only in the thresholded right-column pass therefore require a
matching read from original colour pixels at the same location. Top-descriptor
numeric contradictions return null and `condition_grade_contradiction`; they
never supply a replacement number. CGC's current and legacy Pristine/Perfect
10 semantics are documented in its [official scale](https://www.cgccards.com/card-grading/grading-scale/).

The [v2 report](grading-label100-v2-results-20261002.md) contains final measured
coverage, raw-card controls, latency, source hashes and every incomplete label.
The historical numbers above apply to v1 only. The same 100 labels cannot be
used to claim new-photo/general accuracy after tuning. Certification digits,
TAG scores, subgrades and native descriptors still need independent scoring.

Official offline template provenance is recorded in
`api/app/recognition/assets/grading-logos/sources.json`; no benchmark label was
used as a template. This detector does not claim to authenticate copied logos.
Unresolved fields remain null with warnings and require manual confirmation or
a close, straight, glare-free label photo. Unknown does not mean ungraded.

## V3.2 recovery reference

The recovery budget is now ten passes, including failures; clear labels still
exit after one. Original orientation precedes rotation, with bounded label-panel
rectification, wider strips when independent label identities are visible,
localized wordmark proposals, and original-pixel numeral recognition. The
minimum literal grading confidence remains 0.80 and the strict logo threshold
remains 0.72. Logo proposals cannot assign an issuer without supporting evidence.

Card OCR separately marks a header as `holder_name` when dated/numbered identity,
an independently readable issuer or certificate, and condition/subgrade fields
occur together without a printed card-layout badge. This prevents an English
holder translation from vetoing a Japanese card title. It does not infer a
grader, grade, printing or translation from the catalogue.

The original 100-label regression, remaining manual-review queue and scope are
in the [v3.2 label report](grading-label100-v32-results-20261002.md). The measured
historical reports above retain their original versions and denominators.

The [accepted mixed card/slab report](card-and-slab-accuracy-v32-20261002.md)
separates printing accuracy from label coverage on 100 newly collected photos.
Its [manual-review queue](card-and-slab-manual-review-v32-20261002.md) preserves
unresolved card and label cases as pending, not successful identifications.

## Holder printing review v15

For supported labelled slabs already classified `printing_ambiguous`, one
additional header OCR pass may order an existing artwork family. Independent
card-name evidence, a dated holder identity, condition/issuer-or-certificate
context, a literal `#` collector identifier and an exact expansion name/code
must agree. Reliable printed collector fractions remain constraints. The
status stays ambiguous; grade, finish, edition and authenticity remain separate.
This path cannot create a card/URL, translate a name or bypass a retake.

`timings_ms.holder_hint_ms` measures this optional extra pass. Saved diagnostics
record `holder_printing_hint.preferred_card_id`, literal header lines and the
review-only policy; a changed order adds
`holder_label_printing_hint_review_only` to confidence reasons. Displayed and
persisted candidate IDs stay consistent. Probability remains uncalibrated/null.

The [v15 regression report](card-slab-holder-review-v15-20261002.md) records the
measured card improvement and pending cases. Its full-pipeline grading results
still use v3.2; these versions must not be conflated.

## V3.3 first-strip numeral recovery

An incomplete label with an independently supported issuer can propose a tight
original-pixel glyph crop next to an observed condition descriptor before panel
rectification. Two literal numeric reads at different scales must agree. The
descriptor cannot supply a number, and grade/certificate/conflict checks still
apply. The established wider panel crop remains the default; tightening that
path globally lost a working ACE grade and was rejected.

This extra view shares the ten-call grading budget. It does not run on labels
that already have a readable issuer and numeric grade, or on unsupported labels.
It changes neither numeric confidence thresholds nor logo thresholds, Cardmarket
mappings, catalogue membership or vectors. It does not prove ungraded status,
authenticity or physical condition.

The [v3.3 validation report](grading-v33-validation-20261002.md) separates the
final label-component regressions from the earlier full card run and the small
combined integration smoke. It lists all thirteen still-incomplete labels.
