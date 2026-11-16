# FIXES1: missing cards, duplicate set and SP numbers (2026-11-16)

The fixes found by the missing-cards check (`docs/catalogue-missing-cards-20261116.md`), in one release on top
of LINKS4. The owner asked to finish them before the phone index ("finalize all and then phone index",
2026-11-16). Staging only; production is not touched. The model is unchanged and no vector was computed:
vectors were only deleted or moved.

## What changed

| Change | Rows | How |
|---|---:|---|
| 3 missing cards added, no image | +3 | `ja:SP-099` 名探偵ピカチュウ (Detective Pikachu, `099/S-P`); the second Vending Series 3 Kadabra and Haunter, `ja:jr-vending-machine-series-3-green-u52`, `-u53`. No image, no vector |
| `jr-moonlit-pursuit-dawn-dash` deleted | -135 | The combined set repeated the 135 distinct cards of Moonlit Pursuit and Dawn Dash under "Lv." titles. Each row was paired with its original by name (the 5 cards printed in both sets by image) |
| ... their Cardmarket links | 130 | Moved to the original rows, which had none |
| ... their vectors | 59 moved, 64 dropped | Where the original had no vector (59), the duplicate's vector moved to it together with its image, artwork regions and feature record (new `adopt_image`, so vector, regions, features and image stay one scan). Where the original had its own vector (64), the duplicate's vector went |
| `ja:SP-u43` Mew, `ja:SP-u47` Oricorio deleted | -2 | Placeholder rows of `ja:SP-343` and `ja:SP-242` (printed numbers read on the images, pad cosine 0.97 and 0.98); the numbered rows keep their links |
| SP printed numbers | 65 | `ja:SP-u..` placeholder rows get `printed_collector_number` `NNN/S-P`, read on their reference images with the server's OCR and matching the card named at that number on Limitless |
| `ja:jr-dawn-dash-014` | 1 | "Dark Magcargo" -> "Magcargo" (the card is Magcargo LV.35) |
| Vending Series 3 titles | 4 | `Kadabra LV.39` / `LV.40`, `Haunter LV.25` / `LV.26`. The two older rows have no image, so which print each one is was assigned (the older row takes the first print) |

Not changed: 5 SP placeholder rows without an image (Bede, Hop, Pikachu, Poké Ball, Potion) could each be
one of two numbers and keep no number; 9 more `ja:SP-u..` rows are event cards without a number on Limitless.

Totals: cards 62,208 -> 62,074 (+3, -137). Pad vectors 48,934 -> 48,870. Artwork regions 37,478 -> 37,350.
Feature records 62,208 -> 62,074 (available 55,653 -> 55,518).

## Build

Three inactive schemas in a chain, the last one served (B and C were built twice; see "First build" below):

| Step | Schema / import | Tool | SQL sha256 |
|---|---|---|---|
| A, add | `pokesingle_completion_20261116_fixes1a`, `PS-CATALOGUE-EN-JA-FIXES1A-20261116` | `build_release.py`, `prepare_sql.py` (29 statements) | `6acc6fc9116f652676f8c9ae49da82742399c97325fff29ed2ef79f7c81491af` |
| B, duplicates | `pokesingle_completion_20261116_fixes1rb`, `PS-CATALOGUE-EN-JA-FIXES1RB-20261116` | `prepare_sql_cleanup.py` (475 statements) | `708040d5edceecb0959d0b905efbe468f00cc98b419d86bdafd7396596fcebf9` |
| C, labels | `pokesingle_completion_20261116_fixes1r`, `PS-CATALOGUE-EN-JA-FIXES1R-20261116` | `prepare_sql_fixes.py` (167 statements, 71 rows) | `28e4aa36ea458dc08e21c008baa5f17c4d8773d907e7ee7bbe29bd29ccc82c7b` |

Reference features `/data/reference-features/20261116-fixes1r`, manifest sha256
`4e9d64ec5e32b2871e5865ad6b10d4feba01b0e996dcc9c99bc83d850a7efd43`: the served bundle plus 3 unavailable
records, then `cleanup_features.py` with the deletions and the 59 adopted records. Built on this Mac and on
the staging host with the same sha256. Artwork bundle `/data/artwork/20261116-fixes1` (embeddings
`36123f27...`), identical on both. Work files: `data/catalogue-gaps/fixes1-20261116/`.

First build. Schemas `pokesingle_completion_20261116_fixes1b` and `_fixes1` (and the bundle
`/data/reference-features/20261116-fixes1`, manifest `0583d0ac...`) gave each adopting row the duplicate's
feature record under the duplicate's file name. The server names a card's file `sha256(card id).npz` and refused
the bundle ("Unsafe reference-feature record"), so no photo was replayed. `cleanup_features.py` now hard-links
the adopted file under the adopting row's name, and B and C were rebuilt from A under new names. The first-build
schemas and bundle are unused; dropping them waits for the owner.

## Gate

(pending)

## Switch

(pending)

## Going back

(pending)
