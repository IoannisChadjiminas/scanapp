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

## Step 1: the footer's printing orders the full pipeline (`OCR_PRINTING_FROM_TEXT`)

The 16 family-vector disagreements were all printing choices where the server had not read a footer number, so the visual leader was shown first (`printing_ambiguous`, same card name). The phone's own name and number name one card (set totals applied) in every such case, and that card was already a candidate.

- Change: when a printing is ambiguous and no earlier rule has named a printing, the card the phone's text names is moved to the front, if it is among the candidates. Status stays `printing_ambiguous`. Default off in code and in production; **on in the staging compose file** (gate below).
- Offline measurement on the 174 labelled uploads, using the stored candidate lists (`visual_top20` and `predicted`) and the owner's card as the text (the oracle; see caveats above):

| | Displayed first card is the owner's card |
|---|---:|
| Stored full pipeline | 143 of 174 |
| With the reorder | **168 of 174** |
| Wrong → correct | 25 |
| Correct → wrong | **0** |

- All 16 family-vector disagreements would be resolved: the owner's card is among their candidates, so the reordered full pipeline would agree with the family answer. Re-run the family rule against it, and its disagreements should drop from 16 to about 0 under the oracle text.
- Caveats: this reads stored candidate lists, not a full pipeline run (the real `combined` list can differ); the phone's text is assumed right, and a misread number that names another card in the list would move that card to the front, still under `printing_ambiguous`.
- Gate (plan step 1): 0 wrong first cards introduced, and a clear gain. Passed offline. Live confirmation: check the next staging scans of a reprint card show the footer's printing first.
- Tests: `api/tests/test_printing_from_text.py` (5). Full suite: 1067 passed, 10 skipped.

## Family vector re-run with the printing reorder

Same benchmark, with the stored full-pipeline answer replaced by what it would show with `OCR_PRINTING_FROM_TEXT` on (`--printing-from-text`; applies only to printing_ambiguous results whose candidates include the text's card).

| Text | Family rule | Early answers | Wrong | Disagreements with full pipeline (before reorder → after) |
|---|---|---:|---:|---|
| server | off | 26 | 0 | 0 → 0 |
| server | **on** | **40** | 0 | 1 → **0** |
| owner's card (oracle) | off | 50 | 0 | 1 → 1 |
| owner's card (oracle) | **on** | **78** | 0 | 16 → **1** |

The one remaining oracle disagreement (scan 4ae8e378, Toxel 078) is a `retake` in the full pipeline, which returned no card, so the reorder cannot apply. The early answer is the owner's card. It is the only disagreement left once the reorder is on.

Read: on the server's own text, the family rule gives +14 early answers with 0 wrong and 0 disagreements. It is the realistic setting (the phone's text was better than the server's, so the oracle is an upper bound). The family flag stays off in code and in both compose files; the decision to turn it on in staging is the owner's, with the one retake case in view.

## Decision point: the family rule's code default

Turning `STAGE1_FAMILY_VECTOR` on in code breaks four existing gate tests (`tests/test_stage1_gate.py`), including `test_stage1b_refuses_a_same_language_card_ahead_by_005`: a same-name card with another number that leads by 0.05 must be refused at stage 1b. The family rule allows exactly that case.

All 14 early answers the rule gains (server text) come from that case: the leader is a same-name card with a different collector number (Base Set Charmander 46 or Pikachu 58, a Pikachu promo 2015xy-6, or Pikachu extra-classic). So the policy is "the printed number outranks a same-name card's artwork at stage 1b".

State: code default off (suite green, 1067 passed); staging compose on (`STAGE1_FAMILY_VECTOR:-true`); production off. Accepting the policy means changing the four tests and the code default; keeping the contract means turning the rule off in staging too.

## Narrow footer rule (`STAGE1_FAMILY_VECTOR`, plan docs/family-rule-narrow-plan-20261026.md)

A same-name row is removed from the race only when the footer reads a full fraction whose total equals the text card's own known total and differs from that row's known total. Four existing gate tests and the stage 1b contradiction contract are unchanged; code default off; staging on.

| Text | Rule | Stage 1 (correct) | Stage 1b, needs artwork (correct) | Wrong | Disagreements with full pipeline |
|---|---|---:|---:|---:|---:|
| server | off | 26 | 31 | 0 | 0 |
| server | broad (earlier) | 40 | 21 | 0 | 0 |
| server | **narrow** | **30** | 27 | 0 | 0 |
| owner's card | off | 50 | 56 | 0 | 1 |
| owner's card | **narrow** | **56** | 52 | 0 | 1 (the Toxel retake, unchanged) |

**Correction.** The earlier "+14" for the broad rule counted stage 1 answers only. Most of those came from cases that stage 1b already reached, so the net gain in answerable cards was about +4. The narrow rule moves 4 cases from stage 1b to stage 1 on the server's text and adds none; on the owner's text it adds 6 at stage 1 and moves 4 from 1b, a net +2. The gain is mainly that stage 1 answers skip the artwork check, so they are faster and less likely to fail.

The plan's gate (0 wrong, 0 disagreements, a gain) passes on the server's text. The Charmander cases the rule frees (Base Set 46 leading against an 9/108 footer) are mostly stage 1b candidates, where the artwork check still runs.

## Step 3: frame fallback (`STAGE1B_FRAME_FALLBACK`), on the real server-frame path

`api/scripts/stage1_bench/run_server_frame.py` calls the real `evaluate_stage1` with no phone embedding, so it reaches `_evaluate_server_frame`: the server's frame finder, the real DINOv2 embedder, and the real local artwork check on the reference images. Only the fallback differs.

| Text | Fallback | Family | Early answers (artwork passed) | Wrong | Disagreements | `no_server_frame` | `artwork_miss` |
|---|---|---|---:|---:|---:|---:|---:|
| server | off | off | 0 | 0 | 0 | 91 | 4 |
| server | **on** | off | **10** | 0 | 0 | 0 | 46 |
| server | on | on | 10 | 0 | 0 | 0 | 48 |
| owner's card | off | off | 0 | 0 | 0 | 159 | 10 |
| owner's card | **on** | off | **16** | 0 | 0 | 0 | 83 |

The server's frame finder fails on 91 of 174 stored uploads (the uploads are already cropped to the card), and the fallback recovers those. Its frame is the whole upload here, since the bench sends no phone corners; in the app the phone's card-shaped corners are used when present, which should do better. The artwork check rejects the large majority of fallback frames (`artwork_miss`), which is the safety net working, not a failure. The reference images cover 876 cards, so some uploads cannot be artwork-checked at all.

Gate (plan step 3): 0 wrong, 0 disagreements, a gain. Passed. Turned on in the staging compose file; off in production.
