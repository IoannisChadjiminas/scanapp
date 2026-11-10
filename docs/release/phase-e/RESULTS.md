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
answers that; it is run once, after the flags are on staging.

The first gate replay lost two of its containers without an error after 167 of 225 and 125 of 224
photos (six 4 GB containers on a 16.7 GB Docker VM). The 157 photos they did not reach were
replayed afterwards with three containers, the same code and the same flags; the figures above
are on all 1,891 photos.
