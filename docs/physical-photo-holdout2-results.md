# Fresh 50-photo holdout — 2026-10-02

The frozen full-card + artwork scanner returned the correct displayed best match for **44/50 photos (88%)**. The correct printing appeared in the best match or displayed alternatives for **45/50 (90%)**. There were two wrong suggestions and four photos without a best match. All 11 automatically confirmed matches were correct within this sample.

This is a new holdout result, not a claim of final population accuracy. The earlier 50-photo batch reached 50/50 after fixes and is now a regression set; its result must not be presented as independent validation.

## Scope and integrity

Selected and visually labelled 50 physical-card marketplace photos from a 98-image Internet pool, before inference. Reviewed all 17 contact sheets and checked ambiguous printed numbers on original images. Labels and scanner code stayed frozen throughout the run; no failure was removed or tuned away. No selected photo was added to either reference index.

- 36 English and 14 Japanese photos, covering 18 printing identities; 17 identities were new relative to the prior photo batches. Three new photos repeat the previously tested English Galarian Moltres printing.
- 28 Pokémon full-art, seven trainer full-art and 15 standard-frame photos. Conditions include foil reflections, sleeves, slabs, backgrounds and perspective tilt.
- All 50 photos passed exact-URL and byte-hash overlap checks; no near-duplicate dHash flags were found against prior photos or within this selection. This does not establish physical-copy or seller independence.
- 35 photos' truth printings are covered by the separate artwork subset; all 18 truth printings have catalogue image references.
- Frozen source-label SHA-256: `2f7149f32aaf768f04279c08f8d9d51dcd0ee943b2f7e9aebf95bca8693688aa`. Benchmark scanner code hashes equal the preceding generic-fix regression hashes.

Exact set, collector number and language are scored. English provider-prefix aliases of the same catalogue ID are accepted; other printings/languages are not. Only the response's displayed `best_match` and `alternatives` count, not an internal top-ranked or retrieved card.

## Results

| Measure | Full-card + artwork | Full-card only, same code/photos |
| --- | ---: | ---: |
| Correct displayed best | 44/50 | 45/50 |
| Correct best or alternatives | 45/50 | 46/50 |
| Wrong displayed best | 2 | 1 |
| No displayed best | 4 | 4 |
| Automatic confirmations | 11 | 11 |
| Wrong automatic confirmations | 0/11 | 0/11 |

The paired full-card-only comparison is an index-path ablation, not a comparison with older code. Artwork fusion regressed two Iono photos relative to full-card-only presentation. Its net result is worse on this batch; do not assume it always improves retrieval.

| Slice | Correct best | Correct best or alternatives |
| --- | ---: | ---: |
| English | 34/36 | 35/36 |
| Japanese | 10/14 | 10/14 |
| Pokémon full-art | 26/28 | 27/28 |
| Trainer full-art | 4/7 | 4/7 |
| Standard frame | 14/15 | 14/15 |

Response statuses: 11 matched, 30 uncertain, five printing-ambiguous, three retake, one no-match. Zero observed wrong confirmations among only 11 confirmations is not proof of a zero false-confirmation rate. Blank and noise controls produced no suggestions.

## Failure queue — all retained

| Photo | Truth | Displayed result | Read-only diagnostic evidence |
| --- | --- | --- | --- |
| holdout2_026 | Origin Forme Dialga VSTAR GG68 | Arceus VSTAR GG70, uncertain; Dialga in alternatives | Correct truth retrieved by both indices. Weak OCR title `STAR`; Dialga has higher raw visual similarity but lower combined score. Evidence weighting/ranking is implicated, not a missing reference. |
| holdout2_046 | Japanese Eevee ex 224/187 | No match | Correct truth internally ranked first and present in full-card shortlist, but rejected from presentation. Selected query only 209×291 pixels; OCR name garbled; truth absent from artwork subset. |
| holdout2_048 | Japanese Iono 096/071 | Retake | OCR chooses generic Support label `サボート`, despite reading 096/071. Correct truth retrieved by full-card stream. Full-card-only displayed Iono; fusion instead ranks another trainer. |
| holdout2_051 | Japanese Iono 096/071 | Pokémon Fan Club 071, uncertain | OCR chooses generic Trainers label `トレーナーズ`, despite reading 096/071. Correct truth retrieved by full-card stream but absent from displayed results after fusion. Full-card-only displayed Iono. |
| holdout2_057 | Japanese Pikachu 001/028 | Retake | OCR correctly reads `ピカチュウ` and 001/028; catalogue name is English `Pikachu`. Truth internally ranked first and retrieved by both indices. Name/collector conflict flags demonstrate an evidence/alias problem. |
| holdout2_062 | Cynthia's Ambition GG60 | Retake | Slab included in the selected query; OCR chooses slab text `#GG60` as the name. Correct printing absent from both shortlists. Framing/retrieval plus non-name OCR contamination require investigation. |

These observations are hypotheses for the next fixes, not claims that fixes have been implemented. No recognition changes or post-hoc replacement results were made in this holdout.

## Timing, mapping and limitations

Local offline recognition median **4.51 s**, sample P95 **11.79 s**, max **12.76 s**. OCR stage median 2.33 s. These are container measurements, not live staging, network or Flutter camera latency.

Ten of the 18 truth printing rows have no primary `cardmarket_url`; reference identity accuracy does not imply complete marketplace mapping. The audit lists these IDs. No URLs were invented or changed.

This convenience sample includes repeated identities and marketplace sources, not a random representative camera population. Authenticity, finish, seller/physical-copy independence and model-pretraining overlap are unverified. The photos were checked as physical-card photographs, but are not newly captured in-app photos. Foil/finish selection was not scored as ground truth. Slab labels can help or harm identification. Avoid combining this result with the tuned previous batch to advertise a single accuracy percentage.

Ran locally with network disabled and catalogue/reference/index mounts read-only. No PlanetScale writes, staging deployment, Flutter changes or public photo publication. Test suite: **466 passed**, one pre-existing deprecation warning; `git diff --check` passed.

## Reproducible artifacts

- `docs/internet-photo-holdout2-sources.json`: frozen labels, photo hashes and public source URLs.
- `docs/physical-photo-holdout2-final.json`: completed paired run with structured diagnostics and scanner/index hashes.
- `docs/physical-photo-holdout2-presentation-audit.json`: displayed-match scoring, all 50 cases, six-case failure queue and missing mapping IDs.
- `api/scripts/prepare_holdout2.py`, `api/scripts/audit_photo_holdout.py`: selection integrity and scoring checks.

Next work should address generic OCR label exclusion/name aliases, evidence-aware fusion and slab framing, preserve this batch as regression coverage, then measure a further untouched holdout and independently captured phone photos.
