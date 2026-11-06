# The phone's number alone orders an ambiguous printing (2026-11-06)

Read-only analysis of staging scan `bd643ddd` (Redmi Note 10 Pro, the PP-OCR footer-band round of 6 November 2026, PokeSingle `docs/phone-first-results-2026-11-06-redmi-ppocr-band/`) and a replay of the rule on every stored staging review case whose phone hint carried a number. No photos and no OCR lines are in this file.

## What happened

- The phone's PP-OCR read the collector number `9/108` (confidence 0.966) on an Evolutions Charmander and sent it in the upload's late text hint with no name (ML Kit had read none). The photo's footer shows `9/108 ©2016 Pokémon` with the Evolutions symbol.
- The server's own OCR read the number as `3` and the name as `harmander`. The picture put Base Set Charmander 46 first (visual 0.887) and the Evolutions reprint of the same art third (0.871); the answer was `printing_ambiguous` with Base Set shown first, as on the three rounds before with this photo.
- `OCR_PRINTING_FROM_TEXT` (on in staging) orders an ambiguous result by the card the phone's **name and number** name in the catalogue (`_text_named_card`). With no name it names nothing, so the phone's right number did not reach the printing choice.

## Change (under `OCR_PRINTING_FROM_TEXT`, no new switch)

- When the name-and-number lookup names no card, the phone's number alone goes through the footer fraction rule (`fraction_named_printing`) against the printings the picture could not tell apart: parsed like a footer read with its own confidence (0.85 or more, the footer bar), matched with set totals, naming a printing only when exactly one of the ambiguous printings agrees and the card shown first does not. `_hint_number_named_printing` in `pipeline.py`.
- It only orders: the status stays `printing_ambiguous`, the stage 1 shortcut (name, number and the embedding's agreement) is untouched, and a number that matches none, several, or the card already shown changes nothing. Tests in `api/tests/test_printing_from_number.py` (the stored top 3 of `bd643ddd`, a number matching none, two printings sharing it, a wrong total, no confidence).

## Replay on stored staging scans

`replay_ranking.py` does not carry the phone's hint, so a streamed read-only export of every stored `printing_ambiguous` case with a phone number (ids, the hint's number and confidence, the top 20's ids and numbers with their set totals from `/data/catalog.sqlite`) was replayed through the rule with the stored first card shown and the top-20 cards sharing its name standing in for the ambiguous family (wider than the live family, so an upper bound on moves).

| | Count |
|---|---:|
| Stored `printing_ambiguous` scans with a phone number (26 Oct to 6 Nov 2026) | 192 |
| of which with no name in the hint | 17 |
| of which with number confidence 0.85 or more | 37 |
| First card changed by the rule | **1**: `bd643ddd`, base1-46 → en:xy12-9 (the photo's printing) |
| Changed to a wrong card | 0 |

The other 191 stay: on most the number agrees with the card already shown (the name-and-number rule or the server's own footer read had ordered them), on the rest it names none or several. Limits as for every stored-scan replay: the stored top 20 and the stored first card only; the live family is the printing index's, narrower than "same name in the top 20".

## Not changed here

- The server's own footer read (`3` for `9/108`) and the gallery detector's corners on this photo (a box wider than tall; the app's band guard refused it) are separate issues.
- The stage 1 shortcut still needs the name: a right number with no name confirms nothing on the server, as before.
