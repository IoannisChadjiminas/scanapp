# Older-era Japanese cards without scan vectors — problem and proposal (2026-11-07)

## Where things stand

Staging serves `PS-CATALOGUE-EN-JA-REC5-20261107` (schema `pokesingle_completion_20261107_jarec5`). The Japanese recovery added 11,705 new cards:

| New Japanese cards | Cards | Scan behaviour |
|---|---|---|
| Image + scan vectors | 1,562 | Can be the top scan result |
| Image, no vectors — same artwork as a scannable card (reprint "twin") | ~3,170 | Scan finds the twin; the card is offered as a printing choice. Final, by design |
| Image, no vectors — **older era, held back** | **~6,220** | See below |
| No image yet | 749 | Page and price only |

All 11,705 have a card page and search entry; 8,650 have a Cardmarket link and price. Nothing is missing from the catalogue. The question is only whether a scan can return the ~6,220 older-era cards directly.

## The problem

When every new card was given vectors (candidate `jarec`), an offline replay of the 98 regression photos (staging API image, full scanner) changed 4 results. All four were deterministic:

| Photo | Current (correct) | With all new vectors |
|---|---|---|
| `ja:PMCG4-017` | correct card first | a new Mewtwo promo first; the correct card not in the suggestions |
| `ja:PCG1-048` | correct card first | "retake", no suggestions |
| base Charizard ×2 | already wrong | still wrong, on different cards |

**Cause: crowding.** These are blurry eBay photos of vintage cards; even the correct card only scores ~0.72 picture similarity. Thousands of new vintage-era images sit just as close, so one of them can take the top place (`PMCG4-017`), or the race gets so close that a later check — the local artwork check — rejects the top candidate and the scan asks for a retake (`PCG1-048`).

Removing all new vectors restored the old results exactly. Removing culprit cards one by one did not converge (other new cards took their place). Keeping vectors only for modern eras (Mega Evolution, Scarlet & Violet, Sword & Shield, Sun & Moon) gave zero changes, so that is what was published; older-era cards became printing alternatives.

**What a held card does today:** a scan cannot put it first. The scanner shows the closest scannable card; if that card has the same artwork, the held card appears as a printing choice the user can tap. If the artwork differs, the user has to search for the right card. Existing cards are not affected.

## Why the risk is not the same for every era

Most older-era cards print a collector number (often with a set mark). The scanner reads it and uses it to separate printings, so a near-identical picture alone cannot take over when the number is readable. The two failures were exactly where the number could not help:

- `PMCG4-017` (Team Rocket era): Japanese cards from 1996–2000 (Base, Jungle, Fossil, Team Rocket, Gym, Neo) **print no collector number** — only the picture and the name are available.
- `PCG1-048`: has a number, but the eBay photo is too blurry to read it.

| Era | Printed number | Risk when given vectors |
|---|---|---|
| XY, Black & White, Diamond & Pearl, Platinum, LEGEND | yes, with set code | lower — number usually separates printings |
| ADV, PCG | yes | medium — older print, photos often blurry |
| Original, Neo, VS, e-Card, vending, old promos | often none | higher — picture and name only |

## Testing options

**A. Synthetic test + the 98-photo replay (hours).** For every existing card of an era, make several deliberately bad "photos" of its reference image (blur, tilt, glare, heavy compression, crop) and check which card comes first before and after adding that era's new vectors. A new card that takes the top place from an existing card stays a printing alternative; the rest of the era gets vectors. The same is done for new cards (they should find themselves).

Limits — why this is not enough on its own:
1. A fast synthetic test only checks picture ranking. The `PCG1-048` failure came from a later step (local artwork check), which only the full scanner exercises; the full scanner takes ~10 s per photo locally, too slow for tens of thousands of synthetic photos.
2. Simulated damage is not real damage (sleeves, holo glare, shadows, odd crops). The test can be too easy or too harsh depending on settings.
3. Only two real failures are known, so there is little to calibrate against.

**B. Real eBay photos (days).** Collect 100+ real photos of older-era cards through the owner's Chrome, check each by eye against the reference (handoff rule), and use them as an extra replay panel. Slower, but real.

## Proposal

1. **Calibrate the synthetic test first (1–2 hours).** Run it against the all-eras candidate that failed (`jarec`). It must independently flag the cards that broke `PMCG4-017` (the Mewtwo promo and its neighbours) and those crowding `PCG1-048`. If it cannot reproduce the known failures, drop it and use option B.
2. **If it passes, release by era, numbered eras first:** XY → Black & White → Diamond & Pearl / Platinum → LEGEND (~3,500 cards together), then ADV and PCG. Each batch: synthetic test → flagged cards stay printing alternatives → new candidate → full offline replay of the 98 photos → switch only on **zero** best-match/status changes → record and keep a rollback.
3. **Unnumbered vintage eras last, and only with real photos** (option B): Original, Neo, VS, e-Card, vending, old promos. This is where the known failures came from.

**Gates for every batch:** synthetic test clean; 98-photo replay with 0 best-match or status changes against the served release; staging health ready with no restarts or OOM; rollback file archived; `events.jsonl` and the plan doc updated.

## Open points for the owner

- Accept the calibration step as the decision point for using the synthetic test.
- Approve collecting real eBay photos for the unnumbered vintage eras (handoff: eBay photos are for tests only and are checked by eye).
- The last replays ran on the previous staging API image (`e99c2332…`); staging now runs `cbbf83b2…` (a 12:00 UTC deploy). The owner chose not to re-run them; future batches should replay on the running image.
