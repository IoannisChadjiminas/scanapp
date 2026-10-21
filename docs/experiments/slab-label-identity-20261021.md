# Slab label set line and number: the CGC Charmander 18a/147

Date: 2026-10-21. Branch `claude/slab-label-identity`, from `origin/main` at dd5170d (includes PR #56 and PR #57). Nothing was pushed or deployed. Staging was only read: the scan row and its recorded OCR.

Follows `docs/experiments/slab-text-identity-20261021.md` (the Lugia fix) and uses the same local replay setup.

## Result in one table

Frozen 155-photo panel plus the Lugia and Charmander photos (157). Two replays per arm; run 5 is the final code.

| Arm | Flags | Answer changes (card or status) vs baseline | Regressions | Fixed | CPU mean / p50 / p90 (ms) | Latency p50 / p90 (ms) |
|---|---|---|---|---|---|---|
| Baseline | none | (baseline vs baseline: 0 of 157) | - | - | 4,754 / 3,666 / 7,864 | 2,272 / 4,360 |
| PR #57 flags | `OCR_LABEL_NAME_FILTER`, `TEXT_IDENTITY_CANDIDATES` | 1 | **0** | Lugia | 4,761 / 3,724 / 7,933 | 2,258 / 4,278 |
| All three | + `SLAB_LABEL_IDENTITY` | 3 | **0** | Charmander, Lugia, `fresh100_135116047131` (ja:CLF-026) | 4,736 / 3,753 / 7,954 | 2,256 / 4,373 |

- Correct answers: baseline 148/156 labelled photos; PR #57 flags 149/156; all three flags 151/156.
- Panel CPU and latency are unchanged within noise. The two baseline runs differ by 0.9% in mean CPU.
- The label path proposed candidates on 6 photos, and every set was exactly the expected card. Three are the fixes. The other three were already correct and are unchanged: CGC `fresh100_177390016065` (SV59), TAG `fresh100_197768683572` (#233/091) and `fresh100_146365926690` (#132).
- Besides the answers, the only field that changes is `collector_text`, on 45 photos: the template-word fix (point 3). It is a display field. Both pipeline uses read it together with every OCR line, of which it is always one, so it cannot change a decision. The replay confirms no other change.

**Proposal:** enable `SLAB_LABEL_IDENTITY=true` together with the two PR #57 flags, on staging first. Both runs showed 0 regressions.

## The Charmander scan

Staging scan `b390124a` (2026-10-21T04:18Z, the real app): a Facebook screenshot of a CGC 8.5 slab.
- **Answer:** `uncertain`, top `en:bw10-53` Archen (visual 0.80). All of the visual top-6 were wrong.
- **OCR:** name "Charmander" (correct); collector_text "retreat" (wrong).
- **Time:** 13.8 s total. The first pass took 7.6 s, the boundary retry 4.5 s plus 0.8 s proposals and 0.8 s selection, OCR 4.1 s, and grading 2.9 s.

What the label said and the pipeline ignored: `Burning Shadows- 18a/147` (0.98) and `Cos. Holo - Charmander Sidekick Coll.`. The card is `en:sm3-18a`, with `printed_collector_number` "18a", in the image index.

Why the existing paths could not use it:
1. The number+name path (PR #57) reads only footer fractions (region `collector`). The label lines are region `holder_name`, and the staging footer read no number at all.
2. That path runs only below the automatic visual floor (0.78). Archen scored 0.80 on staging and 0.780 locally, so text was never consulted.
3. `parse_collector` drops letter suffixes, so 18a and 18 have the same key.

## What changed (default off)

- `SLAB_LABEL_IDENTITY` (`api/app/config.py`; requires `TEXT_IDENTITY_CANDIDATES`). New module `api/app/recognition/label_identity.py`.
  - **Label lines** are confident title-strip or holder lines, used only when a holder label was detected or a grading-label field is among them.
  - **Set line parsing**, per grader:
    - CGC: `<set> - 18a/147`.
    - PSA: a `2017 POKEMON SM BURNING SHADOWS` header, with `#18A` on its own line.
    - BGS/Beckett/ACE: `2017 Pokemon Sun & Moon Burning Shadows #18a` on one line.
    - CGC continues the set on its variant line (`Holo - Blastoise & Suicune ex Deck`), so all label lines together are also scored.
  - **Number keys** keep prefixes and suffixes: 018a → 18A, SV059 → SV59, TG01 → TG1, SWSH050 → SWSH50. The catalogue's `collector_number` or `printed_collector_number` must match exactly: 18a is not 18, TG01 is not 1. Two different numbers on one label abstain.
  - **Set match:** the share of the catalogue `set_name`'s words found on the label, with fuzzy matching for long words, or the whole-string similarity, at least 0.6. A label word equal to the set code (PSA's "SVP") is a full match.
  - **Language:** a label that names it ("Pokémon (2023) Japanese") restricts the language. Otherwise the scan's ranking languages apply.
  - **Tie-break:** the label's card name breaks ties inside a set. With no set match, the number plus the label's card name must agree.
  - **Bound:** 1–3 cards, otherwise abstain.
  - **Feeding the pipeline:** the result joins the PR #57 candidates (still at most 3). Verification is the same: local SIFT verification, then projection onto the upload. A verified single card is a review result (`uncertain`, `requires_confirmation`) and skips the boundary retry. Unverified cards become up to 3 suggestions needing confirmation, and the retry still runs.
  - **Near-threshold leaders:** with this flag, candidates are also tried when the visual leader sits at most 0.07 above the floor (below 0.85) and agrees with no name read on the card or its label. That covers Archen at 0.80 against "Charmander". If any read name agrees with the leader, text is not used (`visual_leader_supported`). A text candidate whose artwork verifies can take the top place from such a leader, as a review result. An unverified candidate replaces the leader only when the leader was itself unverified and not `matched`.
  - **The extra label read (CLF-026):** if a label is detected but no label number was read, and no other candidate exists, one OCR read of the upload's upper half looks for the label's set line. It takes about 0.4 s locally (`ocr_passes` scope `slab_label`). This recovers `fresh100_135116047131`, where card OCR read only the label header `ACGC / CERTIFIED GUARANTY COMPANY`. The label says `Trading Card Game Classic - 026/032` / `Holo - Blastoise & Suicune ex Deck` / `Pokémon (2023) Japanese`, which gives exactly `ja:CLF-026`. Its artwork is mostly out of frame, so it is returned as a single suggestion needing confirmation, not verified.
- **Template words** (under `OCR_LABEL_NAME_FILTER`, `pick_collector_text` in `ocr.py`):
  - A fraction still wins, as before.
  - Otherwise the fallback must be a short line holding a collector-shaped token, with no ©.
  - "retreat", "resistance", "weakness", rules text, copyright lines, ×2, -30 and HP are never `collector_text`. With no such line, `collector_text` is now `None`.
  - Examples from the panel: TG01/TG30, GG66/GG70, SWSH020 and 053 now appear instead of a copyright line. A few fallbacks are still imperfect (an attack damage such as 20 can stand in).
- **Evidence:** `text_identity.label_ids`, `label_reason`, `leader_conflict`; `versions.label_identity`.

## Latency for the Charmander photo

- **Locally (both runs):** baseline `no_match`, 7.8–8.3 s CPU, 3.9–4.3 s latency. All three flags: `uncertain en:sm3-18a`, verified with 59 artwork inliers on the first pass, 8.3–8.5 s CPU, 4.4–4.6 s latency. The label parse itself costs under 15 ms.
- **No local saving, because no local boundary retry existed to skip.** Locally the first pass ends `no_match` (Archen is not even in the local top 4), and the boundary retry only runs after a `retake`. The 0.2–0.3 s increase is the verification of the new candidate.
- **The saving is expected on staging, but not measured there.** On staging the first pass led into the boundary retry, which cost 4.5 + 0.8 + 0.8 = 6.1 s of the 13.8 s. With the label candidate verified on the first pass, that work is skipped. The expected scan is about 7.6 s plus roughly 1 s of verification, instead of 13.8 s. This needs an x86 rescan to confirm.
- **Lugia** with all three flags: 5.6 s CPU / 2.8 s latency (baseline 7.3 s / 4.2 s), the same as the PR #57 flags. A first version spent a needless 0.5 s label read on it, because the label had no number. The label read is now skipped when a candidate already exists.
- **CLF-026:** 5.1 → 6.4 s CPU, 3.0 → 3.5 s latency, for the extra label read and the boundary retry that still runs for an unverified suggestion. In exchange it goes from retake to the right card.

## How this was measured

- **Setup:** same as the Lugia report.
  - Local M4 Pro; staging catalogue export (md5-identical to staging's); staging artwork bundle.
  - Reference card images copied read-only from staging, so the local artwork verifier and its projection really run.
  - Three servers in parallel, one per arm, using `api/scripts/cpu_replay.py` with no `graded` hint. CPU is the server process tree's.
- **Runs:**
  - Run 4 had an intermediate template filter and the needless Lugia label read: also 0 regressions, with the same 3 fixes.
  - Run 5 is the final code.
- **Raw outputs:** `data/latency/slab-label-identity-20261021/` (gitignored).

## Regression fixtures

- **`api/tests/fixtures/text_identity_cases.jsonl`** now holds three recorded cases, each with its photo sha256, expected card and true catalogue neighbourhood (public card data):
  - Lugia (staging OCR).
  - Charmander (staging scan `b390124a`'s OCR hits; 183 English cards numbered 18).
  - `fresh100_135116047131`: card OCR plus the label read; 394 cards numbered 26 across all languages.
  - For both label cases the test asserts three things. The label path returns exactly the expected card. The number+name path alone cannot reach it. The old `collector_text` was a template word, and the new one is not.
- **`api/tests/test_text_identity.py`** adds:
  - grader label layouts (CGC, PSA, BGS, SV59, SWSH050, TG01, the Japanese Classic set line);
  - number keys;
  - template words;
  - pipeline tests for the near-threshold gate: a 0.80 leader contradicted by the text gets a verified candidate and no boundary retry; a 0.80 leader the text supports is left alone; without the flag nothing changes.
- **Totals:** full API suite 853 passed, 4 skipped.
- **Photos stay out of git.** The Charmander photo is the owner's upload; the panel photo is in the frozen panel kit.

## Caveats

- **ARM, not x86.** The same caveat as the Lugia report: features are extracted on the fly on ARM, not taken from staging's x86 bundle. The Charmander first pass differs locally (`no_match`, a different visual top) from staging (`uncertain` Archen, followed by a boundary retry). So the staging saving is an expectation, not a measurement.
- **The near-threshold gate is the new risk.** It lets text be considered against a visual leader up to 0.85. It applies only when no read name supports that leader, and it can only add candidates that pass the same verification and confirmation rules. On the panel it engaged on 2 photos, both correct.
- **Coverage is thin.** The label parser was exercised on 6 real slabs (CGC ×3, TAG, PSA ×2 counting the earlier ones). Other layouts, such as SGC, older BGS and Japanese-language labels, are covered only by unit tests or not at all.

## Recommendation

1. Enable `SLAB_LABEL_IDENTITY=true` alongside `OCR_LABEL_NAME_FILTER=true` and `TEXT_IDENTITY_CANDIDATES=true` on staging. Rescan the Charmander, Lugia and CLF-026 photos there to confirm the answers and measure the staging latency.
2. Watch `text_identity.label_reason` and `leader_conflict` in stored evidence before production.
