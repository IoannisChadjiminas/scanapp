# Plan for the remaining cards (2026-11-11)

What is still missing after the English and Japanese coverage work, and how to close it.
Numbers are from the staging catalogue (`pokesingle_completion_20261110_jarec15`), read on
11 November 2026, and from the coverage queue and the findings
(`docs/phase-e-findings-20261110.md`).

## What is left

| Group | Cards | What it really is |
|---|---|---|
| English, no image | 195 | 161 digital TCG Pocket cards, 28 duplicate rows, 6 real cards |
| Japanese, no image | 316 | 296 with nothing, 20 with an image too small to scan |
| Wrong or missing reference image | 14 | 10 Japanese, 4 English |
| Cards not in the catalogue at all | 16 known | 15 Japanese, 1 English. Likely more (see step 6) |
| English images that should be replaced | 31 | eBay photos, kept because they are correct |

So the English gap in physical cards is **6 cards**. The Japanese gap is the real work.

### English, 195

| Cards | Group | Fix |
|---|---|---|
| 131 | TCG Pocket, Paldean Wonders (whole set) | Digital only. TCGdex has not published the art yet |
| 27 + 3 | TCG Pocket, Promos-A and three single cards | Same |
| 28 | Unseen Forces Unown Collection (`exu`) | Duplicate rows. The same 28 cards are already scanned as `ex10` |
| 6 | Yellow A Alternate (`xya`) | Images exist on Cardmarket product pages only |

### Japanese, 316, by product

| Cards | Group |
|---|---|
| 192 | 44 decks, kits and gift boxes (gym decks, LV.X decks, master kits, VS packs, starter sets) |
| 81 | Promos: miscellaneous 41, Sword & Shield 18, LEGEND 12, Black & White 5, Sun & Moon 4, Diamond & Pearl 1 |
| 24 | Energy sets: 2006, Scarlet & Violet, Mega Evolution (8 each) |
| 14 | Small special sets: Pikachu World Collection 9 (whole set), VMAX Special Set 4, Zacian + Zamazenta Box 1 |
| 5 | Main sets, one card each: Secret of the Lakes, Shining Darkness, Islands Await You, Moonlit Pursuit, Dawn Dash |

### Japanese, 316, by why there is no image

| Cards | Reason on file |
|---|---|
| 236 | No source page could be matched to the card |
| 20 | The only image found already belongs to another card |
| 20 | TCG Collector image under 180 px: shown, not scannable |
| 16 | Several pages matched and none could be told apart |
| 13 | The catalogue row has no usable name |
| 4 | Identical print of another card in the same deck; the one file went to the other |
| 5 | Cardmarket image rejected on eye-check (placeholder, another card's file, Chinese printing) |
| 2 | eBay photo too small or too blurry |

All 296 without an image have already been through TCG Collector, Cardmarket, Japanese shop
catalogues, Bulbapedia (for identity) and eBay listings. More of the same search will not find
them. 244 of the 316 share their name with a Japanese card that does have an image, which fits
deck reprints of trainers, energies and common Pokémon.

## Steps, in order

Each step that changes the catalogue is one release on staging: built, replayed against the
panels, switched only if the gates pass, with one rollback file. Production is not switched by
any of this.

### 1. Data-only fixes (no new images)

- **28 Unown duplicates:** hide the `exu` rows behind their `ex10` twins, so search shows each
  card once. The twin is already recorded per row. No image is copied (never two cards one image).
- **Numbers and totals:** L2 and L3 to /080, SM7a to /060, SM10b to /054, the `DPBP#NNN` numbers
  for DP1–DP3, Zekrom `BW005`.
- **Data shape:** the id styles in L1HG and L1SS, text notes in `twins`, SV4a's set name, the
  mixed "pop1" pool.
- **13 rows without a name** (LEGEND Promos 500–511 and Islands Await You 062): fill the name
  from an outside card list, or drop the row if no such card exists.

Size: small. Risk: the totals feed the number rules, so this needs the full replay.

### 2. One browser sitting (needs the owner's Chrome)

One worklist, done in one go, about 90 pages:

| Cards | What | Source |
|---|---|---|
| 6 | Yellow A Alternate | Cardmarket product pages. Reference only, never mirrored to the CDN |
| 31 | Replace the eBay photos | Bulbagarden Archives, CardTrader, Card Codex |
| 20 | Full-size version of the tiny TCG Collector images | The card's own page |
| 14 | Wrong or missing references (list in the findings, section 8) | Bulbagarden Archives, the official card search |
| 16 | Cards not in the catalogue | Same, plus the row itself from Bulbapedia |

Every image is eye-checked against the card's name, number and set before it is used. Images
from shops and listings stay local references and are never mirrored. I do not solve CAPTCHAs;
a page that asks for one is skipped and listed.

### 3. English image release

The 6 Yellow A cards, the 31 replacements, the 4 English references (`pop4-2`, `pop4-9`,
`pop5-2`, `basep-36`) and the Shining Celebi 106/105 row. After it, every physical English
card in the catalogue has an image. Size: small.

### 4. Japanese image release

The 10 Japanese reference fixes, the 15 new rows, the 20 full-size images, plus whatever step 5
has produced by then. Two of the fixes (`ja:XYP-050`, vending series 3 `u21`) are the cause of
all 3 wrong-first photos in the last sealed run.

Then **one fresh sealed set of about 500 never-run photos**. With none wrong, that brings the
upper bound on wrong-first answers under 1% (it is 1.8% now; the measured rate is 0.6%).

### 5. The Japanese tail (296 cards)

Worked by product, most-wanted first: promos (81), special sets (14), main-set singles (5),
then decks and energies (216).

1. **Prove a same-art printing.** For a deck card that reprints a card we already have, link it
   as a printing of that card, the way 3,967 Japanese cards already work: scanning it offers
   both printings. The link needs one photo of the deck card to eye-check the art. That photo is
   used for the check only and is not stored as the card's image, which the rules allow.
2. **Bulbagarden Archives scans** for cards whose identity Bulbapedia already confirmed. Part of
   the browser sitting if done at the same time.
3. **The 4 identical prints** (the same gym-deck card in four decks): record them as printings
   of the card that holds the file, instead of looking for a second file. **The 20 whose image
   belongs to another card:** look at each pair once. Where it is the same print, record it the
   same way; where it is not, the card stays in the search.
4. **Photos from owners of the card.** A card with no image is still searchable. When a user
   adds one by hand after a scan, that scan is a photo of exactly the card we lack. Collecting
   it needs the user's consent and an eye-check before use. This is the only route that keeps
   working without us searching, and it is a product decision.
5. **What is left stays display-only**, each with its reason, as today.

No promise on a number here. Route 1 could cover a large part of the 192 deck cards if photos
exist; the earlier eBay search found none that passed for these cards, so expect a remainder.

### 6. Check against an outside list

Coverage so far is measured against our own catalogue. The 16 missing cards were found only
because a test photo happened to show them, so there are likely more.

- Compare our set list and the card count per set against two outside lists: Bulbapedia's set
  lists for both languages, and the official Japanese card database for the Sun & Moon era
  onward.
- Output: a list of missing sets and missing cards, each with a source for the row and the image.
- These then go through steps 2 and 4 as a second batch.

Size: medium. Read-only until the batch is built.

### 7. TCG Pocket (161 cards)

Nothing to search for. When TCGdex publishes the Paldean Wonders art, the normal mirror job
picks it up. These cards are digital and will never be scanned from paper.

## Rules that apply to every step

- Every image and every label is eye-checked. Never two cards with one image.
- Cardmarket product photos, shop and listing photos are never mirrored to the CDN.
- Photos and text read from them never go into git.
- Per release: zero right-to-wrong, no cell lower than staging, one rollback file.
- eBay photos are for checks only, apart from the 31 kept by decision until step 3 replaces them.

## What I need from the owner

1. **The browser sitting (step 2):** Chrome open and signed in to Cardmarket for about 90 pages.
2. **TCG Pocket cards:** keep them in the catalogue as searchable-only, or leave them out of the
   scanner's catalogue.
3. **Photos from users (step 5, route 4):** allowed with consent, or not.

Steps 1, 6 and the same-art part of step 5 need nothing from the owner and can start now.
