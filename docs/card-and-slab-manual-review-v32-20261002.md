# Card and slab manual-review queue — v3.2 (2026-10-02)

These cases are **pending**, not done. Card printing and slab-label extraction are separate review tasks; a single photo can appear in both queues. Results correspond to the accepted local implementation, not a newly deployed staging service. Null denotes missing evidence, not a fabricated grade or proof of an ungraded card.

## Six new card cases

| Original photo | Expected printing | Returned result | Remaining issue |
| --- | --- | --- | --- |
| [PSA Charizard ex](../datasets/review/grading-fresh100-20261002/frozen-photos/freshimg_0_1212241946.jpg) · [source](https://www.ebay.com/p/17062924371) | `en:sv03.5-199`, 199/165 | Retake; no best match | Card region approximately 96 pixels wide; insufficient verification |
| [CGC Professor Oak](../datasets/review/grading-fresh100-20261002/frozen-photos/fresh100_135116047131.jpg) · [source](https://www.ebay.com/itm/135116047131) | `ja:CLF-026`, 026/032 | Retake; no best match | Lower card is cut off |
| [CGC Shaymin V](../datasets/review/grading-fresh100-20261002/frozen-photos/fresh100_326075712447.jpg) · [source](https://www.ebay.com/itm/326075712447) | `en:swsh9-013`, 013/172 | Retake; no best match | Card region approximately 146 pixels wide; label also incomplete |
| [CGC Gardevoir](../datasets/review/grading-fresh100-20261002/frozen-photos/fresh100_407246892266.jpg) · [source](https://www.ebay.com/itm/407246892266) | Japanese ADV Expansion Pack 029/055 (2003) | Retake; catalogue truth unbound | Missing catalogue row; correctly read CGC 7.5 is separate from card matching |
| [TAG Eevee ex](../datasets/review/grading-fresh100-20261002/frozen-photos/freshextra_0_70889495.jpg) · [source](https://www.ebay.com/p/4074368147) | `en:sv08.5-075`, 075/131 | `en:PPS7-PRE-075`; `printing_ambiguous` | Wrong top reprint; correct base printing in alternatives |
| [AGS Gyarados](../datasets/review/grading-fresh100-20261002/frozen-photos/fresh100_205148259527.jpg) · [source](https://www.ebay.com/itm/205148259527) | `en:CLB-007`, 007/034 | `en:hgss1-4`; `printing_ambiguous` | Wrong top reprint; correct kit printing in alternatives; visible footer misread by OCR |

## Six new incomplete slab labels

| Original photo | Expected company / grade | Returned company / grade | Pending evidence |
| --- | --- | --- | --- |
| [Charizard ex](../datasets/review/grading-fresh100-20261002/frozen-photos/freshimg_0_1212241946.jpg) · [source](https://www.ebay.com/p/17062924371) | PSA / 8 | null / 8 | Issuer |
| [Mew ex](../datasets/review/grading-fresh100-20261002/frozen-photos/freshimg_1_113190404.jpg) · [source](https://www.ebay.ca/p/22065243991) | Beckett / 9 | null / 9 | Issuer |
| [Shaymin V](../datasets/review/grading-fresh100-20261002/frozen-photos/fresh100_326075712447.jpg) · [source](https://www.ebay.com/itm/326075712447) | CGC / 10 | null / null | Issuer and grade |
| [Lucario & Melmetal GX](../datasets/review/grading-fresh100-20261002/frozen-photos/fresh100_377526701873.jpg) · [source](https://www.ebay.com/itm/377526701873) | TAG / 10 | null / null | Issuer and grade; card artwork match is recovered |
| [Eevee](../datasets/review/grading-fresh100-20261002/frozen-photos/fresh100_205408031074.jpg) · [source](https://www.ebay.com/itm/205408031074) | ACE / 9 | null / null | Issuer and grade |
| [Dark Charizard](../datasets/review/grading-fresh100-20261002/frozen-photos/fresh100_227337115305.jpg) · [source](https://www.ebay.com/itm/227337115305) | ACE / 8 | null / 8 | Issuer |

## Eight original incomplete slab labels

The unchanged eight-case queue, original photos, sources, expected values, returned fields and warnings are in the [original v3.2 label report](grading-label100-v32-results-20261002.md#incomplete-labels-for-manual-review). These remain pending even though no wrong fields are returned.

## Safe next work

- Obtain closer, straight, glare-free card/label captures for small or truncated regions. Retain the existing low-resolution originals as regression controls.
- Investigate collector-footer OCR using independently labelled reprint pairs, including Gyarados's visible 007/034 footer. Do not silently prefer a printing by popularity or by case ID.
- Ingest missing historical Japanese sets using independently sourced catalogue references, then rerun the still-frozen Gardevoir photo. Do not use the test image as its reference.
- Validate any additional issuer/grade recognizer on a broad untouched label set plus raw negatives and latency controls before enabling it. The larger-model ablation is diagnostic, not a deployed recovery.

The [accuracy report](card-and-slab-accuracy-v32-20261002.md) links machine-readable accepted results and documents all denominators and limitations.
