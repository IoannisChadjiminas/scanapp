# Why the phone's text fails to name one card on Android manual scans

Date: 2026-10-25. Read-only analysis of the 29 manual scans from the Galaxy A55 rescan (build 1.0.0+153, release, scan flags `nr1.bf-none.emb1`: number reader on, blur-fix flags off, embedding on). Staging was only read (no config, no captures, no deletions). No photos and no raw OCR lines are in this file. Scans are named by the first 8 characters of their scan id. Parsed name and number values appear only where the table needs them.

Sources: the phone log (`/private/tmp/ph.txt`, 29 scan ids with `scan-diagnostics` lines), the 26 case JSONs and 26 input photos in `/data/review` on staging (3 scans have no case record, see below), and the 53-scan analysis in `docs/experiments/live-android-uncertain-scans-20261025.md`. Analysis scripts and copies of the photos are in the session scratchpad, not in git.

## Answer in five lines

1. **The phone's text is missing for most of these scans, and that is an app timing problem.** 16 of 29 phone text results arrived after the 300 ms budget (`client_text.late`), and 3 more had no name or number fields (`client_text.none`). Only 10 scans sent any text. The phone's text sent a name on all 10 and a number on 7.
2. **When the phone's text arrives, it is usually right, and the server still does not name one card.** The server reads both a name and a number on 13 of 26 stored cases (one of them wrong, `24`); the rest are blocked by twins (Paradox Rift versus Prize Pack, 7 scans), reprint ties (Base Set versus Evolutions, 6 scans), or the frame rule (`inferred_frame` downgrade, 4 scans). Those are server decisions, and they are correct to stop.
3. **Number-side app causes are the second group.** The phone found a name but no number on 3 scans, and found no fields at all on 3 more. Two of those are capture problems: a blurred card (2 scans) and a card that fills only about 16% of the frame (1 scan).
4. **Server number parsing is now mostly fixed for the 30th Celebration `30C` prefix** (Comfey and Zorua read as `077/128` and `095/128`), but the `MEP` promo prefix still reads as `MP078` (1 scan), and the bare `078` gets a `retake` (1 scan). One footer was misread as `199/122` (1 scan).
5. **Ranked fix:** (a) let the phone's text finish after the 300 ms budget, or send it as a late hint; (b) give the PP-OCR number read a longer cap; (c) parser fix for the `MP`/`MEP` promo prefix. Server rules for twins and reprint ties should stay as they are. Details are in the ranked proposal at the end.

## Status of the 29 scans

Phone log (`scan.result`): printing_ambiguous 12, uncertain 14, no_match 2, retake 1, **matched 0**. No scan was answered early. The owner's note of "3 early answers of 29" does not appear in the phone log (`scan.result` has no matched). The 20 `scan.provisional` events may be what was counted; I could not check that from these logs.

Phone embedding: sent on 23 of 29 (`embedding.sent`), late on 6. This is a change from the 53-scan run, where it was never sent.

Phone text (`client_text.*`, `text.read`):

| Phone text state | Scans | Scan ids |
|---|---|---|
| Sent, name and number both true | 7 | 7, 8, 9, 10, 12, 21, 22 |
| Sent, name true and number false (1 candidate on 2 of them) | 3 | 4, 15, 24 |
| Late (after the 300 ms budget, nothing sent) | 16 | 0, 1, 2, 3, 5, 6, 11, 14, 16, 17, 18, 19, 20, 25, 27, 28 |
| No name or number fields (`no_fields`) | 3 | 13, 23, 26 |

Phone number reader (`number_recognizer.*`, PP-OCR on the photo): capped at 1.2 s and late on 15 scans; finished on 6, with a number on 1 (`27`, `35/108`). This matches the owner's note.

Timing: the ML Kit read (`text.read.read_ms`) was 162 to 1117 ms, median 277 ms. The recognition result (`recognition.done`) had a median of 6.97 s, against 7.0 s in the owner's note.

## What changed since the 53-scan run

| Item | 53-scan run (`641 x 896`, no embedding) | This run (29 scans) |
|---|---|---|
| Upload size | 641 x 896 (about 150 KB) | 1363 x 1904 in 28 scans; 1432 x 2000 in 1 (`e0789f27`); about 0.8 MB |
| Still | requested 4000 x 3000 | 3060 x 4080 (portrait) |
| Footer digit height in the upload | about 8 px (eyeballed) | about 15 to 17 px (eyeballed, see below) |
| Phone embedding | never sent (`no_reader`) | sent on 23 of 29 |
| Phone text late (budget missed) | 7 of 53 | 16 of 29 (55%) |
| Phone text sent | 21 of 53 | 10 of 29 |
| Set-code prefix `30C` before the number | lost by the parser on 4 Comfey scans | read correctly on Comfey (`077/128`, 3 scans) and Zorua (`095/128`, 1 scan) |
| `MEP` promo prefix (Toxel) | lost (`MEP078`) | still lost: read as `MP078` on 1 scan; bare `078` on 1 scan |

The footer is bigger, but the phone read is slower and later. My guess is that ML Kit's read on the larger photo or the larger still takes longer than the 300 ms budget; this is not measured. The 53-scan run had 7 late reads out of 53, so the late count rose from 13% to 55% after the change.

Eyeball estimate of the footer digits: on the stored review copy, which is 1145 px wide (not the 1363 px upload; see the last section), the collector line `077/128` is about 12 to 14 px tall. At upload scale that is about 15 to 17 px. This is an estimate from the image, not a measurement.

## Per-scan table

Columns: phone text (the state, and name/number as sent); PP-OCR number (`num`); what the server read (parsed name and number, from the case JSON); server status; first blocker in pipeline order (capture, then phone text, then server OCR, then identity or printing rule); other contributing causes.

| # | Scan | Phone text | Server read (name / number) | Server status and top card | First blocker | Also |
|---|---|---|---|---|---|---|
| 0 | e0789f27 | late (528 ms); PP late | Brute Bonnet / none | printing_ambiguous; sv04-123 (right name and number, printing unconfirmed) | APP text late | SRV number not read; twins |
| 1 | fc98725f | late (415 ms); PP late | none / 159/182 | printing_ambiguous; sv04-159 (Capsule) | APP text late | SRV name not read; twins (Paradox Rift vs PS5) |
| 2 | 8ced766c | late; 0 lines; num false | none / none | uncertain; below visual floor; 30th-077 | CAPTURE blur (sharp 207 on phone, 42 on server) | APP text late |
| 3 | 587ff04f | late (332 ms, 17 lines); PP late | Charmeleon / 24/102 | uncertain; base1-24 (right) | APP text late | reprint tie and finish rule |
| 4 | 3dad0958 | name true, number false (3 lines); num false | none / none | uncertain; conflict; 30th-095 (Zorua) | APP number not read (card 31% of frame, sharp 373) | SRV read nothing |
| 5 | dd6cf888 | late (259 ms); PP late | Pikachu / none | printing_ambiguous; base1-58 (Base Set Pikachu, owner has Evolutions 35/108) | APP text late | VT: Base Set leads by 0.02 |
| 6 | 29847b9d | late (1147 ms); PP late | Toxel / MP078 | uncertain; mep-078 (right), gap +0.13, rank conflict | APP text late | SRV prefix `MP` vs `MEP` |
| 7 | bf698dd0 | name true, number true (cameraQuad); PP none | no case record | (phone: uncertain) | UNKNOWN | server data not available |
| 8 | 849a3f7b | name true, number true; PP none | Brute Bonnet / 123/182 | printing_ambiguous; sv04-123 | TW (Paradox Rift vs PS5; server and phone agree) | none |
| 9 | 7477d6d3 | name true, number true; PP none | none / 159/182 | printing_ambiguous; sv04-159 | TW | SRV name not read |
| 10 | 3823fadf | name true, number true; PP none | no case record | (phone: uncertain) | UNKNOWN | server data not available |
| 11 | d193fa58 | late (534 ms, 0 lines); PP late | none / none | no_match; below visual floor | APP text late | SRV found no text |
| 12 | 046e9f04 | name true, number true (cardShaped, sharp 333, 39% of frame); PP none | none / none (1 line) | printing_ambiguous; zh-tw SV8a-157 (wrong card, visual 0.77) | SRV OCR miss on the same photo | visual floor |
| 13 | b8151325 | none: 11 lines, no fields; PP late | Brute Bonnet / none | printing_ambiguous; sv04-123 | APP no name or number fields | TW |
| 14 | 52eb9bad | late (398 ms); PP late | Comfey / 077/128 | uncertain; 30th-077 (right), visual 0.82, gap +0.16 | SRV frame rule (`inferred_frame`) | APP text late |
| 15 | b5dbebd7 | name true, number false (1 candidate, 14 lines); PP late | none / none | printing_ambiguous; base1-24 (conflict) | APP number not read | SRV read nothing; VT |
| 16 | 74f468b4 | late (277 ms); PP late | Zorua / 095/128 | uncertain; 30th-095 (right), gap +0.06 | SRV frame rule (`inferred_frame`) | APP text late |
| 17 | e3af63b1 | late (287 ms); PP late | Pikachu / none | printing_ambiguous; 30th-c-014 (wrong card, visual 0.85) | APP text late | VT |
| 18 | 4ae8e378 | late (988 ms); PP late | Toxel / 078 (no prefix) | retake; conflict; local artwork incompatible | APP text late | SRV: bare `078` against MEP, which gave retake |
| 19 | 3386615d | late (334 ms); PP late | Charmander / 9/108 | uncertain; xy12-9 (right), gap -0.03 (base1-46 leads) | APP text late | VT (reprint tie) |
| 20 | ba060500 | late (356 ms); PP late | Brute Bonnet / 123/182 | printing_ambiguous; sv04-123 | APP text late | TW |
| 21 | 1f3dfa76 | name true, number true; PP none | no case record | (phone: printing_ambiguous) | UNKNOWN | server data not available |
| 22 | 28217260 | name true, number true; PP none | Comfey / 077/128 | uncertain; 30th-077 (right), gap +0.08 | SRV frame rule (`inferred_frame`, client quad rejected) | none |
| 23 | 24331e6f | none, 0 lines; PP number false | none / none | no_match; below visual floor | CAPTURE blur (sharp 474 on phone, 103 on server) | none |
| 24 | 21fe303f | name true, number false (1 candidate); PP late | partial name / 199/122 (misread) | printing_ambiguous; PPS5-PAR-159 (wrong printing), identity conflicting | APP number not read; SRV number misread | TW (PS5 sibling on top) |
| 25 | b86ab46d | late (295 ms); PP number false (1 candidate) | Comfey / 077/128 | uncertain; 30th-077 (right), visual 0.77, below floor | APP text late | SRV visual floor; framing rescue |
| 26 | 797e6f64 | none (9 lines, no fields); PP number false | Zorua / none | uncertain; 30th-095 (right), gap +0.14, conflict | CAPTURE card small (16% of frame) | APP no number |
| 27 | ba6ff678 | late (319 ms); PP number true | Pikachu / 35/108 | uncertain; xy12-35 (right), gap -0.02 (base1-58 leads) | APP text late | VT |
| 28 | 090e9f9d | late (277 ms); PP late | Charmeleon / 24/102 | uncertain; base1-24 (right), gap 0 (tie) | APP text late | VT / finish rule |

Notes on the table:
- "Right" means the card the owner listed (Brute Bonnet 123/182, Capsule 159/182, Charmander 9/108, Charmeleon 24/102, Pikachu 35/108, Comfey 077/128, Zorua 095/128, Toxel 078). The owner's list does not show Prize Pack or 1st edition; those are treated as the plain printing.
- Scans 7, 10 and 21 have no case record on staging, so the server's read is unknown. The phone sent a name and number on all three.
- For phone-side agreement with the server (the owner's "number agreed on 6 of 29"), I cannot re-check: the server's `stage0` lines for these scans are gone from the container log (see below).

## Causes, ranked by scans

Each scan gets one first blocker (table column 6). Several scans have a second cause; those are counted in the last column.

| Rank | Cause | Scans (first blocker) | Also contributes | Side |
|---|---|---|---|---|
| 1 | Phone text arrived after the 300 ms budget, nothing sent | 15 (0, 1, 3, 5, 6, 11, 14, 16, 17, 18, 19, 20, 25, 27, 28) | 6 and 18 also have a prefix problem; scan 2 is late and blurred (counted under rank 5) | App |
| 2 | Phone found a name but no number, or no fields at all | 4 (4, 13, 15, 24) | 2 with capture limits (26, 23) | App |
| 3 | Twins: Paradox Rift versus Prize Pack sibling (correct server behaviour) | 2 (8, 9) | 5 more (0, 1, 20, 13, 24) | Catalogue |
| 4 | Server OCR read nothing although the phone read both | 1 (12) | 2 (4, 15) | Server |
| 5 | Blur or card too small in frame | 3 (2, 23, 26) | 26 also has no number (rank 2) | App (shutter, guidance) |
| 6 | Unknown: no server case record | 3 (7, 10, 21) | none | Logs |
| 7 | Server frame rule downgraded a correct visual match | 1 (22) | 3 more (14, 16, 25) | Server |

Reprint ties and number parsing did not block any scan first, because the phone's text ran late on the same scans. They still matter after the text is fixed:

- **Reprint ties (visual leader wrong or tied, server design):** 3, 5, 15, 17, 19, 27, 28. Here the server already reads the right name and number on 3, 19, 27 and 28, and the picture leads with the older print.
- **Number parsing:** 6 (`MP078` for `MEP 078`), 18 (bare `078`, gave `retake`), and 24 (`199/122` misread). The `30C` prefix is fixed (14, 16, 22, 25).

Short version: the phone's text is missing on 19 of 29 scans. Where it is present, the server's rules stop the scan for twins or reprint ties, which is correct until a stamp or footer is seen.

## App causes and server causes, separated

App (phone side):
- Text budget of 300 ms: 16 late (the largest cause). Later text is never sent.
- Number reader not finishing: PP-OCR capped at 1.2 s, late on 15 scans, a number on 1 of 6 completed reads.
- Name-only text: 4, 15, 24.
- Capture: blur on 2 and 23 (sharpness 207 and 474 on the phone; 42 and 103 on the server); card too small on 26 (card about 16% of the frame).

Server:
- Parser: `MP078` for `MEP 078` (6); bare `078` with no set prefix gives `retake` (18); `199/122` misread (24).
- Frame rule: `inferred_frame` downgrade on 14, 16, 22, 25 (visual 0.77 to 0.82, name and number right).
- Visual leader and reprint ties: 3, 5, 15, 17, 19, 27, 28.
- OCR miss on the server's own read: 12 (phone read both), 4, 9 (name not read), 0 (number not read).
- Twins: 0, 1, 8, 9, 13, 20, 24. These are correct stops.

Catalogue: Paradox Rift versus Prize Pack and the Base Set versus Evolutions reprints are real ambiguity. The staging catalogue has only 775 `en` rows, and it does not contain Brute Bonnet, Capsule, Comfey or Zorua, so I could not check uniqueness of name plus number from it.

## Smallest fix per cause

Every change goes behind a switch, default off. Gains are estimates from these logs; nothing was replayed.

| # | Fix | Scans it can change | Risk of a wrong answer | How to measure |
|---|---|---|---|---|
| 1 | **Let the phone's text finish after the 300 ms budget**: keep the ML Kit read running and send the text as a late hint when it arrives (the server already streams `provisional` results). Or raise the budget to 600 ms and see if the upload waits | up to 15 | Low. The text is a hint; the server still checks it against the catalogue and the picture. A late hint could still agree with the wrong card if the name is a twin, which the server already handles | Count `client_text.done` on the same 30 cards before and after; compare sent-text rate (10 of 29 now). Check `text.read.read_ms` on 1363 px and on 641 px photos to test the slow-read guess |
| 2 | **Longer PP-OCR cap or start it earlier** on the still (already written, PokeSingle #166, off). Its cap hit 15 of 29 scans | up to 4 (number missing) and part of 15 | Low: same gate as text (the server checks a candidate number) | Number reader done and number-true rate on the same cards (1 of 6 now); want at least 4 of 6 finished with the right number |
| 3 | **Set-prefix parser for `MP`/`MEP`**: treat a promo prefix that is a near-miss of the catalogue set id (`MP` for `MEP`) as equal, only for a known set id, and send the full footer to the parser | 6 (and 18 would leave `retake`) | Low to medium: `MP` could match another set. Limit it to set ids that exist in the catalogue and match the name | Replay the 29 stored footers: `MP078` and `078` should map to `en:mep-078`, and no other card should change |
| 4 | **Capture guidance**: "move closer" when the card is under about 30% of the frame; "hold still" when the sharpness is low. Keep the full-resolution footer in the upload | 2, 23, 26 (3 scans) and some of the number misses | None: fewer retakes, no change to the answer | 30 manual shots per setting; retake rate and footer digit height in pixels |
| 5 | **Frame-rule downgrade**: do not downgrade a `visual_ok` match to `uncertain` for `inferred_frame` when the phone's quad passed card-shape checks | 14, 16, 22, 25 (4 scans) | Low to medium. These four already agree on name and number; the risk is a wrong card with a close picture | Replay the 29 and the 53: count changes, wrong answers must stay 0 |
| 6 | **Name plus full fraction for reprint ties**: when the phone's name and number both name one catalogue card and the picture ranks it in the top 20, allow `matched` instead of `uncertain` | 3, 5, 17, 19, 27, 28 (6 scans) | Medium. A wrong read that names another real card is the failure | Replay the Pikachu, Charmander and Charmeleon pairs: 0 wrong; the twins must not change |
| 7 | **Twins**: no change. Optionally pre-select the plain Paradox Rift printing in the app's chooser | 0, 1, 8, 9, 13, 20, 24 | None | Not applicable |

## Ranked proposal

1. **Fix 1 (text after the budget).** It addresses the largest cause (15 of 29 scans with the first blocker in the phone's text). It is an app change with the lowest wrong-answer risk, because the server keeps its checks.
2. **Fix 2 (PP-OCR cap) in the same change.** Same gate, and it helps the number-missing scans (4 of 29).
3. **Fix 3 (MP/MEP parser).** Small, testable on the stored footers, and it is the only server-side blocker that gives a wrong status on a correct card (6 and 18).
4. **Fix 4 (capture guidance).** Needed for 2, 23 and 26, and it changes no answers.
5. **Fixes 5 and 6 only after 1 to 3 are measured.** Fix 6 is the only one with real wrong-answer risk.
6. **Leave the twins alone.** 7 scans in `printing_ambiguous` are the correct answer for these reprints.

Even with 1 to 4 done, no scan is answered early until the stage 1 gate and `STAGE1_REQUIRE_CONFIRMATION` are reviewed, which is outside this task.

## Logs that are gone or missing

- The server's `stage0` lines and `scan_summary` lines for these traces were in the container log. The container's log files were reset at 19:05 UTC (the container appears to have been recreated then), and the log only covers later scans (traces from 1792955741 on). I could not read the server's name-agreement, number-agreement, `text_candidates` or stage 1 abstain reason for any scan. The owner's figures (phone number agreed on 6 of 29, name on 6, `number_agree=none` on 21) cannot be checked here.
- The phone log has only booleans for text (name true or false, number true or false, number candidate count). The text itself is not logged, so I cannot say which name or number the phone read.
- `/data/review/images` holds the review copies at 1145 px wide (the upload was 1363 px). Anyone measuring from the review store will under-count footer digits by about 16%.
- Scans 7, 10 and 21 have no case JSON and no valid image in `/data/review`.

## What I could not verify

- The phone's text content and whether a late text was ever sent to the server.
- The owner's "3 early answers" (the phone log has 0 matched).
- The stage 1 abstain reasons (`no_unique_text`, `no_embedding`, and so on), which lived in the lost `stage0` lines.
- Whether the slower text read is caused by the larger photo or the larger still. The guess is untested.
- The footer digit height in pixels. The 15 to 17 px figure is an eyeball estimate.
- Whether `OCR_SET_CODE_PREFIX` was on for this run. The owner says it was; the phone log flags (`nr1.bf-none.emb1`) do not show it. The `30C` result on Comfey and Zorua suggests the parser change is active.
- Name uniqueness in the full catalogue (the staging catalogue is a subset).
- Whether fix 1 or 2 is already in the PokeSingle code path used by the live camera; I did not read the app source.
