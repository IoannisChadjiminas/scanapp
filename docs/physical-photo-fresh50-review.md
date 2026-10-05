# Fresh 50-photo holdout — 2 October 2026

The previous 69-photo regression result did **not** generalize unchanged to this new sample. The current JSON returned the correct first match in **39/50 (78%)**, and the correct printing somewhere in the best match or alternatives in **40/50 (80%)**. All 50 selected photos, including every failure, remain in these denominators.

## What was tested

50 fresh downloaded internet listing photos, independently visually labelled before scanner inference. Eleven printing identities, none present in the previous 69-photo test; 39 English and 11 Japanese photos. Layouts: 37 Pokémon full-art/illustration cards, 8 trainer full-art cards and 5 standard-frame Pikachu cards. Conditions include sleeves, top-loaders, stands, hands, one slab, glare, perspective and varied backgrounds. No synthetic crop positives or catalogue reference controls are counted here.

The sample is a deliberately selected convenience holdout, **not** random population sampling or independently captured phone-camera testing. Several photos share a card identity, and four photos have repeated eBay category-page sources with different image assets. Authenticity, physical capture origin, editing, finish and model-pretraining overlap are not authenticated. Finish was not labelled or evaluated.

79 candidates were downloaded and visually inspected; duplicate photos, a previously tested Espeon identity, a near-duplicate Japanese Gardevoir view and an apparently digital product image were excluded before inference. Eligible extras were omitted to freeze a 50-photo identity mix, not on the basis of recognition success. Labels were checked against visible names, collector numbers and language, rather than trusting search descriptions; two misleading search labels were corrected before inference. The selected photos have no exact-byte overlap with earlier downloaded photos or artwork reference hashes; a whole-image 256-bit difference-hash check and manual contact-sheet review found no selected near-duplicate flags. This is not an exhaustive proof against transformed/cropped asset reuse.

## Results: actual returned JSON

| Measure | Result |
| --- | --- |
| Correct `best_match` / all photos | 39/50 — 78% |
| Correct in `best_match` or `alternatives` | 40/50 — 80% |
| Wrong best match, requiring review | 8/50 |
| No best match / retake | 3/50 |
| Automatic `matched` | 10/50 |
| Wrong automatic `matched` | 0/10 |
| Internal first-ranked printing correct | 41/50 — 82% |

The internal ranking metric is higher because two correctly ranked Japanese Gardevoir photos were rejected and have **no displayed best match**. They are failures for the requested user-facing matching metric, not successes. Of the 47 displayed best matches, 39 were correct and 8 wrong. These percentages are measured test frequencies, **not** calibrated per-photo probabilities. A perfect 10/10 automatic subset is too small to imply perfect real-world precision.

Response statuses: 10 matched, 29 uncertain, 8 printing-ambiguous, 3 retake. Presentation states: 10 matched, 25 likely, 12 tentative, 3 unavailable. Blank and noise negative controls returned no suggestions; neither was automatically matched.

## Failure review

| Cases | Finding | Evidence / next correction |
| --- | --- | --- |
| `fresh_020`, `021`, `022`, `024`–`028` (8 Mewtwo VSTAR GG44/GG70 photos) | Correct card absent from both retrieval indexes; 7 wrong tentative best matches and 1 retake. | Read-only catalogue audit: `en:swsh12.5gg-GG44` has `image_path=null`, zero full-vector rows, and no artwork vectors. It is the only GG44 catalogue row. The normal OCR path did not supply a useful collector hit, so metadata did not recover it. Add a verified reference asset and vectors in a separate change; do not lower thresholds to compensate for missing coverage. |
| `fresh_018` (Base Set Pikachu 58/102) | Best match chose Base Set 2 87; correct Base Set card remained in alternatives. | No usable collector reading (`FOLIO`). Shared-art printing ambiguity was retained. Improve visible bottom-number evidence without asserting an exact printing from artwork alone. |
| `fresh_070`, `073` (Japanese Gardevoir sv1S 101/078) | Correct internal lead, but retake; no displayed result. | Visual scores .8424/.8580. OCR supplied the stage label `2進化` as the name, causing a strong-name conflict and preventing framing rescue. `fresh_070` also read 101/078. Name-region/stage-label parsing needs correction and regression tests; missing artwork-index coverage is an additional limitation. |

English: 30/39 correct internal leaders; Japanese: 11/11 correct internal leaders but only 9/11 returned correctly. Those language results are small, identity-clustered samples, not broad language accuracy estimates.

For context only, removing the eight missing-index Mewtwo photos would leave 39/42 correct displayed best matches and 40/42 correct returned choices. **That filtered result is not the headline accuracy and does not replace the full 50-photo result.**

## Frozen paired comparison

Both sides used the same current code and thresholds. “Before” in the JSON means **artwork index disabled**, not the older deployed scanner. “After” means the same local scanner with the existing frozen artwork index enabled.

| Measure | Full-card only | Artwork-assisted |
| --- | --- | --- |
| Internal first correct | 41/50 | 41/50 |
| Correct printing returned by existing suggestion/review contract | 39/50 | 40/50 |
| Wrong automatic printing | 0 | 0 |
| Retakes | 4 | 3 |
| Median pipeline latency | 3.518 s | 4.030 s |
| Sample p95 pipeline latency | 7.143 s | 7.509 s |

The artwork stream recovered `fresh_046` (Alakazam held in a sleeve) into review choices. There were no returned-recall regressions. Only 37/50 truths were covered by this frozen artwork artifact. Timings are local offline pipeline timings, not app/server/network latency; sequential paired execution and caching limit causal latency comparisons.

The full snapshot had 37,755 rows; the artwork artifact contains 4,834 cards / 9,668 regions. Recognition code hashes exactly match the previous final 69-photo reports. No thresholds, mappings, catalogue rows or vectors were changed during or after this holdout run; no staging deployment or app rebuild occurred. Runtime catalogue/image/vector mounts were read-only and recognition ran network-isolated. New photos were never indexed. The fresh results are sealed as the baseline; any later fix/retest must be reported separately, and would turn this sample into regression data.

## Evidence

- [Frozen labels and source URLs](internet-photo-fresh50-sources.json), SHA256 `4bc9bb83dfd7f4290b57cdb75d1173acd89c5909585e47cd8410a85c3a3eb76a`.
- [Completed paired report](physical-photo-fresh50-final.json), including every case, model/index/code hashes, timings and negatives; OCR rules text removed.
- [Returned-JSON audit and all failures](physical-photo-fresh50-presentation-audit.json).
- Private, Git-ignored downloads/contact sheets and raw results: `datasets/review/fresh50-20261002/`. Third-party images are not committed or redistributed.
- Reproducible runner: `api/scripts/benchmark_artwork_pilot.py --photos-only --sources docs/internet-photo-fresh50-sources.json`, using the frozen `data/artwork-candidates/20261002-recovery/` artifact and read-only local volume. The preparation script intentionally refuses to overwrite the frozen manifest.
