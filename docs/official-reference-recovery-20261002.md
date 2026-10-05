# Official reference recovery — 2 October 2026

Local candidate only. PlanetScale, staging, GitHub review HTML, and live scanner configuration have not been changed by this recovery.

## Recovered coverage

1,696 missing references were recovered and identity-verified from official Pokémon sources: 598 English and 1,098 Japanese. This includes all 70 Crown Zenith Galarian Gallery cards, including Mewtwo VSTAR GG44/GG70.

The discovery failures included special-set/promotional asset aliases, unpadded promotional filenames, a newer official asset directory, and a Japanese parser that confused the printed denominator with the set code. The parser now obtains the set code from the official regulation-logo metadata and rejects conflicting evidence.

English identities were verified through conservative OCR plus visual name/number review where OCR was insufficient. Japanese identities require exact official detail-page set, name, and collector-number agreement. Source URLs and image SHA-256 checksums are retained in the frozen selections. Five downloaded English images remain withheld: Gothitelle SVP211 and Morpeko V-UNION SWSH287–290, whose individual printed identifiers were not confidently readable.

The English/Japanese missing-image inventory still contains 3,148 pending cards: 565 English and 2,583 Japanese. This does not prove that their images are unavailable elsewhere. Chinese cards were inventoried but not searched in this pass.

## Candidate validation

Candidate directory: `data/image-recovery/20261002-official/verified-final-v5/`.

- Full-card pad and square indexes each contain 39,451 cards (37,755 existing plus 1,696 recovered).
- Artwork index contains 6,530 cards / 13,060 regions. It does not cover the entire catalogue.
- All existing full-card and artwork vectors are bitwise unchanged.
- Recovered image checksums, card identities, and existing Cardmarket URLs were validated. No Cardmarket URLs or finish mappings were added or changed; a previously absent URL remains absent.
- No card flagged as having an image is missing from the full-card candidate index.
- SQLite integrity check passed. The candidate was converted to DELETE journal mode for portable, read-only tests; this changes the file checksum, not the catalogue rows. The authoritative post-conversion checksum is in the artifact audit.
- API tests: 437 passed, one warning.

## Same 50-photo regression sample

These are real Internet camera photographs, not synthetic crops. The same previously tested photos were reused to measure the reference-recovery change; this is not a fresh holdout or a population accuracy estimate.

| User-visible result | Original references | Recovered references |
| --- | ---: | ---: |
| Correct best match | 39/50 (78%) | 44/50 (88%) |
| Correct best match or alternative | 40/50 (80%) | 48/50 (96%) |
| Wrong best match | 8 | 4 |
| No best match / retake | 3 | 2 |
| Wrong automatic confirmations | 0 | 0 |

No previously correct best match regressed. Blank and noise controls still returned no suggestions.

Mewtwo GG44 now appears in all eight photos' returned results; it is the best match in five and an alternative in three. All three remaining Mewtwo first-place errors retrieve the correct card in both full-card and artwork shortlists. Their selected Japanese candidates carry language-conflict evidence, while frame detection fails and OCR samples rules text instead of the intended card regions. Therefore these remaining errors are ranking/framing/OCR problems, not missing vectors. No thresholds or recognition-policy code was changed in this recovery.

Other remaining cases: one Pikachu printing ambiguity (correct Base Set alternative, Base Set 2 first) and two Japanese Gardevoir retakes caused by evolution-stage text being treated as the card name. These are retained as explicit failures, not counted as successful exact matches.

Reports: `physical-photo-fresh50-recovered-presentation-audit.json`, `physical-photo-fresh50-recovered-references.json`, and `official-reference-recovery-artifact-audit.json`. Full pending inventory and frozen selections remain under `data/image-recovery/20261002-official/`.

Next work is to correct those isolated framing/OCR/ranking failures with paired regression tests, then publish the validated catalogue/images/vectors together through a reversible staging migration. Do not advertise the local candidate as live.
