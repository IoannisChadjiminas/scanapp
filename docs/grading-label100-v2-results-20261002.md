# Grading recovery v2 — 2 October 2026

Correct company and grade together: **74/100**, up from **26/100** in v1. Correct company: **79/100**; correct grade: **84/100**. Wrong returned company: **0**; wrong returned grade: **0**. **26 labels still require review**; this is not complete or near-100% recognition.

| Grader | Photos | Company correct | Grade correct | Both correct | Pending |
|---|---:|---:|---:|---:|---:|
| psa | 17 | 17 | 17 | 17 | 0 |
| beckett | 16 | 15 | 16 | 15 | 1 |
| cgc | 17 | 17 | 13 | 13 | 4 |
| tag | 17 | 10 | 10 | 10 | 7 |
| ace | 16 | 5 | 11 | 4 | 12 |
| ags | 17 | 15 | 17 | 15 | 2 |

## Generic changes

- Safe registered/trademark typography, older CGC headings, plus-grade and AGS native descriptor support. No fuzzy issuer aliases or numeric grade inferred from a descriptor.
- Bounded label proposals from geometry and located OCR fields, perspective rectification, contrast and observed right-column digit recovery; maximum six OCR calls, including errors, with one-call exit for clear labels.
- Official PSA, Beckett, TAG, ACE and AGS shape templates; independently supported label text is mandatory. Colour and recognized card identity cannot supply the company. Template matches are not authenticity verification.
- Certificate-scoped issuer transfer, cross-view conflict checks and exclusion of card-body EX suffixes below the label. Subgrades and TAG scores cannot become an overall grade.
- Additive API company_source field; native grade/descriptor retained, unreadable/conflicting fields null. Unknown is not ungraded and raw physical condition remains not_assessed.

## Validation and limitations

646 API tests pass, including 93 grading tests. Tests cover upright slabs in landscape photos, rotation, six-call bounds, trademark/legacy labels, native descriptors, logo polarity, threshold-only digit rejection, descriptor/number contradictions, seller-watermark/card-text rejection, conflicting holders, API serialization/history and card-ranking isolation.

The separate existing 100-photo control set contains 20 labelled slabs and **80 raw/unlabelled photos**. False slab claims: **0/80**; wrong returned companies/grades: **0/0**. This small reused control set is not proof of a zero population false-positive rate.

Label-component latency: median **1769 ms**, p95 **5779 ms**, maximum **8000 ms** under concurrent local Docker inference. Not staging HTTP or end-to-end scan latency. Recovery increases tail cost; USE_GRADING=false disables it.

The 100-label photos and manual truth were frozen before v1. They are now tuning/regression data, **not an unseen accuracy test**. The final snapshot verifies code/assets did not change during the run; the scorer also verifies truth and every image hash. No certificates/card IDs are hardcoded into inference. Certification-digit, descriptor, subgrade and TAG-score accuracy are not independently scored. No authentication or physical raw-condition claim.

Remaining failures concern missed/too-small issuer marks, stylized/embossed digits and incorrectly localized/poor-resolution labels. Null does not establish that the photo is unreadable to a human. A stronger trained label/digit detector and a fresh independent benchmark are still needed; the pending rows below must not be called fixed.

A wider-crop experiment produced one incorrect CGC gold-digit read (4 on a Pristine 10). That experiment was rejected. Final recovery requires the thresholded digit to be independently read from original colour pixels in the same position; top-descriptor/numeric contradictions abstain instead of inferring a 10. The final numbers here exclude rejected/intermediate experiments.

All changes are local. No deployment, database mutation, credential creation or grading-company certificate lookup occurred.

## Residual manual-review queue

Open the original full photo or source listing. Request a straight, close label photo without glare when a field cannot be established. These are per-photo OCR gaps, not incorrect catalogue mappings.

| Photo | Expected company / grade | Observed company / grade | Warnings |
|---|---|---|---|
| [label100_406975129126](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_406975129126.jpg) · [source](https://www.ebay.com/itm/406975129126) | beckett / 8 | None / 8.0 | grading_company_unreadable_or_unsupported |
| [label100_147245288873](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_147245288873.jpg) · [source](https://www.ebay.com/itm/147245288873) | cgc / 10 | cgc / None | overall_grade_unreadable_or_ambiguous |
| [label100_800716677202](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_800716677202.jpg) · [source](https://www.ebay.com/itm/800716677202) | cgc / 10 | cgc / None | overall_grade_unreadable_or_ambiguous |
| [label100_157534594084](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_157534594084.jpg) · [source](https://www.ebay.com/itm/157534594084) | cgc / 10 | cgc / None | condition_grade_contradiction |
| [label100_326878079751](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_326878079751.jpg) · [source](https://www.ebay.com/itm/326878079751) | cgc / 10 | cgc / None | overall_grade_unreadable_or_ambiguous |
| [label100_137154472208](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_137154472208.jpg) · [source](https://www.ebay.com/itm/137154472208) | tag / 9 | None / None | no_supported_grading_label_detected, ungraded_status_not_proven |
| [label100_127844524552](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_127844524552.jpg) · [source](https://www.ebay.com/itm/127844524552) | tag / 10 | None / None | no_supported_grading_label_detected, ungraded_status_not_proven |
| [label100_267615603004](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_267615603004.jpg) · [source](https://www.ebay.com/itm/267615603004) | tag / 10 | None / None | no_supported_grading_label_detected, ungraded_status_not_proven |
| [label100_205373770550](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_205373770550.jpg) · [source](https://www.ebay.com/itm/205373770550) | tag / 10 | None / None | no_supported_grading_label_detected, ungraded_status_not_proven |
| [label100_398150162220](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_398150162220.jpg) · [source](https://www.ebay.com/itm/398150162220) | tag / 10 | None / None | no_supported_grading_label_detected, ungraded_status_not_proven |
| [label100_117278078333](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_117278078333.jpg) · [source](https://www.ebay.com/itm/117278078333) | tag / 10 | None / None | no_supported_grading_label_detected, ungraded_status_not_proven |
| [label100_407228091588](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_407228091588.jpg) · [source](https://www.ebay.com/itm/407228091588) | tag / 9 | None / None | no_supported_grading_label_detected, ungraded_status_not_proven |
| [label100_147552021925](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_147552021925.jpg) · [source](https://www.ebay.co.uk/itm/147552021925) | ace / 10 | ace / None | overall_grade_unreadable_or_ambiguous |
| [label100_317559256789](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_317559256789.jpg) · [source](https://www.ebay.co.uk/itm/317559256789) | ace / 6 | None / None | no_supported_grading_label_detected, ungraded_status_not_proven |
| [label100_227526033226](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_227526033226.jpg) · [source](https://www.ebay.co.uk/itm/227526033226) | ace / 8 | None / None | no_supported_grading_label_detected, ungraded_status_not_proven |
| [label100_407143628483](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_407143628483.jpg) · [source](https://www.ebay.co.uk/itm/407143628483) | ace / 2 | None / 2.0 | grading_company_unreadable_or_unsupported |
| [label100_137209581494](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_137209581494.jpg) · [source](https://www.ebay.co.uk/itm/137209581494) | ace / 9 | None / None | grading_company_unreadable_or_unsupported, overall_grade_unreadable_or_ambiguous |
| [label100_287567779040](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_287567779040.jpg) · [source](https://www.ebay.co.uk/itm/287567779040) | ace / 10 | None / None | no_supported_grading_label_detected, ungraded_status_not_proven |
| [label100_397078152442](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_397078152442.jpg) · [source](https://www.ebay.co.uk/itm/397078152442) | ace / 10 | None / 10.0 | grading_company_unreadable_or_unsupported |
| [label100_287166531557](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_287166531557.jpg) · [source](https://www.ebay.co.uk/itm/287166531557) | ace / 10 | None / 10.0 | grading_company_unreadable_or_unsupported |
| [label100_318837968582](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_318837968582.jpg) · [source](https://www.ebay.co.uk/itm/318837968582) | ace / 10 | None / 10.0 | grading_company_unreadable_or_unsupported |
| [label100_366424401446](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_366424401446.jpg) · [source](https://www.ebay.co.uk/itm/366424401446) | ace / 10 | None / 10.0 | grading_company_unreadable_or_unsupported |
| [label100_197567930366](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_197567930366.jpg) · [source](https://www.ebay.co.uk/itm/197567930366) | ace / 10 | None / 10.0 | grading_company_unreadable_or_unsupported |
| [label100_267680041404](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_267680041404.jpg) · [source](https://www.ebay.co.uk/itm/267680041404) | ace / 7 | None / 7.0 | grading_company_unreadable_or_unsupported |
| [label100_168242458584](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_168242458584.jpg) · [source](https://www.ebay.com/itm/168242458584) | ags / 9.5 | None / 9.5 | grading_company_unreadable_or_unsupported |
| [label100_196982574569](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_196982574569.jpg) · [source](https://www.ebay.com/itm/196982574569) | ags / 9.5 | None / 9.5 | grading_company_unreadable_or_unsupported |

## Reproducible artifacts

- [All 100 JSON responses, truth, warning codes, hashes and timings](grading-label100-v2-results-20261002.json)
- [Final code/asset snapshot](grading-label100-v2-validated-code-snapshot-20261002.json)
- [Raw-card/slab control results](grading-label-v2-controls-20261002.json)
- [Original v1 baseline](grading-label100-baseline-20261002.json)
- [API contract and policy](scan-grading-evidence.md)
- Official logo URLs, extraction transforms and hashes: `api/app/recognition/assets/grading-logos/sources.json`
