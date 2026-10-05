# Slab-label v3.3 validation

Local final-code validation, 2 October 2026. `slab-label-ocr-v3.3` adds a tight original-pixel numeral proposal on the first label strip while retaining the established broad panel crop. It requires two agreeing literal reads and keeps descriptor, issuer, certificate and subgrade conflict safeguards. Thresholds and the ten-call budget are unchanged.

## Measured label results

| Sample | Previous complete company/grade pairs | v3.3 complete pairs | Wrong returned companies | Wrong returned grades | Still incomplete |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original 100 slabs | 92/100 | 93/100 | 0 | 0 | 7 |
| Later 50 slabs | 44/50 | 44/50 | 0 | 0 | 6 |
| Later 50 raw negatives | Not counted as slab successes | 0 false slab claims | 0 | 0 | Not applicable |

Original issuer coverage is 94/100 and numeric-grade coverage 96/100. Later issuer coverage is 44/50 and numeric-grade coverage 47/50. Unknown/null fields remain incomplete. This is not close-to-100% joint label recognition on the later sample.

The recovered [CGC foil-label photo](../datasets/review/grading-label100-20261002/frozen-photos/label100_147245288873.jpg) now returns its literal grade 10 and CGC issuer together. No previously complete company/grade pair is lost across the 150 slabs. No test image was added as a logo template or embedding reference.

## Rejected experiments

- Additional issuer-word crops recovered none of the 14 previously incomplete labels.
- Tightening all component-based numeric crops recovered the CGC grade but lost the working ACE grade on `fresh100_307061782471`. That version was rejected.
- The accepted additive crop preserves the wider legacy panel proposal; the final ACE photo still returns ACE / 8.
- The earlier larger-recognizer experiment remains rejected and contributes no enabled recoveries to these counts.

These are generic crop/evidence changes, not photo-ID, card-name, certificate-number or expected-grade exceptions in inference. Printed descriptors never manufacture a numeric grade.

## Pending label queue

| Original photo | Expected company / grade | Returned company / grade |
| --- | --- | --- |
| [Original Beckett](../datasets/review/grading-label100-20261002/frozen-photos/label100_406975129126.jpg) | Beckett / 8 | null / 8 |
| [Original TAG](../datasets/review/grading-label100-20261002/frozen-photos/label100_205373770550.jpg) | TAG / 10 | null / null |
| [Original ACE 6](../datasets/review/grading-label100-20261002/frozen-photos/label100_317559256789.jpg) | ACE / 6 | ACE / null |
| [Original ACE 8](../datasets/review/grading-label100-20261002/frozen-photos/label100_227526033226.jpg) | ACE / 8 | null / null |
| [Original ACE 10](../datasets/review/grading-label100-20261002/frozen-photos/label100_287567779040.jpg) | ACE / 10 | null / null |
| [Original AGS A](../datasets/review/grading-label100-20261002/frozen-photos/label100_168242458584.jpg) | AGS / 9.5 | null / 9.5 |
| [Original AGS B](../datasets/review/grading-label100-20261002/frozen-photos/label100_196982574569.jpg) | AGS / 9.5 | null / 9.5 |
| [Later PSA Charizard](../datasets/review/grading-fresh100-20261002/frozen-photos/freshimg_0_1212241946.jpg) | PSA / 8 | null / 8 |
| [Later Beckett Mew](../datasets/review/grading-fresh100-20261002/frozen-photos/freshimg_1_113190404.jpg) | Beckett / 9 | null / 9 |
| [Later CGC Shaymin](../datasets/review/grading-fresh100-20261002/frozen-photos/fresh100_326075712447.jpg) | CGC / 10 | null / null |
| [Later TAG Lucario/Melmetal](../datasets/review/grading-fresh100-20261002/frozen-photos/fresh100_377526701873.jpg) | TAG / 10 | null / null |
| [Later ACE Eevee](../datasets/review/grading-fresh100-20261002/frozen-photos/fresh100_205408031074.jpg) | ACE / 9 | null / null |
| [Later ACE Dark Charizard](../datasets/review/grading-fresh100-20261002/frozen-photos/fresh100_227337115305.jpg) | ACE / 8 | null / 8 |

All thirteen are pending, not fixed. The machine-readable results retain source URLs, manual truth and warning codes. The next issuer/digit-localization work must preserve these originals as regression controls and use separate development/evaluation photos.

## Final-code checks and scope

750 API tests pass, including 121 label/glyph tests and 35 holder-hint tests. Tests cover repeated-read disagreement, descriptor contradiction, absent context, blank glyph proposals, legacy crop preservation, the bounded call count, shared OCR flags, API serialization/history and review-only ranking consistency. One existing Starlette deprecation warning remains.

The final current-code five-photo integration smoke preserves both corrected Eevee/Gyarados first choices as `printing_ambiguous`, the ACE / 8 label and correct card suggestion, and the two unsupported small/truncated-card retakes. It is a diagnostic subset, **not another accuracy test**.

The completed [100-photo card-ranking regression](card-slab-holder-review-v15-20261002.md) was run with grading v3.2. The final 200-photo label-component runs use v3.3, and the final five-photo integration smoke uses v15/v3.3 together. The full 100-photo card pipeline was not rerun after the numeric recovery patch; these scopes and hashes must not be combined into a fictional joint run.

Original label-component latency under concurrent local Docker load: median 1.24 seconds, p95 12.05 seconds. Later mixed label-component latency: median 2.01 seconds, p95 11.16 seconds. These are not staging HTTP/Flutter latency measurements.

Both complete component probes validate unchanged code/assets during execution and every original photo/truth hash. These reused seller-photo samples are tuned regressions, not new untouched or population-random accuracy estimates. Authenticity, raw physical condition, foil/edition, certification-digit, subgrade, descriptor and TAG-score accuracy are not independently scored. Zero observed mistakes does not guarantee zero future mistakes.

No staging deployment, PlanetScale mutation, catalogue import, vector change or mapping write occurred.

## Evidence

- [Original 100-slab results](grading-label100-v33-results-20261002.json) and [code/assets snapshot](grading-label100-v33-code-20261002.json)
- [Later 100-photo label-component results](grading-fresh100-v33-results-20261002.json) and [code/assets snapshot](grading-fresh100-v33-code-20261002.json)
- [Final five-photo integration smoke](card-slab-v15-v33-smoke-20261002.jsonl) and [full app/logo snapshot](card-slab-v15-v33-smoke-code-20261002.json)
- [API evidence semantics](scan-grading-evidence.md) and [remaining improvement plan](scan-accuracy-improvement-plan.md)
