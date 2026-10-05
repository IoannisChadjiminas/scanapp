# Cropped-card recognition: tested local proposal

Date: 2026-10-01. Status: implemented and tested locally; **not deployed**.
The current testing-only environment permits a clean response contract rather
than hiding printing ambiguity inside an ordinary match. No database, mapping,
reference-image, existing-vector or decision-threshold updates were made in the
original crop-safety work. A later opt-in, separate artwork retrieval pilot and
physical-photo audit are documented in [artwork-pilot-results.md](artwork-pilot-results.md).

## Implemented behavior

- Missing or unknown-confidence OCR contributes neutral evidence. Known OCR
  matches and conflicts have confidence-scaled influence; gameplay numbers are
  not promoted into collector-number proof.
- `printing_ambiguous` is separate from ordinary `uncertain`, and from the
  Normal/Holo/Cardmarket finish choice. Different printings keep distinct IDs.
- A bounded reference-image cache expands same-name, same-language review
  choices beyond the vector shortlist. Reference correlation adds tentative
  choices; it does not certify an authoritative artwork family.
- A bounded SIFT/RANSAC artwork-only verification fallback can recover a crop
  from the existing retrieval shortlist. It excludes common borders/text,
  requires distributed inliers and non-reflected geometry, and never upgrades
  a rescued candidate to an automatic single-printing match.
- Shared printed numbers, conflicting reliable OCR, and uninspected reference
  siblings preserve ambiguity. A uniquely matching strong structured collector
  identifier can remove this extra ambiguity block, but does not itself force
  the overall result to `matched`.
- Unverified atypically framed crops return a retake without a visible guessed
  printing. No-match, retake and failed scans also hide guesses in history.
- Printing review, evidence and local-verification diagnostics use existing
  scan JSON storage; no operational SQL schema migration is required.

## API, Flutter and web contract

`printing_review` contains tentative `plausible_printings`, an explicit grouping
basis, guidance and reference-coverage information. It does not invent match
probabilities or claim that the entire real-world catalogue is complete.
`reference_coverage_complete` only describes the known same-name reference
rows inspected in this snapshot, bounded at 512 rows per group.

Both clients require the user to select the printing, then load the actual
card-detail endpoint to obtain its identity-filtered finish choices. Finish
selection is required when there are multiple choices. Prices and Cardmarket
links are not shown for an unselected ambiguous printing. The first suggestion
is explicitly unconfirmed, not a proven set.

Confirmation sends the chosen catalogue ID, chosen finish URL and
`printing_selected: true`. The API requires an offered or previously manually
confirmed printing, an existing catalogue row and a validated finish URL.
A finish cannot silently switch the selection to a different set/number/language.
This guard also rejects unoffered URLs with an editable local catalogue.
History and Flutter portfolio saving preserve the selected printing and URL.

## Verification

- Python suite: **277 passed, 1 skipped**; one existing Starlette deprecation
  warning. The suite includes real API card-detail → printing/finish confirmation
  → session-history tests, missing selection rejection, wrong URL rejection and
  retake/no-match/failed confirmation guards with manual-correction escape paths.
- Flutter suite: **173 passed**; `flutter analyze` reports no issues.
- Native simulator integration: printing → Holo → confirmation → batch portfolio
  save passed. This uses isolated fake transport/preferences and tests the UI
  contract, not real recognition or live staging. Evidence is in PokeSingle's
  `docs/printing-review-native.json`.
- Browser suite: **4 passed**, desktop Chromium and mobile Chrome, including a
  failed metadata read/retry, disabled confirmation before printing and finish,
  no premature price/job calls, acknowledgement payload and selected history URL.
  These are mocked API contract tests, not live recognition tests.
- TypeScript check and production web build pass. Changed standalone UI/type/API
  files pass targeted lint. Full lint still finds a pre-existing
  `react-hooks/set-state-in-effect` error in the language-storage effect in
  `scanner-app.tsx`; this work does not suppress it.
- Existing browser shell expectation was updated for the current page heading.
  Playwright now uses `localhost`, which Next trusts for development resources;
  `127.0.0.1` had blocked hydration and invalidated interactive tests.

## Offline crop audit

Results: `docs/crop-printing-benchmark.json`; runner:
`api/scripts/benchmark_printing_crops.py`.

The runner uses the existing local SQLite/reference/vector Docker volume
read-only, network disabled, and in-memory result storage. It does **not** query
or mutate PlanetScale or live staging. Only RapidOCR's unused visualization-font
download setup is disabled; recognition models and OCR remain unchanged.

Five reference cards (Base Pikachu, 30th Pikachu, Prize Pack Bibarel, English
Fuecoco, Japanese Victini) each have six conditions: full, art-only, top half,
bottom half, partial crop, and central patch. Two negatives are blank and noise.
Energy cards are not negatives: they are valid catalogue cards.

| Result | Baseline | Proposed |
| --- | ---: | ---: |
| Correct printing present in returned choices, 30 positive cases | 10 | 19 |
| Automatic single-printing claims | — | 1, correct |
| False automatic single-printing claims, 32 total probes | — | 0 observed |
| Printing-review results | — | 11 |

There is **one intentional recall regression**: the Base Pikachu partial crop
was previously an uncertain correct guess, but now requests a retake because
local geometry did not verify it. This is not a claim of universal improvement.
Most bottom-only and tiny central patches remain unresolved. 30th Pikachu's
full, art-only and top-half cases include its correct printing in review choices;
its partial crop still requires a retake. Artwork-only Fuecoco remains a miss.

These are synthetic crops of only five source references, including references
used by retrieval, with language explicitly locked to the fixture language.
They do not establish real-camera accuracy, language auto-detection accuracy,
a zero-error guarantee, calibrated probabilities, or a production precision
percentage. Local verification reached about 385 ms, and the cold reference
review reached about 638 ms on this machine; no sub-100-ms promise is made.

## Remaining architecture work

This is a safety foundation, not the complete dual-index architecture. The
subsequent local [artwork pilot](artwork-pilot-results.md) recovers cropped
Fuecoco, but does not yet provide full-catalogue or representative phone accuracy.
The conventional illustration ROI does not certify every full-art/modern layout.
SIFT can only verify candidates that were retrieved; it cannot recover an absent
Fuecoco candidate. The next retrieval improvement is a versioned artwork-only
index searched alongside the full-card index, with measured union recall and
layout-aware reference crops. Set stamps, set symbols and copyright-region proof
are not automatically verified by this implementation.

Before calibrating thresholds, add an independently labelled real-phone holdout
with repeated artwork, alternate finishes, Japanese/English auto-detection,
glare, sleeves, crop/perspective, full-art and valid energy/trainer cards.
Report false specificity and abstention separately from candidate recall.

## Proposed rollout: STAGING-CROP-009 (approval required)

Target: Dokploy `scanapp-scanapp-z1mwj4` at `staging-scan.auctaro.com`, source
`/etc/dokploy/compose/scanapp-scanapp-z1mwj4/code`; API and web only. User reports
there are no external clients and no production service. PlanetScale target
`pokesingle/pokesingle-db/main`, schema `pokesingle_import_20261001`, remains
**read-only** despite its production branch label. Scraper stays unchanged.

Read-only preflight confirmed API `20e7f885389d` healthy, web `3dfcfe247c40`,
scraper `66b2a00e20b3`, and public health `ready: true` with the PlanetScale backend.
Recheck IDs/source before execution; stop if they drift.

Execution proposal:

1. Preserve the current API and web image IDs with rollback tags and archive
   the current source/compose file in a new mode-0700 rollback directory. Compare
   a bounded tested source manifest before transferring changes. Preserve all
   earlier 006–008 fixes; do not push Git and trigger an all-service deployment.
2. Transfer only the reviewed API/web source changes. No catalogue, vector,
   secret, environment, dependency or threshold edits.
3. In the source directory, use:

   ```sh
   docker compose -p scanapp-scanapp-z1mwj4 -f compose.dokploy.yaml config --quiet
   docker compose -p scanapp-scanapp-z1mwj4 -f compose.dokploy.yaml build api web
   docker compose -p scanapp-scanapp-z1mwj4 -f compose.dokploy.yaml up -d --no-deps api web
   ```

4. Verify readiness and actual `printing_ambiguous` behavior, card-detail finish
   metadata, rejection of unselected/wrong-printing URLs and valid Normal/Holo
   feedback/history. Use an isolated test session; smoke-test the built web UI.
   Monitor startup/cold-cache latency, scan logs and container health.
5. Use a rebuilt Flutter testing app for the new contract. The current physical
   device binary has not been updated by this local work.

Availability: a brief testing-service interruption during container replacement.
Data: no PlanetScale writes; smoke tests create isolated operational scan records.
Security: no new roles, secrets, network settings or dependencies. New behavior
requires explicit manual acknowledgement, not elevated privileges.

Rollback: restore the archived API/web source and retag preserved images to their
original compose image names, then run the same API/web-only `up -d --no-deps`.
Recheck health and retain rollback artifacts. No database restore is necessary.
Existing review JSON records may remain; do not delete scans to roll back code.

The PlanetScale change-gates-and-approval-contract skill requires a named rollout
approval. No rollout or database mutation has been executed in this work.
