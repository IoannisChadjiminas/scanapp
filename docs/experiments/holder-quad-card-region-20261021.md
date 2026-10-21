# Holder quads, PSA Japanese labels and misread denominators

Date: 2026-10-21. Branch `claude/holder-quad-card-region`, from `origin/main` at 78bb0e9 (includes PR #60). Staging was only read: scan rows and API logs.

This is the regression the user reported ("now I get inteleon card") after the app started sending card corners for gallery imports.

## Result in one table

The 155-photo panel, plus the earlier extras (Lugia PNG and JPEG, Charmander, three gallery-screenshot reproductions), plus four holder-quad cases: 165 photos.
- **Holder-quad cases:** the Lugia 923×2000 app-like JPEG and the Lugia PNG, each with the holder quad the app sent; the Charmander app-like JPEG and the Charmander PNG, each with a holder quad.
- **Arms:** the baseline is today's deployed flags (`OCR_LABEL_NAME_FILTER`, `TEXT_IDENTITY_CANDIDATES`, `SLAB_LABEL_IDENTITY`, `FULL_IMAGE_TEXT_FALLBACK`; `USE_CLIENT_QUAD` on). The variant adds `HOLDER_CARD_REGION=true` and `SLAB_TEXT_RECOVERY=true`.
- **Runs:** two replays; run 9 is the final code.

| | Answer changes (card or status) | Regressions | Fixed | CPU mean / p50 / p90 (ms) | Latency p50 / p90 (ms) |
|---|---|---|---|---|---|
| Baseline (run 9) | (run 8 vs run 9 baseline: 0) | - | - | 5,055 / 3,638 / 8,257 | 2,243 / 4,437 |
| + new flags (run 9) | 3 | **0** | Lugia holder quad (was ja:SC-013 locally, Inteleon on staging), Charmander holder quad (was retake), panel `holdout4_072` (was retake) | 5,049 / 3,676 / 8,010 | 2,276 / 4,375 |

- Correct answers: baseline 157/164 labelled photos, with the new flags 160/164.
- Panel CPU and latency are unchanged within noise.
- **Field changes besides the fixes:** one. The Lugia PNG with a holder quad keeps its correct card (artwork plus label), but its footer number is no longer read (017/032 → none), so printing drops from `metadata_supported` to `unconfirmed`. The card window's footer number is about 8 px tall and OCR misses it; the wider holder frame read it at 0.88.
- **Two field changes run 8 showed, both fixed before run 9:**
  - The set-line rule took `2016 BREAKPOINT` (a dated header that already holds its set) as the header of a set line and dropped the card name below it. It now applies only to headers with no set of their own (`YEAR POKÉMON [language]`).
  - A holder-quad slab lost its grade. With no `graded` hint, the grading safety net only looks for label text in the card OCR, and the card region holds none. A holder quad now counts as a seen slab.

## What went wrong on staging

Scans `ad1b8f19` and `072818fe` (08:41Z, iOS gallery, 421,985 bytes, `client_quad_only`): the app's quad outlined the slab holder, not the card.
- **Frame and OCR:** the selected frame was the 784×1238 holder. Its title strip (784×272) held the PSA-style label: `10, PRISTINE, 2023 POKÉMON JP, CLASSIC COLLECTION, LUGIA EX, #17HOLO, 00044829`. Its footer misread 017/032 as `017/012`.
- **Name:** "CLASSIC COLLECTION". The label filter skips only label fields it recognises, and a set line without a number is not one.
- **Label path:** it found no number. `#17HOLO` fuses the number with the variant word, and the set name "CLASSIC COLLECTION" shares no words with the catalogue's "Pokémon Card Game Classic Venusaur & Lugia ex Deck".
- **Number+name path:** 017/012 matches no printed total, so `number_not_in_catalogue`.
- **Result:** the visual top, `ja:S8b-038` Inteleon (0.71), was returned as uncertain. Wrong.

Charmander with a holder quad (`404c4b50`) happened to be right on staging (`slab_interior` frame). Locally the same holder quad gives a retake: the label candidate verifies (72 inliers), but the footer misread `16a/147` vetoes it as incompatible.

## What changed (both flags default off in code; on in both compose files)

### `HOLDER_CARD_REGION`
- **Trigger:** the client quad was used alone (`client_quad_only`) and the warped frame is holder-shaped (portrait aspect 0.52–0.67).
- **Card region:**
  - The card's outline inside the holder is used when the detector finds a card-shaped (0.64–0.80), large (≥ 35%) rectangle below the label.
  - Otherwise a card-aspect window below the label (24–96% of the holder height), calibrated on both holders.
  - The visual embedding, artwork search, local verification and the card's own title/footer OCR all run on that region. No alternative frames are proposed, so the holder cannot win the frame selection back.
- **Label strip:** the holder's top 27% is kept and read once (`ocr_passes` scope `holder_label`). This happens only when the text paths found nothing on the card, and the lines feed the slab-label path as `holder_name` hits.
- **Status:** a holder-region scan is never `matched` (reason `holder_card_region:<outline|window>`).
- **Grading:** it also counts as a seen slab for the grading safety net.

### `SLAB_TEXT_RECOVERY`
- **PSA labels** (`label_identity.py`):
  - `#17HOLO` → number 17.
  - The `2023 POKÉMON JP` header sets the language (JP/JPN → ja, KR → ko, CH/CHN → zh-tw).
  - A small set-alias table, (ja, "CLASSIC COLLECTION") → CLF/CLL/CLK.
  - Without a set match, the existing fallback applies: label card name + number + language, 1–3 cards. "LUGIA EX" matches view_title "Lugia ex".
- **Name selection:** a digit-free line right after a set-less dated label header (`2023 POKÉMON JP` → `CLASSIC COLLECTION`) is the label's set line, never the card name.
- **Misread denominators** (`text_identity.py`): when the read denominator is no known printed total for that number (017/012), the numerator stands and the read name must narrow the cards on its own (reason `numerator_candidates`). The panel's `holdout4_072` (Oddish, base2-58) is fixed this way, as an unverified suggestion needing confirmation.
- **Label over footer:** a slab label's candidate whose artwork verifies is not vetoed by a footer fraction that contradicts the label (Charmander `16a/147`).

All existing safety rules still apply: the text gate (visual top below the floor, or near it when the leader conflicts), local artwork verification and projection, review-only results, at most 3 suggestions.

`api/scripts/cpu_replay.py` now sends a case's recorded `card_quad`, if it has one.

## Time

Per photo, run 8 / run 9, CPU and latency in ms:

| Photo | Baseline | + new flags |
|---|---|---|
| Charmander JPEG + holder quad | 10,547 / 10,731 CPU, 5,721 / 6,066 latency, retake | 5,952 / 5,772 CPU, 3,498 / 3,369 latency, sm3-18a verified |
| Charmander PNG + holder quad | 5,577 / 5,534, 3,208 / 3,224 | 3,963 / 5,313, 2,342 / 3,104 |
| Lugia JPEG + holder quad | 34,611 / 34,791, 24,593 / 24,588, wrong card | 33,671 / 33,591, 24,442 / 24,321, CLF-017 verified |
| Lugia PNG + holder quad | 35,341 / 34,808, 25,948 / 25,683 | 36,417 / 35,900, 26,579 / 26,253 |
| `holdout4_072` | 10,743 / 10,747, 5,386 / 5,366, retake | 11,665 / 11,816, 5,644 / 5,653, base2-58 suggested |

- **Charmander:** the boundary retry (2.4–2.6 s) is no longer needed, so CPU is about −45% and latency −42%.
- **Lugia rows:** about 21.8 s of these rows is the grading safety net, in both arms. The replay sends no `graded` hint, so the holder's label text triggers a synchronous label read. The app sends `graded=true`, so in the app grading runs in parallel. Without it, recognition is about 2.5 s in both arms; the new flags add the label-strip read and remove most local-verification time.
- Lugia and Charmander without a quad, and the gallery-screenshot reproductions, are unchanged.

## Regression fixtures

- **`api/tests/fixtures/text_identity_cases.jsonl`** gains:
  - `lugia_holder_quad_ad1b8f19`: staging's own recorded OCR. Today's label and number paths miss the card; label recovery and the numerator + card-name path each find exactly ja:CLF-017.
  - `charmander_holder_quad_404c4b50`: staging's card OCR with the `16a/147` misread, plus the holder label strip. Without the label read nothing reaches sm3-18a; with it, the label path finds exactly it.
- **`api/tests/test_text_identity.py`** adds:
  - PSA recovery (number, `JP` language override);
  - the numerator fallback, which is not used when the denominator is a known total;
  - set-line selection, including the PSA MEW, CGC and Gyarados guards;
  - the holder window geometry;
  - pipeline tests: a holder quad with the flags reads the card's title (ルギア), reads the label strip and returns CLF-017; without the flags the label stays the title and the wrong card stays.
- **The holder quads** were derived from the staging frames (784×1238 at x≈10–794, y≈338–1576 on the 923×2000 screenshot) and measured on the Charmander screenshot. They are recorded in the local replay panel; photos stay out of git.
- **Totals:** full API suite 866 passed, 4 skipped.

## Caveats

- **ARM, not x86.** The replay ran locally on ARM (see the earlier reports). Staging latency is not measured.
- **The app's exact quad is unknown.** It is not logged; the one used here reproduces the same frame size and the same failure.
- **The card window is a fixed layout.** It fits PSA- and CGC-style holders photographed head-on. A strongly skewed holder or an unusual label height could crop the card's footer, as on the Lugia PNG; the answer then rests on artwork plus label.
- **The set-alias table holds one entry.** Further PSA names need adding as they are seen.

## Recommendation

The flags are on in both compose files; the code default stays off. After deploy, rescan the Lugia and Charmander slab screenshots from the iOS gallery and confirm `holder_card_region` in the stored evidence.
