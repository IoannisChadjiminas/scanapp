# Slab label text recovery for slab-outline scans

Date: 2026-10-21. Branch `claude/holder-quad-card-region` (PR #61), from `origin/main` at 78bb0e9. Staging was only read: scan rows and API logs.

This is the user-reported regression: "now I get inteleon card". The app (build 147) sends the slab outline as `card_quad` for gallery imports, and that is the intended client input. An earlier version of this PR cropped the quad down to the card inside the holder. The user found that cropping made the app worse, so that part was removed and holder framing is unchanged. What remains is text-path robustness: with a slab-outline quad, the label text (LUGIA EX, #17, JP / Burning Shadows 18a/147) is present in every scan, and it now leads to the right card.

## Result in one table

The 155-photo panel, plus earlier extras (Lugia PNG and JPEG, Charmander, three gallery-screenshot reproductions), plus seven quad cases: 168 photos.
- **Quad cases:** four slab-outline quads derived from the staging frames (Lugia app-like JPEG and PNG, Charmander app-like JPEG and PNG), plus three card-window quads that mimic the user's experiments (Lugia tight, Lugia loose, Charmander).
- **Arms:** the baseline is today's deployed flags (`OCR_LABEL_NAME_FILTER`, `TEXT_IDENTITY_CANDIDATES`, `SLAB_LABEL_IDENTITY`, `FULL_IMAGE_TEXT_FALLBACK`, `USE_CLIENT_QUAD`). The variant adds `SLAB_TEXT_RECOVERY=true`.

| | Answer changes (card or status) | Regressions | Fixed | CPU mean / p50 / p90 (ms) | Latency p50 / p90 (ms) |
|---|---|---|---|---|---|
| Baseline | (vs previous baseline run: 0) | - | - | 5,125 / 3,684 / 8,597 | 2,266 / 4,547 |
| + `SLAB_TEXT_RECOVERY` | 4 | **0** | Lugia slab outline (ja:SC-013 locally, Inteleon on staging → CLF-017), Charmander slab outline (retake → sm3-18a), Lugia loose card window (retake → CLF-017), panel `holdout4_072` (retake → base2-58, needs confirmation) | 5,078 / 3,713 / 7,828 | 2,252 / 4,472 |

- Correct answers: baseline 159/167 labelled photos, with the flag 163/167.
- **All seven quad cases now end on the right card** (CLF-017 or sm3-18a).
- **Field changes besides the fixes:**
  - Two panel photos' `collector_text` changes from attack damage (`60`, `180`) to none.
  - Staging's Lugia JPEG (`lugia-app.jpg`) now answers CLF-017 on the first pass through the label path. Before, the boundary retry supplied ルギア and the printing evidence. Same card, about half the time; name now none, printing `unconfirmed` instead of `metadata_supported`.

## The staging scans, and what each now does

All are slab screenshots from the iOS gallery with `quad=rect`. The quads are not logged; the frame sizes tell slab outlines (about 0.63) from card windows (about 0.76–0.81).

| Scan | Frame | Was | Cause | With `SLAB_TEXT_RECOVERY` (recorded OCR, fixture) |
|---|---|---|---|---|
| ad1b8f19, 072818fe, 862c09b5 | 784×1238 slab | ja:S8b-038 Inteleon | name "CLASSIC COLLECTION"; `#17HOLO` not parsed; PSA set name not in catalogue; footer 017/012 | label: #17 + JP + LUGIA EX → ja:CLF-017 |
| b73e0359 | 906×1236 | ja:CLF-017 verified | (footer 017/032 read) | unchanged; name now LUGIA EX, not CLASSIC COLLECTION |
| b6b5a00b | 694×917 card window | ja:SM10b-065 | name "CLASSIC COLLECTION", no number | name ルギア; label #17 + CLASSIC COLLECTION alias → CLF-017 |
| 14f53a69 | 662×817 | retake | name "#17HOLO", collector "200" | name ルギア, collector none; label #17 + ルギア → CLF-017 |
| cab13528 | slab interior | en:sm3-18a verified | (picture) | unchanged; no label text was read |
| 8d5a1e7b | 414×582 | en:sm3-18a unverified | name "Burning Shadows- 18a/147", collector "20" | name none, collector none; label → sm3-18a |
| e61fc463 | 395×519 | ja:E3-020 | only the variant line "Cos. Holo - Charmander Sidekick Coll." was read | the variant line now marks a label, so the upper-half label read finds Burning Shadows - 18a/147 → sm3-18a |

## What changed (`SLAB_TEXT_RECOVERY`: code default off; on in both compose files)

- **PSA labels** (`label_identity.py`):
  - A number fused with its variant word (`#17HOLO`) parses as 17.
  - The dated header `2023 POKÉMON JP` sets the language (JP/JPN → ja, KR → ko, CH/CHN → zh-tw).
  - A set alias: (ja, CLASSIC COLLECTION) → CLF/CLL/CLK.
  - Without a set match, the existing fallback applies: label card name + number + language, 1–3 cards.
- **Label detection:** a fused `#17HOLO`, a set line with a suffixed number (`Burning Shadows- 18a/147`) or a CGC variant line (`Cos. Holo - …`, `Holo - …`) now marks a label. So the existing upper-half label read runs when the strips held only those lines.
- **Name selection** (`ocr.py`, under `OCR_LABEL_NAME_FILTER`, only with this flag):
  - Those label lines are never the name.
  - A digit-free line after a set-less dated header (`2023 POKÉMON JP` → `CLASSIC COLLECTION`) is the label's set line.
  - With label fields in the strip, a CJK title (ルギア) beats the Latin label lines.
  - Guards: the PSA MEW, CGC Charmander and `2016 BREAKPOINT` Gyarados cases keep their names.
- **Collector text:** attack damage, a bare multiple of ten (20, 200), is never `collector_text`. Printed numbers without a total keep their leading zeros or prefix (053, SWSH050).
- **Misread denominators** (`text_identity.py`): when the read denominator is no known printed total for that number (017/012), the numerator stands and the read name must narrow the cards on its own (`numerator_candidates`).
- **Label over footer:** a slab label's candidate whose artwork verifies is not vetoed by a footer fraction that contradicts the label (Charmander `16a/147`).
- **Unchanged:** the text gate, artwork verification and projection, review-only results, at most 3 suggestions. Holder framing for the visual and artwork paths is not touched.
- **Tooling:** `api/scripts/cpu_replay.py` now sends a case's recorded `card_quad`.

## Time (ms; CPU / latency)

| Photo | Baseline | + flag |
|---|---|---|
| Charmander slab outline (JPEG) | 10,679 / 5,878, retake | 6,139 / 3,311, sm3-18a verified, no boundary retry |
| Charmander slab outline (PNG) | 6,077 / 3,754 | 5,758 / 3,410 |
| Lugia slab outline (JPEG) | 34,341 / 24,607, wrong card | 34,376 / 24,507, CLF-017 verified |
| Lugia slab outline (PNG) | 34,678 / 25,718 | 34,648 / 25,725 |
| Lugia loose card window | 8,111 / 4,464, retake | 4,403 / 2,714, CLF-017 |
| Lugia tight card window | 3,906 / 2,625 | 3,587 / 2,300 |
| Charmander card window | 3,512 / 2,113, matched | 3,904 / 2,408, matched |
| Staging's Lugia JPEG (no quad) | 9,003 / 4,943 | 5,418 / 2,677 |
| `holdout4_072` | 10,695 / 5,363, retake | 11,527 / 5,600, base2-58 suggested |

- About 22–24 s of the Lugia slab-outline rows is the grading safety net, in both arms. The replay sends no `graded` hint, so the holder's label text triggers a synchronous label read. The app sends `graded=true`, so in the app grading runs in parallel.

## Regression fixtures

- **`api/tests/fixtures/text_identity_cases.jsonl`** gains the recorded OCR of all nine staging scans above (`staging_<id>`), each with its true catalogue neighbourhood. For `e61fc463` it also holds the upper-half label read, recorded on the Charmander screenshot at 923×2000. The test asserts, per scan:
  - the old name and collector picks are reproduced;
  - with recovery, no label line becomes the name and no damage or template word becomes the number;
  - label recovery (or numerator + name) gives exactly the expected card;
  - `cab13528`, which was answered by its picture, is not disturbed.
- **Unit tests** cover the new label fields, damage, the CJK-title preference and the guards.
- **Top acceptance case, `862c09b5`** (app build 1.0.0+147, the app's exact 421,985-byte upload, slab-outline quad; its OCR is identical to ad1b8f19 and 072818fe). A pipeline test replays its recorded OCR through `recognize_bytes` with a slab-outline quad (`client_quad_only`, 784×1238 frame):
  - without the flag, the visual guess wins, as on staging;
  - with `SLAB_TEXT_RECOVERY`, the label (LUGIA EX + #17 + JP) gives ja:CLF-017. It is verified by artwork projection, shown for confirmation, and the boundary retry is skipped.
  - Re-encodes of that screenshot already pass on staging. Only the app's exact bytes fail, and those were not stored, so recorded OCR is the strongest reproduction available.
- **Full API suite:** 873 passed, 4 skipped. The replay ran on this recognition code; later commits only added tests and fixtures.

## Caveats

- **ARM, not x86.** The replay ran locally on ARM. Staging latency is not measured.
- **The quads are reconstructed.** They come from the logged frame sizes; the app's exact quads and bytes are unknown. The fixtures use staging's own OCR, so the text logic is checked against what the app really produced.
- **The set-alias table holds one entry.**
- **The damage rule** treats a bare multiple of ten as damage. A real printed number like "20" without a total is then not shown as `collector_text`. It does not affect identity: a bare number is not used as printing proof.

## Recommendation

Merge after review. The flag is on in both compose files. Then rescan the two slab screenshots from the iOS gallery with the slab outline, and confirm both end on CLF-017 and sm3-18a.
