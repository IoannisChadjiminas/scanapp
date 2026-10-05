# Card and slab recognition — holder review v15

Local validation, 2 October 2026. Ranking version: `rank-v15-holder-printing-review`; grading version in this full-pipeline run: `slab-label-ocr-v3.2`. This is a completed **tuned regression**, not a new untouched accuracy test or a staging deployment.

## Measured card results

| Metric | Accepted v3.2 baseline | Holder review v15 |
| --- | ---: | ---: |
| Original photos retained | 100 | 100 |
| Scorable printing identities | 99 | 99 |
| Correct displayed best match | 94 | 96 |
| Wrong displayed best match | 2 | 0 |
| Scorable photos without a best match | 3 | 3 |
| Unscored catalogue gaps | 1 | 1 |
| Wrong automatic printing confirmations | 0 | 0 |
| Correct best match on older 50-photo regression | 50 | 50 |

Correct best-match coverage is **96/99 (97.0%) among scorable photos**, or **96/100 across the entire mixed batch**. Missing output is not a success. Raw cards are 50/50; slabs are 46/49 scorable, or 46/50 overall. The mixed batch contains 57 distinct scorable printings; the older batch contains 20. Repeated photos/identities must not be counted as 150 independent card types.

All 100 statuses are unchanged: 34 matched, 53 uncertain, 9 printing-ambiguous and 4 retakes. Both recovered best matches remain printing-ambiguous; they do not become automatic confirmations. No previously correct best match was lost. Full-pipeline label coverage remains 44/50 correct company-and-grade pairs, with zero wrong returned company/grade fields. The 50 raw negatives make zero slab/company/grade claims.

## Generic display-order change

A separately read holder header can reorder **existing, independently supported same-art printing choices**. It requires strong located OCR for the printed card name, a dated/numbered holder identity, a condition descriptor, issuer/certificate context, a literal `#` collector identifier, and a full expansion name or exact standalone catalogue set code. Reliable printed fractions must agree. Multiple matching numbers or candidate set identities abstain.

The change creates no catalogue rows, URLs or artwork candidates. It cannot translate a Japanese card name, rescue an unsupported identity, bypass a retake, infer foil/edition, supply a grade, or raise printing certainty. Displayed suggestions, best match, alternatives, saved ranking and confidence candidate ID stay consistent. Probabilities remain uncalibrated/null and confirmation remains required.

| Recovered photo | Previously first | Now first | Status |
| --- | --- | --- | --- |
| [TAG Eevee ex](../datasets/review/grading-fresh100-20261002/frozen-photos/freshextra_0_70889495.jpg) | `en:PPS7-PRE-075` | `en:sv08.5-075` | `printing_ambiguous` |
| [AGS Gyarados](../datasets/review/grading-fresh100-20261002/frozen-photos/fresh100_205148259527.jpg) | `en:hgss1-4` | `en:CLB-007` | `printing_ambiguous` |

## Pending card cases

| Photo | Printing identity | Issue |
| --- | --- | --- |
| [Charizard ex](../datasets/review/grading-fresh100-20261002/frozen-photos/freshimg_0_1212241946.jpg) | `en:sv03.5-199` | Approximately 96-pixel-wide card; retrieval is not sufficiently verified |
| [Professor Oak](../datasets/review/grading-fresh100-20261002/frozen-photos/fresh100_135116047131.jpg) | `ja:CLF-026` | Lower card truncated; holder text contaminates the proposed card region |
| [Shaymin V](../datasets/review/grading-fresh100-20261002/frozen-photos/fresh100_326075712447.jpg) | `en:swsh9-013` | Approximately 146-pixel-wide card; exact reprint unsupported |
| [Gardevoir](../datasets/review/grading-fresh100-20261002/frozen-photos/fresh100_407246892266.jpg) | Japanese ADV Expansion Pack 029/055 | Catalogue row absent; source found but not imported/indexed |

Gardevoir's independently downloaded [Pooka reference](https://pooka.app/card/ja-adv-expansion-pack-29/Gardevoir) matches the illustration, Japanese title, HP, illustrator and number. It is **not an official Pokémon-hosted image**. Its first-edition stamp differs from the test copy; edition/finish must remain separately unconfirmed. [Local provenance and checksum](../data/catalogue-gaps/20261002-adv1/reference-review.json) preserve this distinction. Eleven existing ADV set rows use provider aliases; whole-set/alias review is pending before any catalogue import. No test photo was used as an embedding reference.

The [previous manual-review queue](card-and-slab-manual-review-v32-20261002.md) is historical. Its Eevee and Gyarados card-ranking issues are now resolved by this regression; the six fresh label gaps remain pending. A separately versioned label-crop validation, if accepted, does not retroactively change the grading version of this card run.

## Evidence and limitations

- [Complete 100-photo responses, audited printing truth and scores](card-slab-holder-v15-results-20261002.json)
- [Full-pipeline grading scores](card-slab-holder-v15-grading-results-20261002.json)
- [Full app/logo code snapshot, stable throughout the run](card-slab-holder-v15-code-20261002.json)
- [Older 50-photo paired regression](physical-photo-holdout4-holder-v15-20261002.json) and [displayed-best audit](physical-photo-holdout4-holder-v15-audit-20261002.json)
- [Original v3.2 results](card-and-slab-accuracy-v32-20261002.md)

Photo hashes and the frozen source/truth manifests were verified. The full 100-photo probe hashes every app Python module and logo asset before/after execution. The older runner hashes its explicit module list at completion, which does not include the new holder helper; it is supplementary regression evidence, not a separate complete-source freeze.

Internet seller photos are a convenience sample, now reused for tuning. Camera capture, staging HTTP, Flutter UX, population accuracy, authenticity, raw physical condition, foil/stamp/edition, certificate digits, subgrades and TAG scores are not independently scored. Zero observed mistakes does not establish zero future mistakes. No new unseen-photo accuracy claim is made.

Under concurrent local Docker load, the 100-photo total median was 7.60 seconds and sample p95 was 19.17 seconds; these are not staging latency measurements. The older regression's median was 7.65 seconds and p95 16.96 seconds. Thresholds, vectors, Cardmarket mappings, PlanetScale and deployed services were unchanged.
