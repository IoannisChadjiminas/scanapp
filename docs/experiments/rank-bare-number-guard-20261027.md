# A bare number lifting a weak picture match (2026-10-27)

Read-only analysis of staging scan `327b30d6` (A55 round 4, a Toxel MEP 078) and a replay of the ranking step on all stored staging review cases. No photos and no OCR text are in this file.

## What happened

- The phone's outline was short at the bottom, so the server's footer strip read the attack line. Its number (the attack damage) came back as a bare collector number at 0.99998 confidence. The server's name read also picked a misread of the stage badge.
- `rerank` gave every card with that number +0.08 and the visual leader −0.20 (conflict). A card at visual 0.60 (DP Bibarel 20) beat Toxel at visual 0.85: 0.695 vs 0.666. The replay reproduces both stored scores exactly.
- `_keep_visual_leader` did not reinstate Toxel: its gap was measured to its own Japanese print (0.05), and a collector conflict with a gap under 0.10 keeps the OCR order.
- The phone's provisional answer was Toxel at 2.2 s, and the final answer was Bibarel at 9.1 s (status `uncertain`, so it asked for confirmation).

## Change (RANK_BARE_NUMBER_GUARD, default off)

- A card cannot be first over the visual leader through a bare number alone (no total, no set code) when its picture is 0.15 or more below a leader that clears the visual floor (0.78), and its name does not agree. The leader keeps its conflict flags, so it still needs confirmation.
- The leader's gap is measured to the best card in a language the scan reads as, not to its own print in another language.
- A full fraction or set code that agrees, or a name that agrees, still wins as before.

## Replay of the ranking step (all stored staging cases)

| | Count |
|---|---:|
| Cases replayed | 7,915 |
| Replay with the flag off gives the stored first card | 6,556 (83%; later steps such as local artwork verification explain most of the rest) |
| First card changed by the flag | 36 |
| Changed to the card the stored full pipeline answered | 35 (one repeated test photo ×33, two Toxel scans from 25 Oct) |
| Changed to a card the stored pipeline did not answer | 1: `327b30d6`, Bibarel → Toxel (the visual leader, and the phone's name) |
| Changed to a card different from both the stored answer and the visual leader | 0 |

Limits: the replay covers the ranking step only, with the stored top-20 candidates plus the stored answer; candidates beyond those are not stored. Language detection is the stored detected language. Staging's OCR prefix flags were used (`OCR_SET_CODE_PREFIX=true`, `OCR_PROMO_PREFIX_NEAR=false`).

## Not changed here

- The short phone outline (the root of the misplaced footer strip) and the server's stage-badge name read are separate issues.
