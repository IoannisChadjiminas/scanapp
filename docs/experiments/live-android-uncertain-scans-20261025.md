# Why live Android scans end as uncertain, ambiguous printing or retake

Date: 2026-10-25. Read-only analysis of the 53 live-camera scans taken today on the Galaxy A55 against staging (`STORE_CAPTURES=true`, app build 1.0.0+153, native Android camera, all manual shutter). Nothing was changed on staging, in the code, or in the saved captures. No photos and no raw OCR text are in this file; scans are named by the first 8 characters of their scan id.

Sources: the 53 case files in `/data/review/cases`, the stored photos, and the `scan_summary`, `stage0` and `phone event=` log lines of the API container since 09:00 today. Staging flags were read from the container environment. The analysis scripts are in the session scratchpad, not in git.

## Answer in five lines

1. **Nothing was wrongly accepted: 0 wrong of 53.** One scan ended `matched` (Toxel, correct). 23 ended `uncertain`, 20 `printing_ambiguous`, 9 `retake`.
2. **The biggest cause is the collector number: it was not read, or read wrong, on 17 scans (32%).** A further 12 scans (23%) are bad captures: blurred, card too small in the frame, or a crop that cuts the footer or title. Together 29 of 53 never had a fair chance.
3. **One server bug explains 7 scans (13%) and is the cheapest fix:** the number was read correctly but the parser turned it into a wrong number, so the server called the right card a conflict. It is the set code printed directly before the number on 30th Celebration cards (`30C077/128` becomes `128`) and the `MEP` prefix on the Toxel promo.
4. **7 scans (13%) are correctly ambiguous:** same card name and number exist as Paradox Rift and as the Play! Pokémon Prize Pack Series Five reprint. A photo cannot prove which one the owner holds unless the small stamp is seen.
5. **The phone's early-answer path never ran:** the build sent no embedding (53 of 53, `no_reader`), text on only 21 of 53, and `STAGE1_REQUIRE_CONFIRMATION=true` makes even a perfect early answer show as `uncertain` by design.

## What happened, in numbers

| Item | Result |
|---|---|
| Final status | matched 1, uncertain 23, printing_ambiguous 20, retake 9 |
| Top candidate right (44 scans with a candidate) | 26 right; 9 right name and number with the printing unconfirmed; **7 wrong**; 2 more wrong if the owner's copies are the plain Paradox Rift print (`NO?`: the top card is the Prize Pack sibling). Owner confirmed Charmander and Pikachu are Evolutions, Brute Bonnet 123/182, Capsule 159/182 |
| Wrong top candidates | 5 Charmander (shows Base Set `base1-46`, the card is Evolutions 9/108), 2 Pikachu (`en:base1-58`, `en:30th-c-014`; the card is Evolutions 35/108). All 7 stayed `printing_ambiguous`, and the right card was in the alternatives list in all 7 |
| Phone sent an embedding | 0 of 53 (`embedding.none state=no_reader` in all 46 scans that logged it) |
| Phone sent text | 21 of 53. Its name agreed with the server's read in 12, its number in 8, and disagreed in 4 and 2. Raw number candidates: 0 |
| Phone outline (manual quad) | found 37, full frame 7, rejected as too small 2, not logged 7 |
| Early answer (stage 1 or 1b) | 0 of 53. Abstain reasons: `no_embedding` 31, `no_unique_text` 17, `no_server_frame` 5 |
| Right number read and usable by the server | 17 of 50 identifiable scans. A further 9 had the right number on the page but lost it (7 parser, 2 garbled or truncated prefix) |
| Why `decide_status` stopped (first rule that fired) | `conflict` 28, `below_visual_floor` 11, `finish_twins` 8, `visual_ok` 2, `ocr_floor` 2, `retake_input` 2 |
| `local_artwork_used` (forces at most `uncertain`) | 26 of 53 |
| Server time | median 5.7 s, p90 8.3 s, max 11.6 s |
| Upload size | 641 x 896 in 50 of 53 (877 x 1225 in 3); about 150 KB each |
| Card share of the upload (stage 0) | median 0.31; the footer digits come out about 8 pixels tall at that size (estimate by eye, see the end) |

Baseline versus blur-fix: I could not tell which scans came from which build (same build string). Splitting at the 88-second pause after the 22nd scan: retakes 4 of 22 (18%) before, 5 of 31 (16%) after; median sharpness 786 before, 709 after; no visible gain. With 22 and 31 scans this cannot show a difference smaller than about 20 points.

## Causes ranked by scans explained

Each scan gets one main cause (the one that blocks it first). Codes are used in the tables below.

| Rank | Cause | Code | Scans | Where |
|---|---|---|---|---|
| 1 | Collector number missing or misread (footer too small, soft, cut off, or digits wrong) | NM | 17 | App (resolution, framing, phone number reader) and server OCR |
| 2 | Bad capture: motion blur 4, card too small or far 3, crop misses the title or footer 5 | RB, RS, RC | 12 | App (shutter, framing guidance, crop) |
| 3 | Right number read, lost by the number parser | NP | 7 | Server |
| 4 | Same name and number in two printings (Paradox Rift versus Prize Pack Five) | TW | 7 | Catalogue (correct behavior) |
| 5 | Reprint family where the picture ties and only the footer separates (Evolutions Pikachu versus Base Set, Base Set Charmeleon versus Legendary Collection) | VT | 6 | Server design |
| 6 | Right name and number but visual score under 0.78, so local artwork use forces `uncertain` | LV | 2 | Server design |
| 7 | Matched on the picture, then downgraded because the frame was inferred rather than detected | FR | 1 | Server |
| - | Matched | OK | 1 | |

Contributing to everything: no phone embedding (53 of 53), phone text on 21 of 53, `local_artwork_used` on 26 of 53.

### What each cause looks like

**NM, number not usable (17).** All 6 Charmander scans, 3 Comfey, 3 Toxel, 4 Brute Bonnet and 1 Charmeleon scan. Typical reads: nothing; a stray attack-damage or resistance number instead of the collector number; or the right number with wrong characters (a missing slash, an extra digit, a truncated prefix, a lone 0). The number is on every photo (I read the Charmander footers by eye). The scans where the right number was read at all had a larger card share (median 0.37 against 0.27) and higher sharpness (845 against 701; sharpness known for 21 of each group), so size and focus matter. Charmander is the clearest: the picture cannot separate Base Set from Evolutions (visual scores of `base1-46`, `en:lc-70` and `en:xy12-9` lie within 0.03 of each other, 0.86 to 0.90 on four of the five), so without the footer the server shows the older print first. That is why 5 Charmander scans show a wrong top card.

**RB, RS, RC, bad capture (12).** Motion blur (sharpness 33, 47, 193, and one zoomed blurred crop at 362): `00449c1d`, `4c14c3fa`, `25bc9fd7`, `75c27ac6`. Card small or far: `2ea07b09` (rejected as too small), `7bccbb2f`, `4f09be32`. Crop misses the title or footer: `b7f74f9a`, `60176282`, `85ae58bc`, `127e43f4`, `ebad120f` (only the artwork was kept). Three of these ended as `printing_ambiguous`, not retake: `85ae58bc` and `127e43f4` with a wrong top card, `ebad120f` with the right one.

**NP, parser (7).** `0c8772bf`, `903af2db`, `0b28268b`, `63a29eef` (Comfey), `2e503903` (Zorua): the card prints the set code and the fraction together, with no space (30th Celebration: `30C` then the number). The parser strips known set codes (PAL, SV, M24 and so on) but not `30C`, so it keeps only the denominator `128`, which contradicts card number 077. `8fd2e758`, `94a13d29` (Toxel): the promo number is printed with its `MEP` prefix; the catalogue number is the bare `078`, and the only promo prefix the matcher accepts is `SVP`, so it calls this a conflict. I reproduced both with the repo's own functions (`extract_collector_candidates`, `number_matches_identifiers`) on typed examples of the printed formats and on the stored hits: a `30C`-prefixed fraction is cut down to its denominator, which does not match; `MEP078` and `M078` return `False`; the bare fraction returns `True`. All 7 had visual scores of 0.74 to 0.88 and correct names or numbers, and up to 5 of them (visual 0.80 or more, gap 0.04 or more, no local artwork: `0c8772bf`, `903af2db`, `8fd2e758`, `94a13d29`, and `2e503903` on the 0.04 edge) would have reached `visual_ok` without the false conflict.

**TW, twins (7).** Capsule: `a0381ec0`, `759d82f9`, `6d96ea3e`, `79cda6b3`, `453aaf28`. Brute Bonnet: `8224e3f4`, `5c65499a`. Name, number and total are right; the catalogue holds Paradox Rift and Prize Pack Series Five with the same number, and the stamp check saw no stamp (it says that not seeing a stamp does not prove its absence). `printing_ambiguous` is the right answer. Two scans, `c0781852` (Brute Bonnet) and `759d82f9` (Capsule), show the Prize Pack sibling on top. The owner gave the card numbers but did not say whether the copies carry the Prize Pack stamp; treated here as the plain print (so `NO?`), still unconfirmed.

**VT, reprint ties (6).** Pikachu `297086be`, `124e824f`, `1608bbc6`, `9a6fdfa7`, `39084433` and Charmeleon `fe5f2a08`. The right number was read (35/108 or 24/102) and the right card is top, but the picture's leader is the older print (Base Set Pikachu `base1-58`, 0.03 to 0.06 above the Evolutions card), so the rule "a visual leader that contradicts the footer means conflict" fires and the status stays `uncertain`. This is the safe behavior; it is the cost of not letting the footer override the picture.

**LV and FR (3).** `73e2e7cf` and `64f55968` (Zorua, name and 095/128 both read, visual 0.78 and 0.75): the picture is under 0.78 so local artwork matching runs, and its use forces `uncertain`. `3e8260c6` (Zorua, visual 0.84, gap 0.05, name and number both right): `decide_status` said `visual_ok`, then `inferred_frame` downgraded it because the server's own frame finder failed on the upload and fell back to a loose or window frame.

## Phone versus server

| Where | What happened |
|---|---|
| **App** | No embedding (not in build 153), so stage 1 can never fire. Phone text reached the server on 21 of 53. Of the other 32: the phone logged `client_text.none` for 8, `client_text.late` for 7 (missed the 300 ms budget), `client_text.done` for 2 (read but not used), and nothing for 15. No raw number candidates (`client_text.crop` shows `number_false` in all 7 logged). 9 retakes plus 3 crop failures. Upload is a fixed 641 x 896 crop (about 150 KB; iPhone uploads were 0.55 to 0.87 MB), so the footer is a few pixels tall. Manual shutter on the A55 is slow to settle: 4 of 53 are motion blur |
| **Server** | The number parser drops 7 correct reads. The picture cannot separate reprints, so every Evolutions and Base Set scan depends on the footer. `local_artwork_used` caps 26 scans at `uncertain`. The server's own frame finder fails on pre-cropped uploads (33 scans used only the phone's corners; stage 1b abstained with `no_server_frame` on 5 scans, in 4 of which the phone's name and number were both right: `3e8260c6`, `a0381ec0`, `124e824f`, `64f55968`; the fifth is `127e43f4`). `STAGE1_REQUIRE_CONFIRMATION=true` means an early answer would also be `uncertain` |
| **Catalogue** | Prize Pack twins and old-print families are real ambiguity, not a bug |

## Smallest fix per cause

Every change goes behind a new switch, default off, per the project rule. Gain figures are estimates from the logged scores, not replays: I had no local catalogue or model, and staging is read-only.

| # | Fix | Scans it can change | Risk of a wrong answer | Proof |
|---|---|---|---|---|
| 1 | **Server number parser (flag, e.g. `OCR_SET_CODE_PREFIX`):** strip letters glued to the front of a fraction when they are the set code, add `30C`; treat a promo prefix as equal when it equals the catalogue set id (`MEP`, as `SVP` already is). Pure parsing, about a day with tests | 7 (NP). 5 would reach `visual_ok`; the other 2 stay `uncertain` because local artwork is used | Very low: it only removes a false conflict, and the denominator and name checks still apply. A glued prefix could only add a false agreement if it equals a real set's code and number; limit it to known codes | Replay the stored hits of these 53 and the 157-photo panel: 0 wrong, the 7 conflicts clear, no card changes status to a wrong one. The harness for this is a ten-line script over the case files |
| 2 | **Phone number reader on the live path (PokeSingle #166, PP-OCRv6 whole-photo read, already written, off):** read the number from the full still, not from the 641 x 896 crop, and send it. Offline it raised A55 gallery reads from 47 to 89 of 102 with the same 3 wrong | up to 17 (NM) plus the 9 lost reads once fix 1 is in | Low: the phone's number is only a candidate; the server checks it against the catalogue, and the gate refuses on disagreement | Same 10 cards, same lighting: parsed right number 17 of 50 now; goal 35 or more of 50 with 0 wrong numbers; early answers and statuses before and after |
| 3 | **Capture and guidance:** log the still size and the blur-fix flags in `scan_summary` first (the build string cannot tell the builds apart), then show "move closer" and "hold still" before the shutter, and keep the full-resolution footer in the upload | 12 (RB, RS, RC) and part of NM | None: it can only produce fewer retakes | 30 manual shots per setting on the same cards: retake rate, sharpness, number height in pixels |
| 4 | **Name plus full fraction rule (flag):** when name and number-with-total are both read at 0.9 or more and name the single catalogue card, and that card is in the picture's top 20, let `printing_ambiguous` or `uncertain` become `matched` for reprint-tie cases | up to 6 (VT) plus 2 (LV) | Medium: a wrong read that names another real card is the failure; needs the unique-row, top-20 and no-same-name-same-number conditions | Replay the 157 panel and the Base/Evolutions pairs: 0 wrong; any change in the Paradox Rift twins must be 0 |
| 5 | **Frame downgrade with phone corners:** do not downgrade a `visual_ok` match to `uncertain` for `inferred_frame` when the phone corners passed the server's card-shape rules | 1 (FR) | Low to medium | Panel replay: wrong 0; count of downgrades removed |
| 6 | **Twins:** no photo fix. Keep `printing_ambiguous`. Optional app change: default-select the plain Paradox Rift printing in the chooser, never auto-confirm | 7 (TW) | None as long as it stays a pre-selection | Not applicable |

## Ranked proposal for the owner

1. **Fix 1 (parser) first.** One day, no change to what the app does, and it explains 13% of scans with the right card already top. It is the only cause with a verified, reproducible root cause.
2. **Fix 2 (phone number reader on the live path) next.** It addresses the largest cause (32%). The work exists; the question is whether #166 reads the live still or only gallery imports. I could not verify that.
3. **Fix 3 (capture logging and guidance).** Cheap, and it needs data anyway: log the flags and the still size so the next 50 scans can be compared.
4. **Fix 4 only after 1 and 2 are measured.** It carries the only real risk, and may be unnecessary once the number is read reliably.
5. **Leave the twins alone.** 7 scans ending in `printing_ambiguous` is the correct answer for Prize Pack reprints.

Even with 1 to 3, the early-answer path stays off until the phone embedding ships (another session is on it), and `STAGE1_REQUIRE_CONFIRMATION=true` keeps early answers visibly `uncertain`. Tell me if you want that switch discussed as a separate decision.

## Owner's answers (2026-10-25)

- Brute Bonnet is 123/182 and the Capsule is 159/182. The owner did not say Prize Pack, so they are treated as the plain Paradox Rift print (`sv04`); the stamp question is not explicitly confirmed.
- Charmeleon is 24/102, normal edition (not 1st edition). Shadowless versus unlimited was not stated.
- Charmander (Evolutions 9/108) and Pikachu (Evolutions 35/108) are confirmed.

## Still open for the owner

- Prize Pack stamp or plain print on the Brute Bonnet and Capsule copies (decides `759d82f9` and `c0781852`).
- Charmeleon: shadowless or unlimited.
- The three unidentified retakes `00449c1d`, `25bc9fd7`, `4f09be32`: which cards were they?

## What I could not verify

- Which scans were baseline and which used the blur-fix build, and which fix flags were on (same build string; I split by time).
- What the phone's text actually contained (only its agreement with the server's read is logged), and why it was late or absent on 32 scans; 7 scans have no phone event lines at all.
- The Android still's real resolution. The code asks for 4000 x 3000, but the upload is 641 x 896 and the queued source is about 0.65 MB against 2.5 MB on iPhone. The digit height (about 8 pixels) is my estimate from viewing the crops, not a measurement.
- Every "would become matched" count in this report. They come from the logged scores and rules, not from a replay.
- The Prize Pack stamp, Charmeleon shadowless versus unlimited, and the three unidentified cards (see above).
- Whether `fix 2` covers the live camera path.
- The catalogue entries themselves: the catalogue SQLite on staging holds only a subset of ids, so the set totals (128, 112, 182, 108, 102) come from the stored case rows, not from the catalogue file.

## Per-scan results

Columns: status; top candidate; whether it is the right card (`yes`, `yes*` = right name and number with the printing unconfirmed, `NO`, `NO?` = Prize Pack sibling on top, wrong if the copy is the plain print, `-` = no candidate); what the phone sent (text yes or no, with `n` for name and `#` for number agreeing with the server's read: Y, N or `-` for not comparable; then the outline state, `a` or `n/a` = not logged); what the server read of name and number (`ok`/`no`; number `read ok` = parsed and usable, `read, lost in parser` = on the page but dropped, `garbled`, `misread or stray digits`, `none`); the top candidate's visual score and its gap to the best different card (negative means another card looked better); main cause; stage 0 sharpness; share of the upload the card fills. The phone sent no embedding on any scan, and no scan was answered early.

#### Comfey (30th Celebration 077/128, `en:30th-077`): 9 scans

| Scan | Status | Top candidate | Right card? | Phone: text (name/number agree with server) / outline | Server read: name / number | Top visual | Gap to next card | Cause | Sharpness | Card share of upload |
|---|---|---|---|---|---|---|---|---|---|---|

| `0c8772bf` | uncertain | en:30th-077 | yes | no / found | ok / read, lost in parser | 0.82 | +0.07 | NP | 777.3 | 0.224 |
| `903af2db` | uncertain | en:30th-077 | yes | yes n:- #:Y / found | no / read, lost in parser | 0.82 | +0.08 | NP | 795.1 | 0.306 |
| `4d4e3b75` | uncertain | en:30th-077 | yes | yes n:Y #:- / full_frame_card | ok / garbled | 0.59 | -0.11 | NM | 727.0 | 1.000 |
| `e9c22d4a` | uncertain | en:30th-077 | yes | no / found | no / misread or stray digits | 0.70 | +0.03 | NM | 179.7 | 0.285 |
| `b7f74f9a` | retake | - | - | no / found | ok / none | - | - | RC | 700.7 | 0.205 |
| `0b28268b` | uncertain | en:30th-077 | yes | no / found | ok / read, lost in parser | 0.75 | +0.00 | NP | 914.0 | 0.211 |
| `2ea07b09` | retake | - | - | no / rejected_small | no / none | - | - | RS | none | none |
| `63a29eef` | uncertain | en:30th-077 | yes | no / found | no / read, lost in parser | 0.74 | -0.01 | NP | 497.6 | 0.401 |
| `f59fd8d3` | uncertain | en:30th-077 | yes | yes n:- #:- / found | ok / none | 0.71 | +0.04 | NM | 459.8 | 0.214 |

#### Zorua (30th Celebration 095/128, `en:30th-095`): 4 scans

| Scan | Status | Top candidate | Right card? | Phone: text (name/number agree with server) / outline | Server read: name / number | Top visual | Gap to next card | Cause | Sharpness | Card share of upload |
|---|---|---|---|---|---|---|---|---|---|---|

| `3e8260c6` | uncertain | en:30th-095 | yes | yes n:Y #:Y / found | ok / read ok | 0.84 | +0.05 | FR | 1373.9 | 0.321 |
| `2e503903` | uncertain | en:30th-095 | yes | yes n:- #:Y / found | ok / read, lost in parser | 0.80 | +0.04 | NP | none | 0.472 |
| `73e2e7cf` | uncertain | en:30th-095 | yes | no / found | ok / read ok | 0.78 | +0.03 | LV | none | none |
| `64f55968` | uncertain | en:30th-095 | yes | yes n:Y #:Y / found | ok / read ok | 0.75 | +0.03 | LV | 1779.3 | 0.294 |

#### Toxel (MEP promo 078, `en:mep-078`): 6 scans

| Scan | Status | Top candidate | Right card? | Phone: text (name/number agree with server) / outline | Server read: name / number | Top visual | Gap to next card | Cause | Sharpness | Card share of upload |
|---|---|---|---|---|---|---|---|---|---|---|

| `8fd2e758` | uncertain | en:mep-078 | yes | yes n:Y #:- / found | no / read, lost in parser | 0.88 | +0.07 | NP | 1196.7 | 0.609 |
| `94a13d29` | uncertain | en:mep-078 | yes | yes n:Y #:- / full_frame_card | no / read, lost in parser | 0.87 | +0.08 | NP | 1106.9 | 1.000 |
| `6a1e2f7c` | matched | en:mep-078 | yes | yes n:Y #:- / found | ok / none | 0.86 | +0.04 | OK | 1171.2 | 0.245 |
| `c5e8fd3c` | uncertain | en:mep-078 | yes | no / found | no / misread or stray digits | 0.84 | +0.06 | NM | 1263.6 | 0.314 |
| `59a3ae15` | uncertain | en:mep-078 | yes | no / found | ok / garbled | 0.89 | +0.03 | NM | 1613.4 | 0.247 |
| `b45f36f2` | uncertain | en:mep-078 | yes | yes n:Y #:- / full_frame_card | ok / misread or stray digits | 0.89 | +0.09 | NM | 1279.9 | 1.000 |

#### Ancient Booster Energy Capsule (Paradox Rift 159/182, `en:sv04-159`; sibling `en:PPS5-PAR-159`): 5 scans

| Scan | Status | Top candidate | Right card? | Phone: text (name/number agree with server) / outline | Server read: name / number | Top visual | Gap to next card | Cause | Sharpness | Card share of upload |
|---|---|---|---|---|---|---|---|---|---|---|

| `a0381ec0` | printing_ambiguous | en:sv04-159 | yes* | yes n:Y #:Y / found | ok / read ok | 0.78 | -0.02 | TW | 503.9 | 0.538 |
| `759d82f9` | uncertain | en:PPS5-PAR-159 | NO? \| no / found | ok / read ok | 0.77 | -0.01 | TW | none | none |
| `6d96ea3e` | printing_ambiguous | en:sv04-159 | yes* | no / found | no / read ok | 0.79 | -0.03 | TW | none | 0.220 |
| `79cda6b3` | printing_ambiguous | en:sv04-159 | yes* | no / found | no / read ok | 0.85 | -0.00 | TW | 760.2 | 0.578 |
| `453aaf28` | printing_ambiguous | en:sv04-159 | yes* | no / found | ok / read ok | 0.79 | -0.00 | TW | 407.4 | 0.225 |

#### Brute Bonnet (Paradox Rift 123/182, `en:sv04-123`; sibling `en:PPS5-PAR-123`): 7 scans

| Scan | Status | Top candidate | Right card? | Phone: text (name/number agree with server) / outline | Server read: name / number | Top visual | Gap to next card | Cause | Sharpness | Card share of upload |
|---|---|---|---|---|---|---|---|---|---|---|

| `8224e3f4` | printing_ambiguous | en:sv04-123 | yes* | yes n:Y #:N / found | ok / read ok | 0.84 | -0.02 | TW | 1232.0 | 0.559 |
| `75c27ac6` | retake | - | - | no / full_frame_card | no / none | - | - | RB | 361.7 | 1.000 |
| `c0781852` | printing_ambiguous | en:PPS5-PAR-123 | NO? \| yes n:N #:- / found | ok / none | 0.59 | -0.08 | NM | 455.0 | 0.370 |
| `5c65499a` | printing_ambiguous | en:sv04-123 | yes* | no / found | ok / read ok | 0.82 | -0.03 | TW | 1000.1 | 0.118 |
| `f537d664` | printing_ambiguous | en:sv04-123 | yes* | yes n:N #:- / n/a | ok / none | 0.67 | -0.07 | NM | 782.1 | 0.230 |
| `cd4d3cb0` | printing_ambiguous | en:sv04-123 | yes* | yes n:N #:- / found | ok / misread or stray digits | 0.74 | -0.04 | NM | 905.6 | 0.147 |
| `9bd5c104` | printing_ambiguous | en:sv04-123 | yes* | no / full_frame_card | no / none | 0.79 | -0.02 | NM | 714.3 | 1.000 |

#### Charmander (Evolutions 9/108, `en:xy12-9`, footer seen in 5ab7d290): 6 scans

| Scan | Status | Top candidate | Right card? | Phone: text (name/number agree with server) / outline | Server read: name / number | Top visual | Gap to next card | Cause | Sharpness | Card share of upload |
|---|---|---|---|---|---|---|---|---|---|---|

| `2aaba2d3` | printing_ambiguous | en:base1-46 | NO | no / found | ok / misread or stray digits | 0.90 | +0.01 | NM | none | 0.231 |
| `ac4f5943` | printing_ambiguous | base1-46 | NO | no / full_frame_card | no / none | 0.78 | -0.01 | NM | 220.0 | 1.000 |
| `38b34f3d` | uncertain | en:xy12-9 | yes | no / rejected_small | no / misread or stray digits | 0.70 | -0.02 | NM | none | none |
| `fe4b6a2b` | printing_ambiguous | base1-46 | NO | no / found | no / misread or stray digits | 0.83 | +0.01 | NM | 708.7 | 0.136 |
| `de906659` | printing_ambiguous | base1-46 | NO | no / found | ok / misread or stray digits | 0.90 | +0.01 | NM | 518.4 | 0.138 |
| `5ab7d290` | printing_ambiguous | base1-46 | NO | no / found | ok / misread or stray digits | 0.87 | +0.01 | NM | 1318.5 | 0.231 |

#### Charmeleon (Base Set 24/102, `base1-24`, footer seen in fe5f2a08): 3 scans

| Scan | Status | Top candidate | Right card? | Phone: text (name/number agree with server) / outline | Server read: name / number | Top visual | Gap to next card | Cause | Sharpness | Card share of upload |
|---|---|---|---|---|---|---|---|---|---|---|

| `9cedce21` | printing_ambiguous | base1-24 | yes | yes n:N #:- / found | ok / misread or stray digits | 0.86 | +0.01 | NM | 1266.0 | 0.254 |
| `fe5f2a08` | uncertain | base1-24 | yes | no / found | ok / read ok | 0.89 | -0.01 | VT | 657.2 | 0.135 |
| `ebad120f` | printing_ambiguous | base1-24 | yes | yes n:- #:Y / found | ok / none | 0.75 | -0.02 | RC | 894.7 | 0.196 |

#### Pikachu (Evolutions 35/108, `en:xy12-35`, footer seen in 127e43f4 and 1608bbc6): 10 scans

| Scan | Status | Top candidate | Right card? | Phone: text (name/number agree with server) / outline | Server read: name / number | Top visual | Gap to next card | Cause | Sharpness | Card share of upload |
|---|---|---|---|---|---|---|---|---|---|---|

| `297086be` | uncertain | en:xy12-35 | yes | no / found | no / read ok | 0.85 | -0.04 | VT | 845.4 | 0.701 |
| `4c14c3fa` | retake | - | - | no / n/a | no / none | - | - | RB | 33.2 | 0.580 |
| `60176282` | retake | - | - | no / found | no / misread or stray digits | - | - | RC | 391.4 | 0.434 |
| `124e824f` | uncertain | en:xy12-35 | yes | yes n:Y #:Y / full_frame_card | ok / read ok | 0.74 | -0.05 | VT | 1023.1 | 1.000 |
| `1608bbc6` | printing_ambiguous | en:xy12-35 | yes | no / n/a | no / read ok | 0.77 | -0.06 | VT | 385.5 | 0.449 |
| `85ae58bc` | printing_ambiguous | en:30th-c-014 | NO | yes n:Y #:- / n/a | no / none | 0.76 | -0.03 | RC | 434.2 | 0.288 |
| `127e43f4` | printing_ambiguous | en:base1-58 | NO | yes n:Y #:N / found | no / read ok | 0.82 | +0.00 | RC | 306.8 | 0.340 |
| `9a6fdfa7` | uncertain | en:xy12-35 | yes | yes n:- #:Y / found | no / read ok | 0.80 | -0.04 | VT | 866.5 | 0.793 |
| `7bccbb2f` | retake | - | - | no / n/a | no / none | - | - | RS | 275.6 | 1.000 |
| `39084433` | uncertain | en:xy12-35 | yes | no / n/a | ok / read ok | 0.77 | -0.04 | VT | none | 0.287 |

#### Card not identifiable from the stored photo: 3 scans

| Scan | Status | Top candidate | Right card? | Phone: text (name/number agree with server) / outline | Server read: name / number | Top visual | Gap to next card | Cause | Sharpness | Card share of upload |
|---|---|---|---|---|---|---|---|---|---|---|

| `00449c1d` | retake | - | - | no / found | no / none | - | - | RB | 47.2 | 0.180 |
| `25bc9fd7` | retake | - | - | no / n/a | no / none | - | - | RB | 193.3 | 1.000 |
| `4f09be32` | retake | - | - | no / found | no / none | - | - | RS | 217.4 | 0.137 |
