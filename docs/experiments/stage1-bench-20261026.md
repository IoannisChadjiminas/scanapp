# Offline stage 1 benchmark, Android manual uploads (2026-10-26)

Plan: `docs/instant-improvement-plan-20261026.md`, steps 1 and 2. Script: `api/scripts/stage1_bench/run_bench.py`. Read-only: the stored uploads (226 Android manual uploads from 25–26 October, of which 174 have a name the owner's list maps to a card), the server's index and model on the Mac, and the staging compose flags. No photos or OCR text in git; this file has counts and scan ids only.

## What it runs, and what it does not

- The phone's input for each upload is a whole-card crop of the photo (the outline the fixed app gives), embedded with the server's DINOv2-small model (the phone's LiteRT model matches it at cosine 0.998).
- The gate is the real `decide()` from `stage1_gate.py`, with the staging flag set from `compose.dokploy.yaml`, and `language='en'` (the owner's cards are English; the app sends the language it read).
- The catalogue is the research export (`data/android-embedding-research-20261023`), with the frozen public set totals from `api/tests/fixtures/stage1-set-totals-20261022.json`, as the replay script uses.
- **Not run:** the artwork check. Stage 1b candidates are counted, not answered, so the 1b numbers are candidates for the artwork check, not answers.
- Two text modes:
  - `server`: the server's own read of the upload (name and number from the stored case). A lower bound: the phone's live text was better (number on 10 of 11 live scans).
  - `oracle`: the labelled card's name and printed number, as a correct footer read would give. The safety test for the family rule.
- "Wrong" = an early answer that is not the owner's card (same card, any printing of its family id). "Disagreement" = an early answer that differs from the stored full-pipeline top card (what the background check would compare).

## Results (174 labelled uploads)

| Run | Early answers | Wrong vs owner's card | Disagreements with full pipeline | Stage 1b candidates (wrong) | Visual contradiction | Printing twins | Ambiguous / no unique text |
|---|---:|---:|---:|---:|---:|---:|---:|
| server text, family off (baseline) | 26 | 0 | 0 | 31 (0) | 15 | 26 | 76 |
| server text, **family on** | **40** | 0 | **1** | 21 (0) | 11 | 26 | 76 |
| oracle text, family off | 50 | 0 | 1 | 56 (0) | 35 | 33 | 0 |
| oracle text, **family on** | **78** | 0 | **16** | 37 (0) | 26 | 33 | 0 |

Flags as staging runs them, plus `family_vector` where marked. The baseline counts are on the current code with the family flag off; they match the staging behaviour. Earlier numbers in this session (20 early answers) used the research export without the set totals and a different language setting, and are superseded.

## Reading

1. **The family rule (`STAGE1_FAMILY_VECTOR`) adds early answers with no wrong ones against the owner's cards** (+14 on the server text, +28 on the oracle text). Where it fires, the vector leader is the same name as the text card (Base Set Pikachu for Evolutions Pikachu; Base Set Charmander for Evolutions Charmander) and the text's number picks the printing.
2. **It also adds disagreements with the full pipeline**, which the rule forbids: 1 on the server text, 16 on the oracle text. In every one of them the full pipeline's stored answer is another printing of the same name (Pikachu 30th promo 014; Charmander Base Set 46) and the early answer is the owner's card. So the full pipeline was not wrong to show a printing choice, and the early answer was not wrong about the card. Both are true at the level of the card name; they differ at the printing. The background check counts this as a disagreement.
3. **So the flag cannot ship under the current rule.** Either the owner accepts a printing-level difference as "same card, printing ambiguous" and the background check compares at the card-family level, or the family rule stays off. This is a policy decision, not a tuning one.
4. **Margins on the family answers are small** (0.025 to 0.043 on the disagreements, against the 0.02 stage 1 minimum). A higher margin would cut the disagreements but also most of the gain; the benchmark shows the trade-off directly if needed.
5. **Frame fallback (`STAGE1B_FRAME_FALLBACK`)** is implemented in `_evaluate_server_frame` and unit-tested for the card-shape check, but this benchmark does not reach that path (it needs the server's frame finder and the artwork check). Not measured here; default off.

## Not verified

- Stage 1b answers (the artwork check is not run). The 1b candidate counts above are not early answers.
- The phone's real text. The server text is a lower bound, and the oracle text is an upper bound; the live phone sat between them.
- The research catalogue, not PlanetScale. The production lookup has the same import id, but the number of rows per lookup was not checked against it.
- Other phones and the Play-delivered model.
- Whether the warnings in the replay tests (`invalid value encountered in matmul`) predate this change; not checked.
