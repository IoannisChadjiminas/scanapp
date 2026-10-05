# Generic missing-number and Japanese-footer fixes

Implemented locally and checked against three frozen 50-photo batches. No card
IDs, URLs, photo hashes or card-name exceptions were added to scanner logic.
No thresholds, vectors, mappings, database records or deployed services changed.

## Changes

1. **Bounded exact-title retrieval when numbers are missing.** A title read with
   confidence at least 0.85 and known language proposes all indexed matching
   title printings, up to 32. More than 32 means abstain, not silent truncation.
   Confident explicit collector evidence disables this fallback. Newly retrieved
   title-only candidates must pass existing local geometric verification before
   presentation; they remain review-only and cannot automatically confirm a
   printing. Existing name, language and collector contradiction guards remain.
2. **Footer text is not title evidence.** The Japanese printed supporter
   instruction is excluded from name selection. If the actual title region has
   no usable name, arbitrary footer lines no longer populate `name_text`.
3. **Contextual Japanese set-code parsing.** When a numeric collector fraction
   is followed by a Japanese rarity token, an isolated `SV` plus one or two
   digits is treated as a set code, not another collector. Without that footer
   context, legitimate English shiny-vault `SV` collectors are preserved.

Versions: `rank-v11-bounded-title-geometry-review` and
`rapidocr-ppocrv6-small-regions-v4-supporter-rule`.

## The two original failures

Regigigas VSTAR GG55 was missing from the original visual/artwork shortlists.
Title retrieval now brings the English printing into verification. Its 71
artwork inliers support an `uncertain` best match despite a full-card similarity
of about 0.662; the missing collector is not manufactured or treated as proof.

Lacey 131/102 was already retrieved and locally verified. Deeper diagnostics
showed that excluding the supporter instruction alone did **not** recover it:
the footer parser also extracted set code `SV7` as a conflicting collector.
The contextual set-code fix removes that false contradiction. The card now
returns as `uncertain`, with 84 artwork inliers and collector 131/102, without
claiming that a missing title or finish was proven.

Both cards remain review-required. Neither fix lowers the confidence floor or
accepts every nearest neighbour.

## Verification

| Frozen batch | Before: correct best | After: correct best | Wrong automatic matches |
|---|---:|---:|---:|
| Third physical-photo batch | 48/50 | 50/50 | 0 |
| Second physical-photo batch | 50/50 | 50/50 | 0 |
| Earlier fresh physical-photo batch | 50/50 | 50/50 | 0 |

The same scanner code hashes were used in all three completed reruns. All
150 original labels and image checksums were retained. There were zero
best-match regressions and zero new automatic confirmations. The existing 39
automatic confirmations were correct; other best matches require review or
printing selection. Blank and noise controls returned no suggestions in all
three runs.

Unit/integration suite: 511 passing tests, one existing Starlette/AnyIO
deprecation warning. Fourteen initial new tests plus one footer-context test
cover weak/missing/unknown-language titles, excessive title-family size,
explicit-number vetoes, foreign-language/mechanic exclusions, indexed-only
retrieval, supporter rules, shiny-vault preservation and pipeline geometry/
automatic-confirmation guards.

Reports:

- `physical-photo-holdout3-generic-final.json`
- `physical-photo-holdout3-generic-audit.json`
- `physical-photo-holdout2-title-fix-final.json`
- `physical-photo-holdout2-title-fix-audit.json`
- `physical-photo-fresh50-title-fix-final.json`
- `physical-photo-fresh50-title-fix-audit.json`

The audits explicitly mark these as tuned regressions. The original untouched
third holdout remains 48/50 in `physical-photo-holdout3-presentation-audit.json`.
Post-fix 150/150 is not independent evidence of 100% real-world accuracy. These
are local offline API tests on convenience marketplace photos, not deployed
Flutter camera tests; authenticity and finish are not ground truth. A new
untouched holdout and physical-phone scans are still needed to measure
generalization. No staging deployment was performed in this request.
