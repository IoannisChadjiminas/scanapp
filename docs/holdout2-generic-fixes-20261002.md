# Generic fixes for the second photo holdout — 2026-10-02

## Changes

No card-ID-specific conditions, benchmark-specific crops, fabricated aliases, new reference vectors or similarity-threshold reductions were introduced.

1. **Separate titles from labels.** Japanese trainer/support categories, isolated mechanic text, isolated HP and grading collector labels are not card names. A weaker real title is no longer displaced by a confidently read generic header. Actual card titles containing numbers remain valid.
2. **Parse visible collector identifiers correctly.** Regulation/set text attached to a numeric fraction is removed only in recognized forms. Repeated TG/GG denominator namespaces are normalized while retaining the collector namespace. Copyright and illustrator lines and isolated set codes are not collector evidence. An explicit confident identifier takes precedence over incidental bare footer numbers; conflicting explicit observations remain preserved, and conflicting fractions prevent confirmation.
3. **Treat missing localization as unknown.** A localized catalogue row with only a Latin provider name cannot be compared directly with a CJK printed title. This does not create a translation or imply title agreement. It removes a false contradiction, forces otherwise eligible results to review, preserves known localized/foreign-language conflicts, and cannot bypass the visual score floor.
4. **Verify unresolved high-score neighbours geometrically.** When title evidence is weak and global visual neighbours are close, the existing bounded local artwork verifier can run even above the usual full-card floor. It retains OCR/language compatibility checks and review-only semantics. High similarity alone does not become printing certainty.

The existing one-retry boundary recovery now works for the slab case once genuine title/collector evidence reaches it. Its frame-generation logic and bounded retry count were not changed.

Files: `api/app/recognition/ocr.py`, `api/app/recognition/rank.py`, `api/app/recognition/pipeline.py`, `api/app/config.py`. Versions: `rank-v10-explicit-collector-localized-review`, `rapidocr-ppocrv6-small-regions-v3-title-labels`.

## Validation discipline

The six original failing photos all returned the correct displayed best match in the focused diagnostic. This subset is not an accuracy estimate. Full validation reruns both existing 50-photo batches and blank/noise controls on unchanged frozen labels and reference artifacts.

The initial partial full reruns were stopped after a safety test identified that the new unknown-localization rule needed to retain the visual eligibility floor. They are not included in final results. The corrected rule has a dedicated below-floor rejection regression test.

The completed `v3` regressions returned 99/100 correct best matches and 100/100 correct best-or-alternatives, with no wrong automatic confirmations. They exposed a new regression on a vintage reprint: its fraction was merged into the copyright line, which the new parser discarded wholesale. The generic correction preserves explicit fractions within otherwise excluded copyright/illustrator lines, without admitting incidental years. Two additional tests cover a shared copyright/fraction line and conflicting fractions on such a line. Intermediate `physical-photo-*-holdout2-fixes*`/`physical-photo-holdout2-generic-fixes*` artifacts without the `final` suffix describe that `v3` run. Final validation uses the `*-v4.jsonl` raw runs and `*-final*` report artifacts.

Tests: 30 new generic tests; full suite **496 passed**, one existing Starlette/AnyIO deprecation warning. The tests cover real-title preservation, malformed/mismatched namespaces, explicit conflicts, foreign-language/name conflicts, unknown localization and below-floor rejection.

## Final completed photo regressions

| Measure | Second holdout, now regression | Previous 50-photo regression |
| --- | ---: | ---: |
| Correct displayed best | 50/50 (was 44/50) | 50/50 (unchanged) |
| Correct best or alternatives | 50/50 | 50/50 |
| Wrong displayed best / no best | 0 / 0 | 0 / 0 |
| Automatic confirmations | 12 | 11 |
| Wrong automatic confirmations | 0/12 | 0/11 |
| Uncertain / printing ambiguous | 34 / 4 | 31 / 8 |

**100/100 displayed best matches were correct across the two regression batches**, with no best-match regressions from the preceding revisions. All six original failures were resolved, and the intermediate vintage-reprint regression was corrected. All selected photos remained in the reports; none was re-labelled or replaced. English, Japanese, full-art, trainer and standard-frame slices in the second batch are each complete with no remaining best-match failures.

The full-card-only ablation returned 49/50 best matches on each batch; the tested full-card + artwork/local-verification path returned 50/50. This does not establish that artwork fusion always helps; the initial independent holdout exposed its failures before these generic corrections.

Blank and noise controls returned zero suggestions and no automatic confirmations in both index paths of both runs. The 23 correct confirmations are finite-sample observations, not a guarantee of zero false confirmations. Remaining 77 matches require review/printing selection; finishes remain unconfirmed rather than inferred from static photos.

Both final runs have identical scanner/benchmark code hashes, verified against current source files. The artwork manifest equals the original holdout's manifest. Frozen source-label hashes and per-photo checksums were validated by the audit scripts. Similarity/quality thresholds and reference/index artifacts were unchanged.

Artifacts:

- `docs/physical-photo-holdout2-generic-fixes-final.json`
- `docs/physical-photo-holdout2-generic-fixes-final-audit.json`
- `docs/physical-photo-fresh50-holdout2-fixes-final.json`
- `docs/physical-photo-fresh50-holdout2-fixes-final-audit.json`

The original independent holdout report remains unchanged at 44/50 best matches. These 100/100 post-fix results are regression performance, not a fresh estimate of population accuracy. Further independent photos, particularly in-app phone captures, are needed to estimate generalization.

No deployment or database changes. Original catalogue/reference/index mounts are read-only, benchmark containers have no network, and test captures are not stored. The two complete photo regressions run concurrently; their latency measurements include host contention and are not comparable to the preceding isolated timing baseline.
