# Slab label names and number+name candidates: the Lugia ex screenshot

Date: 2026-10-21. Branch `claude/pensive-roentgen-944694`. Nothing was pushed, deployed, or changed on staging (only read access: the staging scan JSON and a copy of the public reference card images).

## Result in one table

Frozen 155-photo panel plus the Lugia photo (156), replayed locally three times per arm against staging's catalogue export. Run 3 is the final code.

| Arm | Flags | Answer changes vs baseline (card or status) | Regressions | Fixed | CPU mean / p50 / p90 (ms) | Latency p50 / p90 (ms) |
|---|---|---|---|---|---|---|
| Baseline | none | (baseline vs baseline: 0 of 156 on every repeat) | - | - | 4,818 / 3,795 / 7,835 | 2,326 / 4,531 |
| Label filter | `OCR_LABEL_NAME_FILTER=true` | 1 (Lugia) | **0** | Lugia | 4,832 / 3,819 / 7,997 | 2,354 / 4,478 |
| Both | `OCR_LABEL_NAME_FILTER=true`, `TEXT_IDENTITY_CANDIDATES=true` | 1 (Lugia) | **0** | Lugia | 4,678 / 3,727 / 7,742 | 2,285 / 4,326 |

- Correct answers: 148/155 labelled photos for the baseline, 149/155 for both flag arms. The panel's other 155 photos give byte-identical card, status, printing, name, collector and grading fields in both flag arms (repo `compare_replay.py`: 1 exact-field change, the Lugia photo).
- Panel CPU is unchanged within noise. Two baseline runs differ by up to 1.7% in mean CPU; the arms are within ±3%.
- The Lugia photo itself, mean of 3 runs: baseline 7.3 s CPU / 4.3 s latency, `retake`, no suggestions. Label filter only: correct, but through the boundary retry, 8.8 s CPU / 4.9 s. Both flags: correct on the first pass, boundary retry skipped, **5.5 s CPU / 3.0 s latency** (25% less CPU and 31% less latency than the baseline; 37% and 40% less than the label filter alone).

**Proposal:** enable the two flags together, on staging first. Both arms showed 0 regressions on all 3 replays. Before production, see the caveats: this replay ran on ARM and engaged the new candidate path on only one panel photo.

## What went wrong on the Lugia photo

Staging scan `aa3ff732` (photo: phone screenshot of an auction page; slab label "10 PRISTINE / Pi" above the card; other cards' thumbnails below). The local baseline reproduces it exactly: same OCR lines, same wrong top-1 `ja:S6a-054` Grimmsnarl, `retake`.

1. **The label word became the name.** The selected frame (`loose_0`, nearly the whole screenshot) puts the browser bar and the slab label in the title strip: `十, X, 1/5, 10, Pi, PRISTINE`. Name selection skipped `10`, `1/5` and `Pi` but took `PRISTINE` (confidence 0.9999) as the card name.
2. **The name vetoed the right answer twice.**
   - Metadata retrieval needs a name that agrees with the number, so `ja:CLF-017` never became a candidate.
   - The boundary retry already *found and verified* the card: frame `line_7`, top-1 `ja:CLF-017`, 34 artwork inliers, status uncertain. It was then discarded, because the first pass's name "PRISTINE" is incompatible with ルギアex (`identity_compatible: false`).
3. **The evidence was there.** The footer strip read `017/032` (0.99) and `ルギア` (0.85, from a thumbnail of the same card). In the catalogue, a printed 017/032 plus a name containing ルギア is exactly one card, `ja:CLF-017`.
4. **Time.** On staging, 6.6 s of the 11.7 s went to the boundary retry (3.65 s), its proposals (1.42 s) and its selection (1.56 s). `grading_ms` 11.6 s ran in parallel; it was spent because the direct API call sent no `graded` hint. In the app, the phone's slab check decides that.

## What changed (all default off)

- `OCR_LABEL_NAME_FILTER` (`api/app/config.py`, wired to `CardOcr.label_name_filter` in `runtime.py`)
  - Name selection (`pick_name_line` / `pick_confident_name` in `api/app/recognition/ocr.py`, also used by the conflicting-title retry) never takes a grading-label field as the card name.
  - `grading_label_line` matches whole lines only:
    - grader brands (PSA, BGS/Beckett, CGC, TAG, ACE, AGS, plus Pi, PCA, SGC, CCC, Black/Gold Label);
    - condition words with an optional grade (PRISTINE, GEM MT 10, MINT 9, NM-MT, AUTHENTIC...);
    - dated label headers (`2023 POKEMON JP`) and `#17 HOLO` SKUs;
    - cert numbers (6–14 digits);
    - a label set line that carries a fraction (`Hidden Fates - SV59/SV94`).
  - TAG TEAM, ACE SPEC, Ace Trainer, Porygon2, ルギアex and similar stay titles.
  - Inside the card frame, the existing stage-badge rule still prefers the title after BASIC/たね.
- `TEXT_IDENTITY_CANDIDATES` (`api/app/recognition/text_identity.py`, used in `pipeline.py`)
  - **When it runs:** only when the visual top-1 is below the automatic floor (`THRESHOLD_MIN_VISUAL`, 0.78), so text never competes with a strong picture.
  - **Number evidence:** exactly one confident printed fraction (≥ 0.90). The catalogue match must have a known denominator: `printed_collector_number`, or the set number plus a known set total. A bare catalogue number with an unknown set total does not count. Without this rule, `ja:SM7b-017` ギラティナ qualified through a thumbnail's name.
  - **Name evidence:** a name read in any OCR line (≥ 0.80; HP digits and label fields removed). It matches the catalogue name or the English view title, by exact match, species stem (ルギア in ルギアex) or the existing fuzzy Latin match. Japanese reads only match Japanese names.
  - **Narrowing:** 1–3 cards. More than 3 abstain (`too_many_candidates`).
  - **Verification:** candidates go into the normal ranking as `retrieved_via: ocr_text_identity` and are checked first by the local SIFT artwork verifier. If the selected frame does not verify them (here it is the whole screenshot), each candidate's artwork is projected onto the upload with the existing `propose_frame` and verified there.
  - **Outcomes:**
    - A verified candidate is a review result (`uncertain`, `requires_confirmation`, never `matched`).
    - Unverified candidates on a scan that would otherwise be `retake`/`no_match` are returned as up to 3 suggestions needing confirmation (`text_identity_unverified`). The boundary retry still runs for them.
  - **Skipping the retry:** a verified single candidate leaves the scan `uncertain`, so the boundary retry and its frame proposals are skipped (step 3).
  - **Evidence:** `text_identity` (candidate ids, reason, outcome, aligned_verified) in the stored evidence; `text_identity_ms` timing; `versions.text_identity`.
  - **Intended use:** together with the label filter. Alone it would still lose Lugia, because the confident wrong name "PRISTINE" makes the verified card incompatible.
- HP as a tie-breaker was not built: the catalogue has no HP column. Above three candidates the path abstains instead.

## How this was measured

- **Machine and setup:** local M4 Pro. The same setup as `docs/experiments/ocr-grading-cpu-20261019.md`:
  - staging recognition flags;
  - the catalogue export of `PS-CATALOGUE-EN-JA-ENID2-20261019` (md5 identical to `auctaro-staging:/root/bench/export/catalog.sqlite`; 50,270 cards, 44,021 indexed);
  - artwork bundle `PS-CATALOGUE-EN-JA-SETH3-20261017`;
  - `ORT_INTRA_THREADS=2`, `DINO_INTRA_THREADS=2`.
- **Arms:** three servers in parallel (one per arm), `api/scripts/cpu_replay.py` with no `graded` hint. CPU is the server process tree's.
- **Reference images:** this replay, unlike the 10-19 local runs, had the reference card images (4.6 GB of public card art, 44,301 files, copied read-only from the staging data volume). The local catalogue's `image_path` was rewritten to that copy, so the local artwork verifier and `propose_frame` really run. The x86 reference-features bundle still cannot load on ARM, so features are extracted from the images on the fly.
  - As a result the local baseline is closer to staging than before: 148/155 correct versus 143 in the 10-19 local run and 150 on staging.
- **Panel:** `staging-reference027-20261003` cases (100 raw, 50 slab, 5 phone) plus the Lugia photo.
- **Raw outputs:** `data/latency/text-identity-20261021/` (gitignored, like the earlier latency data): `base*`, `label*`, `both*` JSONL for runs 1–3, and the compare JSON.
- **Run history:**
  - **Run 1** found one regression in both flag arms: `fresh100_177390016065`, a CGC slab, correct `en:sma-SV59` → retake. A first version of the filter preferred "the first title after the label's last field". It took the label's set line `Hidden Fates - SV59/SV94` as the name, which conflicts with Mewtwo GX. The fix: a label line carrying a fraction is a label field.
  - **Run 2:** 0 answer changes besides Lugia, but one printing-field change on `fresh100_277613285848`, a PSA slab. PSA prints the grade word mid-label (`2023 POKEMON SVP EN, #053, MEW ex, NM-MT, 151 ULTRA-PREMIUM COLL`), so "after the label" picked the product line on the original-upload re-read. The fix: the positional preference was removed; only label fields are skipped.
  - **Run 3:** clean (table above).
- **Where the new path ran (run 3):** the candidate path was evaluated on 12 of 156 photos (those below the visual floor) and proposed candidates on 1, the Lugia photo. Reasons on the other 11: 7 had no confident fraction, 4 had a number not in the catalogue. The label filter changed the selected name on 1 photo (Lugia).

## Regression fixture

- `api/tests/fixtures/text_identity_cases.jsonl`: the Lugia case with its recorded staging OCR hits, the photo's sha256, the expected card, and its true catalogue neighbourhood (all 160 Japanese cards numbered 17, public card data). `test_recorded_failures_name_and_narrow_to_the_right_card` replays it.
- `api/tests/test_text_identity.py` also pins the two panel slabs found by the replay as name-selection cases (CGC `fresh100_177390016065`, PSA `fresh100_277613285848`). The full pipeline is tested with faked OCR and verifier: flags off keep the retake; verified skips the boundary retry; unverified gives suggestions and still retries; a strong visual leader is never overridden.
- Photos stay out of git, as elsewhere in the repo. The Lugia photo is the owner's upload; a copy is on staging at `/root/bench/lugia-test.png`.
- A similar case not fixed: `fresh100_135116047131`, a CGC-slabbed Japanese Classic card (`ja:CLF-026` オーキドはかせ), stays `retake`. OCR read only the CGC label (`ACGC`, `CERTIFIED GUARANTY COMPANY`) and no collector number, so the number+name path has nothing to work with. `ACGC` (a garbled CGC logo) and `BECKETTO` are not caught by the whole-word label filter; fuzzy logo matching was not built.

## Caveats

- **ARM, not x86.** Local ARM numerics with on-the-fly reference features, not staging's x86 features bundle. Earlier work found 27 local-vs-staging answer differences without reference images. With them the local baseline is close to staging (148 vs 150 correct), but not identical. An x86 replay on staging was not run (out of scope: no staging changes).
- **Coverage is thin.** The candidate path engaged on one panel photo. Zero regressions shows it is quiet elsewhere, not that it is right on unseen slabs and screenshots. Unverified suggestions are the main new risk: a wrong card offered for confirmation where the app used to say retake. They need a confident fraction, a name read, and a catalogue match to at most 3 cards with a known denominator, and they are always `requires_confirmation`.
- **Single panel, three runs per arm.** CPU differences under ~3% are noise.
- **Lugia's latency saving was measured locally.** On staging the skipped boundary work was 6.6 s on that scan, but the added aligned verification (0.8–1.3 s locally) was not measured there.

## Recommendation

1. Enable `OCR_LABEL_NAME_FILTER=true` and `TEXT_IDENTITY_CANDIDATES=true` together on staging, then rescan the Lugia photo and a handful of slab screenshots to confirm on x86.
2. Watch `text_identity` outcomes in stored evidence for a week before production: how often `unverified` suggestions appear, and whether users confirm them.
3. Follow-ups not done here:
   - fuzzy grader-logo misreads (`ACGC`, `BECKETTO`) in the label filter;
   - an x86 replay with the staging features bundle;
   - HP in the catalogue, as the tie-breaker the brief asked for.
