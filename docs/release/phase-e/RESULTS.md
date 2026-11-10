# Phase E: what was measured

All figures are from the proof panel (photos of real cards, never in git), replayed through the
full pipeline in the staging image against the staging catalogue. Intervals are 95% Wilson.
"Right first" means the first card shown is the card in the photo; "wrong first" means the first
card shown is another card.

## Gate for the four footer-evidence flags (2026-11-10)

`PRINTING_EXACT_FRACTION`, `PRINTING_BARE_NUMBER`, `OCR_SET_CODE_READ` and `RETRY_OWN_LANGUAGE`,
all four on, compared with staging as it runs today (JAREC15 and the 16 flags). The gate is: no
photo goes from right to wrong, no cell is lower than staging, and the upper bound of wrong first
is under 3%.

| Panel | Photos | Right first, staging | Right first, four flags on | Wrong first, staging | Wrong first, four flags on | Right to wrong |
| --- | --- | --- | --- | --- | --- | --- |
| dev | 681 | 636, 93.4% [91.3, 95.0] | 637, 93.5% [91.4, 95.2] | 4, 0.6% [0.2, 1.5] | 4, 0.6% [0.2, 1.5] | 0 |
| dev2 | 238 | 232, 97.5% [94.6, 98.8] | 232, 97.5% [94.6, 98.8] | 0, 0.0% [0.0, 1.6] | 0, 0.0% [0.0, 1.6] | 0 |
| retired sealed half | 972 | 926, 95.3% [93.7, 96.4] | 938, 96.5% [95.2, 97.5] | 2, 0.2% [0.1, 0.7] | 0, 0.0% [0.0, 0.4] | 0 |

The gate passes on all three panels with all four flags.

- 13 photos changed, every one to the right card first: 9 where the right card was offered but
  not first, 2 where the first card was wrong, 2 that had no answer. No other photo changed its
  outcome.
- The 4 wrong-first photos on dev are the same four photos with the same four wrong cards as on
  staging today (`dev-ja-promo-028`, `dev-ja-promo-040`, `dev-ja-vintage-054`,
  `dev-r8-ja-promo-047`); the four flags do not touch them.
- Per cell on the retired sealed half: Modern Japanese 86.3% to 92.3% (101 to 108 of 117), Promo
  Japanese 95.0% to 98.3% (115 to 119 of 121), Modern English 97.2% to 97.9% (137 to 138 of 141);
  the other five cells are unchanged. On dev, Modern Japanese 45 to 46 of 52; the other cells are
  unchanged. On dev2 nothing changed.

The four rules were written from the retired sealed half, so its figures show that the rules do
what they were written to do, not how they generalise. The never-run sealed half (496 photos)
answers that; see the next section.

The first gate replay lost two of its containers without an error after 167 of 225 and 125 of 224
photos (six 4 GB containers on a 16.7 GB Docker VM). The 157 photos they did not reach were
replayed afterwards with three containers, the same code and the same flags; the figures above
are on all 1,891 photos.

## The sealed run (2026-11-10)

496 photos that no release had been run on and nobody has looked at since they were labelled. One
run: the candidate (the four flags on) and the staging side (same code, the four flags off), each
once. The run was logged before any result was read. It was started at 13:29Z, one minute before
the flags went onto staging (13:30Z to 13:33Z), and finished afterwards; the staging switch was
made on the gate above, not on this run.

| Cell | Photos | Right first, staging side | Right first, four flags on | Wrong first (both sides) |
| --- | --- | --- | --- | --- |
| Modern English | 73 | 67, 91.8% [83.2, 96.2] | 68, 93.2% [84.9, 97.0] | 0, 0.0% [0.0, 5.0] |
| Modern Japanese | 81 | 77, 95.1% [88.0, 98.1] | 78, 96.3% [89.7, 98.7] | 0, 0.0% [0.0, 4.5] |
| Numbered older English | 65 | 65, 100% [94.4, 100] | 65, 100% [94.4, 100] | 0, 0.0% [0.0, 5.6] |
| Numbered older Japanese | 60 | 59, 98.3% [91.1, 99.7] | 59, 98.3% [91.1, 99.7] | 0, 0.0% [0.0, 6.0] |
| Promo English | 50 | 50, 100% [92.9, 100] | 50, 100% [92.9, 100] | 0, 0.0% [0.0, 7.1] |
| Promo Japanese | 62 | 57, 91.9% [82.5, 96.5] | 58, 93.5% [84.6, 97.5] | 1, 1.6% [0.3, 8.6] |
| Unnumbered vintage English | 35 | 35, 100% [90.1, 100] | 35, 100% [90.1, 100] | 0, 0.0% [0.0, 9.9] |
| Unnumbered vintage Japanese | 70 | 58, 82.9% [72.4, 89.9] | 58, 82.9% [72.4, 89.9] | 2, 2.9% [0.8, 9.8] |
| All | 496 | 468, 94.4% [92.0, 96.1] | 471, 95.0% [92.7, 96.6] | 3, 0.6% [0.2, 1.8] |

- Per-release gate: passed. No photo went from right to wrong, no cell is lower than the staging
  side, and the upper bound of wrong first (1.8%) is under 3%.
- 3 photos changed, every one to the right card first (2 where the right card was offered but not
  first, 1 that had no answer). With the four flags on, the right card is first or offered on 490
  of 496 photos; 3 photos have no answer.
- The 3 wrong-first photos are the same on both sides, with the same wrong cards, and none is
  caused by the four flags. By their expected cards they fall on two known catalogue gaps:
  `ja:XYP-050`, whose reference image is a card back (1 photo), and
  `ja:jr-vending-machine-series-3-green-u21`, which has no reference image (2 photos).
- The 1% completion bar for wrong first: the measured rate, 0.6%, is under 1%; its upper bound,
  1.8%, is not. With 3 wrong photos the upper bound goes under 1% at 925 photos, 429 more than
  this set. With the two catalogue gaps fixed and none wrong, 493 photos would give 0.8%; that
  needs a new sealed set, because this one is now spent for this release.
- The set is short of its plan in two cells: unnumbered vintage English 35 of 44 photos, promo
  Japanese 62 of 70.
