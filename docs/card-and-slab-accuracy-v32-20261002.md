# Card and slab accuracy — accepted v3.2 results (2026-10-02)

The accepted local implementation returns the correct best printing for **94/100 new Internet photos**: **94/99 scorable photos (94.9%)**, with one missing-catalogue case still counted in the overall 100. All **50 raw-card photos** have a correct best match. Grading is a separate measure: company and overall numeric grade are both correct for **44/50 new slab photos (88%)** and **92/100 original label photos**. These are not 100% results.

## Measured outcomes

| Test | Untuned baseline | Accepted implementation | Remaining coverage/error |
| --- | ---: | ---: | --- |
| New mixed photos: correct best printing | 83/99 scorable | 94/99 scorable; 94/100 overall | 2 wrong suggested reprints, 3 scorable retakes, 1 catalogue gap |
| New mixed photos: correct printing in best or alternatives | 85/99 | 96/99 | 3 scorable retakes |
| New raw-card photos: correct best printing | — | 50/50 | No best-match misses in this sample |
| New slab photos: correct best printing | — | 44/49 scorable; 44/50 overall | Same six cases above |
| New slab labels: company and overall grade complete | 42/50 | 44/50 | 6 incomplete labels |
| Original slab labels: company and overall grade complete | 74/100 (v2) | 92/100 | 8 incomplete labels |
| Older 50-photo card regression: correct best printing | 50/50 (v13) | 50/50 | No best-match regressions |

The paired new-photo comparison recovered **11 previously incorrect/missing best matches**, with **zero previously correct best matches lost**. All 100 IDs remain in both runs. The original label comparison also retains every previously complete v3.1 label. Neither blank nor noise negative controls produces a best-match suggestion.

There are **zero wrong automatic card matches** in the scored new and older photo runs, and **zero wrong returned companies or overall grades** in the original and new slab samples. Missing fields remain null and are counted as incomplete, not correct. A correct best suggestion is not the same as an automatic confirmation: new-photo statuses are 34 `matched`, 53 `uncertain`, 9 `printing_ambiguous`, and 4 `retake`; finish still requires confirmation.

### New slab-label coverage by company

| Company | Photos | Company and grade both correct | Company correct | Grade correct |
| --- | ---: | ---: | ---: | ---: |
| PSA | 10 | 9 | 9 | 10 |
| Beckett | 8 | 7 | 7 | 8 |
| CGC | 8 | 7 | 7 | 7 |
| TAG | 8 | 7 | 7 | 7 |
| ACE | 7 | 5 | 5 | 6 |
| AGS | 9 | 9 | 9 | 9 |

Across these 50 slabs, grade alone is correct for 47/50 and company alone for 44/50. The 50 new raw-card photos have no false slab, company, or grade claims. Unknown grading status does not prove a card is ungraded.

## Generic changes that survived regression testing

- Grading OCR uses a bounded ten-pass recovery budget, whole-label orientation, rectified panels, and original-pixel numeral reads. Its stateless label path avoids a per-line rotation classifier turning a 9 into a 6. Descriptors do not manufacture numeric grades.
- Conflicting readings of the same localized certificate field only suppress that certificate. Separate certificate identities remain a hard conflict. This preserves independently observed grades without combining unrelated labels.
- Holder headers are explicitly distinguished from printed card titles. An English holder translation cannot veto Japanese card text or become proof of the card's exact printing.
- Card OCR handles inverted layout evidence, clipped layout headers, observed SVP codes, and narrowly defined Japanese series-prefix artefacts without rewriting arbitrary numbers.
- Bounded title-family retrieval preserves exact-name families before fuzzy alternatives. Weaker title evidence can propose geometry candidates, but those candidates need local verification and remain review-only.
- Legacy local matching and frame proposals are retained first. Denser keypoints and lower-photo views run only when the legacy matcher has no geometric proof; they do not become a competing printing vote.
- On partial photos with already ambiguous printing evidence, keypoint survival cannot override the better existing structural score within the same artwork family. The top suggestion remains a suggestion, not a confirmed printing.

Versions: `slab-label-ocr-v3.2`, `rank-v14-located-ocr-geometry-review`, and `rapidocr-ppocrv6-small-regions-v7-layout-orientation`. The embedding model, full-card/artwork vectors, Cardmarket mappings, and catalogue were not changed by these fixes.

## Remaining cases and rejected experiments

The [manual-review queue](card-and-slab-manual-review-v32-20261002.md) links the original photos and expected versus returned results. Three card misses have tiny or truncated card regions. Eevee ex and Gyarados return incorrect top reprints, but the correct printing is in their alternatives and both remain `printing_ambiguous`. Gyarados has a visible collector footer that OCR misreads: this is an unresolved OCR problem, not a claim that its printings are physically indistinguishable.

Japanese Gardevoir **029/055, ADV Expansion Pack (2003)** is absent from the inspected catalogue, not simply missing a vector. It remains an unscored coverage gap and a retake; its CGC 7.5 label is correctly read. A proper historical-set ingestion with independently sourced references is needed, not indexing this test photo.

Extra footer/rectified/sibling OCR retries and a smaller alternate recognizer did not produce reliable recovery. A larger recognizer on the 14 incomplete-label photos recovered two Beckett issuers but lost an existing CGC issuer and did not recover any missing overall grade. It was **not adopted**; its two recoveries are not included in the enabled result totals. See the [isolated model ablation](grading-server-recognizer-ablation-20261002.json). Dense frame proposals that regressed older scans were also rejected.

## Independence, truth and scope

The new batch is 50 raw cards and 50 slabs, with 57 distinct scorable printings across English and Japanese. Original Internet backgrounds, glare, sleeves, tilt and framing are retained. Exact asset/byte duplication was checked against earlier photos and reference assets; the recorded perceptual near-duplicate check flagged none. **No test photo was indexed, used as a reference, or turned into a grading-logo template.**

Photos and manual annotations were frozen before inference. One post-baseline truth audit corrected a mistaken catalogue binding for TAG Gardevoir TG05: Silver Tempest `en:swsh12tg-TG05`, not Astral Radiance. The original truth/report remain preserved, and both paired card totals use the same audited truth. A separate Mega Charizard X MEP023 annotation was corrected before card inference.

The untuned run is the new-photo baseline. Once its failures informed fixes, the accepted rerun became a **tuned regression**, not another unseen accuracy estimate. Marketplace convenience photos are not population-random phone scans; repeated identities, undiscovered duplicate copies and model pretraining overlap are limitations. New untouched physical-camera captures are still needed. Scores are not calibrated probabilities, and these samples do not establish authenticity, raw physical condition, finish, certificate-digit, subgrade, or TAG-score accuracy.

## Verification and deployment state

**705 API tests passed**, with one existing Starlette deprecation warning. Accepted runtime hashes match the working source for all four final reports (57 full-pipeline files, 14 grading files/assets, and 19 older-probe files as recorded). All 200 original/new frozen photo hashes were rechecked. All 100 new IDs were retained in the paired comparison; there were 11 gains and no losses.

Local mixed-pipeline latency under concurrent Docker load: median **7.63s**, p95 **17.63s**, maximum **30.45s**. Original isolated label latency: median 1.48s, p95 12.58s. These are offline pipeline measurements, **not staging HTTP or Flutter end-to-end latency**, and not sub-200ms performance.

Changes are local and tested. **No staging deployment or PlanetScale write occurred in this continuation.** Review and deployment remain separate from benchmark success.

## Evidence

- [Accepted 100-photo card results](grading-fresh100-fullscan-v32-accepted-results-20261002.json) and [runtime snapshot](grading-fresh100-fullscan-v32-accepted-code-20261002.json).
- [Untuned audited card baseline](grading-fresh100-fullscan-v31-audited-results-20261002.json).
- [Accepted new-photo grading results](grading-fresh100-v32-accepted-grading-results-20261002.json) and [untuned grading baseline](grading-fresh100-v31-baseline-results-20261002.json).
- [New frozen sources](grading-fresh100-frozen-sources-20261002.json), [grading truth](grading-fresh100-manual-truth-20261002.json), and [audited card truth](grading-fresh100-card-truth-audited-20261002.json).
- [Original accepted label results](grading-label100-v32-accepted-results-20261002.json), [label report](grading-label100-v32-results-20261002.md), and [runtime snapshot](grading-label100-v32-accepted-code-20261002.json).
- [Older accepted card regression](physical-photo-holdout4-v32-accepted-20261002.json) and [audit](physical-photo-holdout4-v32-accepted-audit-20261002.json).
- [API grading evidence reference](scan-grading-evidence.md). Coverage, correctness, and API confidence semantics are intentionally separate.
