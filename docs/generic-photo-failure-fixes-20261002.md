# Generic photo recognition fixes — 2 October 2026

Scope: local implementation and read-only offline regression tests. No PlanetScale writes, catalogue/vector changes, staging deployment, or card-specific exceptions.

## Root causes and fixes

1. **Foreign-language results despite readable language evidence.** Incidental bare numbers in a misaligned footer caused `collector_conflict` and blocked the language-preference rule. Qualified OCR mode now permits the nearby, known-language candidate to lead when it has no strong name or structured-number contradiction. The existing 0.10 visual-distance bound remains. Incidental-number conflicts still prohibit automatic confirmation. Legacy unqualified ranking retains its previous guard.
2. **Evolution badges misclassified as names.** Japanese `1進化`, `2進化`, full-width equivalents, and `…から進化` instructions are skipped as title candidates. They remain in OCR traces and can still inform language detection.
3. **Footer omitted by a successful search window.** An inferred retrieval crop can improve visual similarity while cutting off a number visible in the upload. When a confident title has no explicit identifier, the pipeline consults the original input once. Only an agreeing confident title plus confident explicit collector identifiers can supplement evidence. Initial observations are never discarded. Supplemented results remain review-only.
4. **Small text in a large image.** A bounded overlapping-footer OCR pass is available when no explicit identifier was found. It accepts only confidence-qualified fractions or complete promotional codes, not incidental bare digits. A weak title can receive one interpolated, text-compatible higher-confidence retry. These retries do not lower any match threshold.
5. **Localized name with an unreadable Latin mechanic suffix.** Review-only framing rescue may accept an exact CJK title stem of at least four characters followed by one or two garbled CJK glyphs in place of a catalogue mechanic suffix. An explicit matching collector, known-language agreement, and the existing visual floor are also required. Readable conflicting mechanics (GX/ex/VMAX/VSTAR/V) are rejected. Ordinary automatic name matching is unchanged.

Versions: `rank-v9-qualified-language-review`, `rapidocr-ppocrv6-small-regions-v2`.

## Verification

API tests cover evolution labels, footer retries, weak/unrelated title retries, conflicting fractions, known-language preference, incompatible mechanic suffixes, and original-frame supplementation. The integration tests verify that unrelated original-frame names cannot contribute identifiers and supplemented matches are not automatically confirmed.

The final physical-photo run reuses the same sealed 50 photographs and unchanged recovered reference artifacts. Its baseline is the completed recovered-reference report, not the original missing-reference report. The original gold labels are unchanged; equivalent English provider IDs are accepted, but different sets/languages/collector numbers are not merged. Blank/noise negative controls are retained. This diagnostic regression sample is not a population accuracy estimate or an independent new holdout.

Final results are recorded in `physical-photo-fresh50-generic-fixes.json` and `physical-photo-fresh50-generic-presentation-audit.json`. Extra OCR is deliberately conditional and bounded.

## Completed results

| User-visible result | Recovered-reference baseline | Generic fixes |
| --- | ---: | ---: |
| Correct best match | 44/50 | 50/50 |
| Correct best match or alternative | 48/50 | 50/50 |
| Wrong best match | 4 | 0 |
| No best match / retake | 2 | 0 |
| Automatic confirmations | 12 | 12 |
| Wrong automatic confirmations | 0 | 0 |
| Median local latency | 4.11 s | 4.39 s |
| Sample P95 local latency | 4.73 s | 8.77 s |

All six target cases improved, with no previously correct best-match regressions. Final response statuses are 30 uncertain, 12 matched, and eight printing-ambiguous. The corrected cases therefore do not become unwarranted automatic confirmations. Mewtwo GG44 ranks first in all eight corresponding photos. Blank and random-noise controls continue to return zero suggestions and no automatic confirmation.

The 50 photos contain 11 distinct printing identities and include repeated subjects. The result is **100% on this regression sample**, not evidence of 100% real-world accuracy. More independent photos, localized suffix confusers, multi-card inputs, and camera/app tests remain valuable.

459 API tests passed with one pre-existing deprecation warning. Compilation and `git diff --check` passed. Recorded code hashes bind the completed run to the tested changes. Thresholds, source labels, official references, and vector artifacts are unchanged relative to the recovered-reference baseline. PlanetScale and staging remain untouched; publishing requires a coordinated code/reference rollout.

The long-tail latency increase comes from extra OCR for difficult framing/identifier cases. Before broad rollout, optimize the targeted original-input/footer passes and measure on the staging hardware without weakening the evidence gates.
