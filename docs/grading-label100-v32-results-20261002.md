# Slab label regression — v3.2 (2026-10-02)

Company and overall grade together improved from **74/100** (v2) to **92/100**. Company: 94/100; grade: 95/100. There are zero wrong returned companies or grades, but **eight incomplete labels remain**. Null outputs are missing coverage, not successes.

This is the original frozen convenience sample, now used for tuning/regression. It is not independent general-camera accuracy. No label image was indexed or used as a logo template. All 100 original photos and annotations remain unchanged.

## Results by grader

| Grader | Photos | Both correct | Company correct | Grade correct | Wrong fields |
| --- | ---: | ---: | ---: | ---: | ---: |
| psa | 17 | 17 | 17 | 17 | 0 |
| beckett | 16 | 15 | 15 | 16 | 0 |
| cgc | 17 | 16 | 17 | 16 | 0 |
| tag | 17 | 16 | 16 | 16 | 0 |
| ace | 16 | 13 | 14 | 13 | 0 |
| ags | 17 | 15 | 15 | 17 | 0 |

## Incomplete labels for manual review

| Photo | Expected company / grade | Returned company / grade | Warnings |
| --- | --- | --- | --- |
| [label100_406975129126](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_406975129126.jpg) · [source](https://www.ebay.com/itm/406975129126) | beckett / 8 | None / 8.0 | grading_company_unreadable_or_unsupported |
| [label100_147245288873](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_147245288873.jpg) · [source](https://www.ebay.com/itm/147245288873) | cgc / 10 | cgc / None | overall_grade_unreadable_or_ambiguous |
| [label100_205373770550](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_205373770550.jpg) · [source](https://www.ebay.com/itm/205373770550) | tag / 10 | None / None | no_supported_grading_label_detected, ungraded_status_not_proven |
| [label100_317559256789](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_317559256789.jpg) · [source](https://www.ebay.co.uk/itm/317559256789) | ace / 6 | ace / None | overall_grade_unreadable_or_ambiguous |
| [label100_227526033226](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_227526033226.jpg) · [source](https://www.ebay.co.uk/itm/227526033226) | ace / 8 | None / None | grading_company_unreadable_or_unsupported, overall_grade_unreadable_or_ambiguous, certification_number_ambiguous |
| [label100_287567779040](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_287567779040.jpg) · [source](https://www.ebay.co.uk/itm/287567779040) | ace / 10 | None / None | no_supported_grading_label_detected, ungraded_status_not_proven |
| [label100_168242458584](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_168242458584.jpg) · [source](https://www.ebay.com/itm/168242458584) | ags / 9.5 | None / 9.5 | grading_company_unreadable_or_unsupported |
| [label100_196982574569](/Users/ioannischadjiminas/WebstormProjects/scanapp/datasets/review/grading-label100-20261002/frozen-photos/label100_196982574569.jpg) · [source](https://www.ebay.com/itm/196982574569) | ags / 9.5 | None / 9.5 | grading_company_unreadable_or_unsupported |

## Verification and scope

- No previously complete v3.1 label regressed. The v3.2 changes preserved 92 complete labels while recovering fields in the separate fresh sample.
- Overall grade recovery uses independent literal reads, not descriptor-to-number inference. Different readings of a single certificate field cannot erase an independently observed grade; multiple separate certificates still block it.
- Unreadable issuer marks remain unknown. No company guesses from label colour, card identity or seller titles.
- Certification digits, subgrades, TAG scores, native descriptors, authenticity and raw condition do not have independently scored accuracy here.
- Isolated local grading latency under concurrent Docker load: median 1.48s; p95 12.58s. Not a staging latency measurement.
- Local changes only; this work does not deploy staging or change PlanetScale.

Machine-readable [accepted-version results](grading-label100-v32-accepted-results-20261002.json), [runtime snapshot](grading-label100-v32-accepted-code-20261002.json), and [API reference](scan-grading-evidence.md).

The [accepted mixed card/slab report](card-and-slab-accuracy-v32-20261002.md) covers the separate 100-photo collection, including new label coverage and paired card-recognition regressions. Its [manual-review queue](card-and-slab-manual-review-v32-20261002.md) keeps unresolved cases pending.
