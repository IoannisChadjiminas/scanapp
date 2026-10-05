# Physical-photo recognition recovery

Latest local follow-up: [boundary recovery results](physical-photo-boundary-results.md).
The measurements below remain the prior selected baseline.

2026-10-02. Implemented and verified locally; **not deployed to staging**.
PlanetScale, catalogue mappings, original images and existing full-card vectors
were not modified. The separate artwork index remains opt-in.

## Outcome

On the original 54 physical-photo examples, correct printing recall in the
returned results improved from **18/54 (33.3%) to 50/54 (92.6%)**. The correct
printing ranked first internally in **53/54 (98.1%)**, but internal guesses hidden
behind a retake are not counted as returned successes. No original returned-match
regressions occurred. Nineteen automatic claims were made, all correct in this run.

| Photo set | Photos / printing IDs | Correct printing returned | Correct internal rank 1 | Wrong automatic claims |
| --- | ---: | ---: | ---: | ---: |
| Original frozen sample, baseline | 54 / 15 | 18 | 37 | 0 of 8 claims |
| Original sample, selected code | 54 / 15 | 50 | 53 | 0 of 19 claims |
| New-identity holdout, first evaluation | 12 / 4 | 7 | 11 | 0 of 1 claim |
| Same 12 photos after fixes, now a regression set | 12 / 4 | 11 | 11 | 0 of 1 claim |
| Additional untouched Espeon/Moltres check, first evaluation | 3 / 2 | 3 | 3 | 0 of 2 claims |

The selected code returns 64/69 correct printings across the three sets, with
zero wrong automatic claims among 22 claims. **This is not a calibrated real-world
accuracy estimate or a 100% precision guarantee.** Photos repeat card identities,
come from convenience-selected internet listings, and may use grading-label OCR.
Authenticity, camera origin, editing, pretraining overlap and exact finish are not
established. Review choices are unconfirmed, not automatic printing identifications.

The original sample has 47 English and seven Japanese photos. All seven Japanese
photos were recalled; four English photos still request a retake. These counts do
not establish performance across every English or Japanese set.

Evidence: [selected 54-photo run](physical-photo-recovery-final.json),
[first 12-photo holdout](physical-photo-new-identity-holdout-v9.json),
[selected 12-photo regression](physical-photo-new-identity-final.json),
[first extra holdout](physical-photo-extra-fresh-v11.json), and
[selected extra regression](physical-photo-extra-final.json).

## Changes that helped

- Nested contour inspection can find a card inside a holder. Invalid geometry is
  rejected. Weak crops compare a bounded set of raw, inner-frame, loose-foreground,
  centered portrait and tall-holder hypotheses. Strong primary frames skip that
  extra inference. Inferred windows/holders cannot produce automatic confirmations.
- Conventional and broad full-art reference masks support local artwork matching.
  Distributed geometric inliers remain required; a repeated border or narrow text
  band is not artwork proof. Geometric rescue remains review-only.
- Strong name and fraction evidence can retrieve otherwise missing indexed cards
  from a bounded, read-only metadata index. It preserves printing alternatives,
  uses the existing visual scores, and does not turn OCR-only rescue into an
  automatic match. Weak, missing, unlocated or contradictory fields do not qualify.
- Set/language prefixes and Japanese rarity suffixes no longer invent collector
  conflicts. Genuine TG/GG/promo namespaces remain distinct. Known printed
  denominators take priority over incomplete catalogue aliases; missing catalogue
  identifiers remain unknown rather than contradictions.
- Language decisions use confidence-qualified OCR. Low-confidence invented foreign
  glyphs cannot override readable English fields. Known language/name/number
  conflicts veto automatic claims. Trainer/grading boilerplate is not a card name;
  weak trainer titles cannot hide a readable name. Empty OCR entries and their
  scores are removed together, preventing confidence misassignment.

Decision thresholds remain unchanged: full visual 0.78, OCR-assisted visual 0.70,
gap 0.04. The weaker floor used to choose a retrieval crop is not an acceptance
threshold. No model was retrained and no evaluation photo was indexed.

## Artwork artifact and reproducibility

The expanded artifact contains **4,834 cards / 9,668 regions**. Selection uses
generic English/Japanese rarity classes, the earlier pilot names and seeded
distractors, not benchmark truth IDs. Of 5,763 selected cards, 929 reference files
were unavailable and explicitly skipped. This is still a subset of the 37,755-row
full-card index, not complete catalogue coverage. It covers the truth in 52/54
original photos; the other two are recalled through the full-card stream.

The immutable artifact was preserved locally, outside Git, at:

`data/artwork-candidates/20261002-recovery/`

Manifest SHA-256:
`318246d5497120da562d547fa28e2e1496c7e2b1b6cca579c12d51b2e8c1ccd9`.

The loader validates model, base-vector/ID hashes, record hashes, preprocessing,
crop profiles and known catalogue IDs. An incompatible configured artifact fails
readiness rather than silently changing retrieval. No environment was switched
to this artifact.

Private evaluation inputs are preserved under
`datasets/review/physical-20261002/{photo54,identity12,extra3}/photos/`.
Both directories are Git-ignored; do not publish the photos or infer training
rights. Selected labels/source URLs are in `internet-photo-50-sources.json`,
`physical-photo-holdout-sources.json` and `physical-photo-extra-sources.json`.
Source examples include the [Espeon holder photo](https://www.ebay.com/itm/158304101999),
[second Espeon photo](https://www.ebay.com/itm/227466501313) and
[Moltres source gallery](https://www.ebay.com/p/5047827276).

The extra manifest initially had two Moltres URLs returning identical bytes.
Validation rejected it before any scan; the duplicate was excluded and is not
counted as another successful case. Downloads are checksum-checked, exact-byte
duplicates/reference overlaps rejected, and labels frozen before evaluation.
Near-duplicate/pretraining overlap is not ruled out.

Runners: `api/scripts/benchmark_artwork_pilot.py`,
`api/scripts/summarize_photo_benchmark.py` and
`api/scripts/summarize_crop_recovery.py`. Evaluations used network-isolated Docker
containers, read-only data/source/artifact mounts, an in-memory catalogue copy
with query-only enabled and an in-memory results DB. Only unused OCR drawing-font
setup was disabled. Reports retain model/artifact/source/label hashes and preserve
the original baseline. Failures and retakes stay in the denominator.

## Safety and performance checks

- **368 Python tests passed, one skipped**, with one existing Starlette warning.
  Command: `PYTHONPATH=api .venv/bin/python -m pytest -q -c api/pytest.ini api/tests scraper scripts/tests`.
- Thirty synthetic reference crops plus blank/noise controls produced zero false
  automatic printing claims. All five artwork-only fixtures recalled their correct
  printing as reviewable choices, with zero artwork-only automatic claims.
- Overall synthetic returned recall stays 19/30. Against the previous crop audit,
  there are three gains (both Pikachu partial crops and Fuecoco artwork-only) and
  three regressions (Fuecoco central patch; Japanese Victini top/partial crops).
  The latter abstain (one no-match, two retakes) rather than return unverified guesses. These remain
  open crop-retrieval weaknesses, not successes hidden by unchanged totals.
  Details: [crop recovery audit](crop-recognition-recovery-final.json).
- An early trial made two wrong automatic language/printing claims and was
  rejected. The subsequent language/identity guards closed those observed failures.
  Evidence is retained in `physical-photo-recovery-trial-v4.json`.
- Extra OCR frame/bottom-band retries did not improve returned recall beyond the
  inexpensive name-boilerplate fix, while sample P95 grew to 13.29 seconds. They
  were removed. The selected revision preserves 50/54 returned recall, with a
  4.29-second median and 4.99-second sample P95 (baseline 3.77/4.41 seconds). Offline
  latency is recorded in the selected report; shared-machine runs are not staging
  SLO measurements, and neither vector similarity nor timings are probabilities.

## Remaining review queue and next gate

| Photo ID | Expected card | Why it remains a retake |
| --- | --- | --- |
| `char_1` | English Charizard ex 199/165 | Readable-looking fraction remains below the qualified confidence floor; artwork geometry not verified. |
| `umbreon_2` | English Umbreon VMAX 215/203 | Glare/holder framing; name found but no reliable collector line or geometric verification. |
| `lugia_5` | English Lugia V 186/195 | Hand/sleeve framing; selected window loses the reliable bottom identifier and fails local verification. |
| `trainer2_3` | English Professor's Research 201/202 | Weak framing; name approximate, number missing from selected window, geometry unverified. |
| `holdb_7` | English Miriam 251/198 | Holder/text-panel selection; artwork/name/bottom line do not survive together in a verified frame. |

All four original retakes rank the correct printing internally. Showing that guess
as confirmed would inflate recall without proving the result. The next substantial
improvement should be a validated card-boundary detector/rectification model, tested
on independent app-camera photos, particularly these holder/glare cases and the
three synthetic crop regressions. Further tuning on these photos makes them
regression data, not fresh holdouts.

Before staging rollout: verify the staging artifact/model compatibility, preserve
rollback, verify client printing-review support and run live latency/concurrency
and printing/finish URL guards. Recognition success does not certify a Cardmarket
mapping, foil/finish, every printing in an artwork family, or catalogue metadata.
Existing catalogue-warning fields remain visible in the reports.
