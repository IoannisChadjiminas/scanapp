# How to improve remaining scan accuracy safely

Goal: maximize correct displayed card matches and complete slab-label extraction without inventing an exact printing, issuer, grade, finish or condition. Audience: PokeSingle developers validating the local scanner before staging deployment.

Assumptions: current regressions are tuning data; Internet references are not necessarily official or licensed for redistribution; PlanetScale mappings must follow the [listing-identity contract](/Users/ioannischadjiminas/StudioProjects/PokeSingle/docs/cardmarket-listing-mapping.md). Numeric grading evidence is separate from card identification. Production-population 100% is not established by a finite sample.

## 1. Assign every miss to one repair category

Keep the original photo and expected card/label fields frozen. Classify the failure as catalogue coverage, card framing, artwork retrieval, printing resolution, issuer localization, or literal grade recognition. A photo can have several failures. Preserve unknown fields as unknown.

Expected result: a review queue with actual missing/wrong fields, not one misleading combined accuracy percentage. Card best-match coverage, wrong best matches, wrong automatic confirmations, issuer coverage and grade coverage have separate denominators.

## 2. Fill catalogue gaps independently of the test photo

For a missing historical set, audit the full set and existing provider aliases. Verify language, number, expansion and artwork against independent catalogue/archive sources. Prefer official images when available; retain source URL, checksum, source type and print/edition differences. Never vectorize the benchmark photo as its own reference.

Build an isolated candidate catalogue and both full-card/artwork vector snapshots. Keep existing IDs, vectors and Cardmarket mappings unchanged. Validate FTS/name-search coverage, alias uniqueness, image endpoints and manifest consistency before publication. Verify Cardmarket listing identity separately; an unverified URL or different edition cannot be marked mapped/done.

Expected result: the previously missing printing becomes retrievable without changing the original test input or making an unsupported finish claim. Gardevoir's [pending reference](../data/catalogue-gaps/20261002-adv1/reference-review.json) is ready for this review, not already imported.

## 3. Fix framing and small-image failures before relaxing certainty

Evaluate partial-card/holder boundary proposals using original pixels. Separate holder labels from card titles and language evidence. Verify new crops against candidate artwork geometry. For a tiny or truncated photo, improve capture framing or request a closer photo; upscaling does not create missing evidence.

Expected result: better artwork recall on the same input without showing a confidently wrong printing. A safely supported artwork family can be presented as likely/ambiguous. Mere nearest-neighbour proximity cannot guarantee the correct card on arbitrary inputs.

## 4. Improve labels with localized, independently checked evidence

Preserve the successful legacy crop path. Additional original-pixel glyph proposals must require literal numeric OCR agreement and pass descriptor/subgrade/certificate conflict rules. Company recovery needs literal issuer text or independently supported logo geometry, not label colour, a fuzzy spelling guess, the recognized card, or a grade descriptor.

For unresolved issuer marks, collect separate training/development photos across graders and old/new labels; compare a localized issuer detector/recognizer against the current model. The prior larger recognizer and globally tightened grade crops caused regressions and were rejected. Keep a bounded OCR budget, one-call exit for clear labels and explicit failure diagnostics.

Expected result: company-and-grade coverage improves with no lost previously correct fields and no new raw-card slab claims. Certification digits, subgrades, TAG scores and raw physical condition require their own labelled evaluations; they are not covered by company/grade accuracy.

## 5. Run the frozen regressions, then a genuinely untouched sample

Before accepting each change, run all API tests, all original/fresh label cases, raw-card negatives, and card regressions. Compare each case, not only aggregate totals. Reject a new recovery that sacrifices an existing correct result. Record exact code/model/asset/catalogue hashes and latency.

After the architecture is frozen, collect another approximately 100 untouched photos across raw cards and slabs, English/Japanese, full arts, reprints, all six graders, glare, rotation and partial framing. Split development versus evaluation by duplicate asset and card/artwork family where practical. Annotate truth before inference and audit ambiguous bindings independently. Do not tune on this new holdout before its initial score is published.

Expected result: an honest unseen baseline. Then report any tuned rerun separately. Targets such as ≥99% correct best-match coverage and ≥99% company/grade coverage are acceptance goals, not promises or measured results. Include retakes/catalogue gaps in overall coverage; never count missing output as correct.

## 6. Validate staging and the app separately

Deploy only a tested candidate with a preserved rollback version. Verify staging image/vector/catalogue alignment, grading fields, saved session history, variant choices and image endpoints. Test real phone captures plus correct/wrong URL selections and retake guidance. Measure staging p95 latency and concurrent scans, rather than extrapolating local Docker timing.

Expected result: the tested evidence reaches the user consistently. A local benchmark alone is not proof of a deployed API, Flutter display, calibrated probability, authenticity, foil/edition recognition or physical condition assessment.

See the [v15 measured card regression](card-slab-holder-review-v15-20261002.md) and [API evidence reference](scan-grading-evidence.md) for current facts and response semantics.

The [v3.3 label validation](grading-v33-validation-20261002.md) records the accepted numeral recovery, rejected regression and remaining thirteen label cases.
