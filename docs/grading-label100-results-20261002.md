# Six-grader, 100-photo label baseline — 2 October 2026

The unchanged local API label reader returned the correct company and overall grade together on **26/100** new photos. It returned a correct company on **28/100** and a correct numeric grade on **42/100**. **No returned company or grade was wrong**, but **74/100 responses were incomplete**. This is not adequate six-company coverage yet; zero wrong reads must not be presented as 100% successful recognition.

| Grader | Photos | Company correct | Grade correct | Both correct | Incomplete | Wrong company/grade |
|---|---:|---:|---:|---:|---:|---:|
| PSA | 17 | 10 | 16 | 10 | 7 | 0 |
| Beckett/BGS | 16 | 0 | 1 | 0 | 16 | 0 |
| CGC | 17 | 6 | 5 | 5 | 12 | 0 |
| TAG | 17 | 9 | 8 | 8 | 9 | 0 |
| ACE | 16 | 0 | 6 | 0 | 16 | 0 |
| AGS | 17 | 3 | 6 | 3 | 14 | 0 |
| Total | 100 | 28 | 42 | 26 | 74 | 0 |

Missing means null output, not necessarily unreadable to a human. Forty-eight photos produced a positive slab detection. Forty-two returned `graded`; 58 remained `unknown`. None was falsely labelled `ungraded`. These are all slabs, so this batch alone does not estimate false positives on raw cards.

## Protocol and reproducibility

- Public seller photos were sourced from observed eBay image links. Full downloaded photos, including backgrounds, glare and framing, were used as inputs; review-sheet crops were not scanner inputs.
- Actual labels were visually reviewed and company/overall grade transcribed before inference. Listing titles were not numeric grade truth. The Jirachi listing, for example, said ACE 8 but showed a different label with a visible 7; it was not included.
- A repeated CGC certification `6150344092`, raw-card photos, and an unsupported PGC holder were excluded. Exactly 100 labels from the requested six issuers were selected, with 16–17 per company, grade diversity first and discovery order second. Grades span 1–10.
- Frozen photo hashes are unique and have zero exact image-hash/source-URL overlap with earlier downloaded diagnostic photos. This is not a guarantee against every transformed/near-duplicate internet image, nor proof of physical authenticity.
- No scanner source or truth annotation changed between freeze and scoring. The scorer verifies the frozen hashes of `grading.py`, `ocr.py`, `pipeline.py`, `schemas.py`, `config.py`, truth and every input photo.
- `CardOcr.read_grading` ran offline in the existing `scanapp-api:local` container with a read-only model volume. Only unused RapidOCR visualization-font downloading was disabled. No staging deployment, database writes or recognition threshold changes occurred.
- Existing grading tests: **46 passed** locally. Passing text/parser tests does not imply photo-reading coverage.
- Local label-component latency: median **1,638.73 ms**, p95 **2,592.05 ms**, maximum **2,878.54 ms**. This is not staging HTTP or end-to-end card matching latency.

Model SHA-256:

```
PP-OCRv6_det_small.onnx          090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f
PP-OCRv6_rec_small.onnx          6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884
ch_ppocr_mobile_v2.0_cls_mobile  e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c
```

## Evidence-backed compatibility gaps

1. **Exact brand normalization rejects real label typography.** `label100_225598065196` and `label100_389617271474` contain OCR `BECKETT®`, the correct visible overall `9.5`, and `GEM MINT`. The strict brand expression rejects the registered-trademark suffix. Most BGS labels also omit the word Pokémon in their year/set line, defeating the unbranded fallback. Normalize safe trademark punctuation; do not infer company from arbitrary card text.
2. **Descriptor/layout vocabulary is incomplete.** Old blue CGC label `label100_188157283019` produces `CGCUNIVERSAL GRADE`, `Gem Mint`, `9.5`; the existing aliases do not accept that historical brand heading. CGC `NEAR MINT+`, `NM/MINT`, `NM/MINT+` and AGS `MINT+`/`LEGENDARY` need company-aware, label-context handling. `label100_146677125573` clearly OCRs `AGS`, `LEGENDARY`, `10` and its certificate, but is rejected for missing a supported descriptor.
3. **Graphic logos are not textual logos.** ACE labels generally display a shield, not the word ACE; none of the 16 produces an issuer. `label100_397078152442` returns grade 10 correctly but company null. A validated visual logo/layout detector is needed, separate from card-name OCR; colour alone must not identify the issuer.
4. **Text/grade detection misses stylized digits.** CGC pristine gold digits and decorative ACE numbers fail detection or decode incorrectly and are rejected. `label100_800716677202` misses the gold 10 and reads its descriptor as `PISTNR`. ACE `label100_147552021925` produces `0` rather than 10, safely returning no grade. TAG `label100_168307084070` identifies TAG and EX MT but misses its visible grade 6. Generic label localization and bounded scale/contrast passes should be benchmarked, not a guessed grade from the descriptor.
5. **Framing and tiny logos remain important.** The current reader starts with the top 36% of the full photograph. Seller photos with large margins, tiny holders and reflections can place relevant content outside that strip or below legible scale. Rectify/localize the holder label before OCR and preserve the uncropped photo separately from card recognition.

Recommended next iteration: safe issuer/descriptor normalization, label localization, then independently validated graphic-logo detection. Re-run this batch as a regression set and reserve a fresh unseen batch for the next accuracy claim. Do not add case-specific certificates/card IDs or derive an unreadable grade from company scales/subgrades.

## Scope limits

This is a manually reviewed convenience sample of internet seller photos, not random customer camera data. It measures **company and overall numeric label grade**, not card-matching accuracy. Native condition descriptors, certification digit accuracy, subgrades and TAG scores were not independently quantified here. The scanner does not authenticate slabs or assess the physical condition of ungraded cards from this test.

## Artifacts

- Frozen sources and photo hashes: `docs/grading-label100-frozen-sources-20261002.json`
- Pre-inference manual truth: `docs/grading-label100-manual-truth-20261002.json`
- All 100 actual JSON responses, per-case truth comparisons, warnings and timings: `docs/grading-label100-baseline-20261002.json`
- Freeze/scoring tools: `api/scripts/freeze_grading_label100.py`, `api/scripts/score_grading_label100.py`

Run:

```sh
.venv/bin/python api/scripts/score_grading_label100.py --input /tmp/grading-label100-baseline-20261002.jsonl --output docs/grading-label100-baseline-20261002.json
```
