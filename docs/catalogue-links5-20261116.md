# LINKS5 and LINKS5B: 927 Cardmarket links for Japanese rows (2026-11-16)

Of the 2,966 Japanese rows without a Cardmarket link on IMG1, 926 get one (799 in LINKS5, 127 more in LINKS5B),
plus the English `en:mep-120`
held over from EN1 (`docs/catalogue-en1-findings-20261116.md` on `claude/image-batch-20261116-ffd17e`). The
owner asked for "Japanese links" after IMG1. Staging only. Only link columns change: no vector, image,
feature or artwork record, so IMG1's bundles are reused.

## How the links were found

Offline, from the crawl of Cardmarket expansion pages already in the catalogue (`cardmarket_products`,
crawled 2026-09-18/19), with `api/scripts/ja_set_recovery/match_crawl_links.py`:

- A set's Cardmarket expansion is the one its already-linked rows point to (71 sets have such an expansion
  and a match).
- A crawled product counts as free when no row links its page.
- **Numbered products (290 rows):** the product's printed number, e.g. `(XY-P 170)`, equals the row's number,
  and the product's English name equals the row's English title, with exactly one such product.
- **Unnumbered products (509 rows, mostly DP1-DP3, Temple of Anger, Cry from the Mysterious, Entry Pack 08):**
  the English name, ignoring `Lv.`, is unique among the expansion's free products and among the set's unlinked
  rows. This applies only when no other of our sets links into the same expansion (the vending machine series
  share `Expansion-Sheet`, so they are left out).
- A page that two rows would take is dropped.

**LINKS5B: the full promo lists.** Cardmarket's list pages stop at 300 results, so the stored crawl held only 300
products of each of the big promo expansions. With the owner's Chrome (the owner passed the Cloudflare check;
2026-11-16), every list page of XY Promos, Sun & Moon Promos, Sword & Shield Promos and Scarlet & Violet Promos
was read twice, sorted by number ascending and then descending, which together reach up to 600 results. The
four lists came out at 412, 422, 354 and 304 products, all under 600, so each is complete. Pages were read
about 1.2 s apart. Cardmarket answered 429 at the end of the Shiny Treasure ex list, and the read stopped there.
Shiny Treasure ex (10 rows) and Start Deck 100 (2 rows) were not read. Saved as `crawl-promos-20261116.json`
and given to the matcher as its third argument. This added 127 links (95 Sun & Moon promos, 32 XY promos).
It also cleared the LINKS5 link of `ja:XYP-065` Hawlucha: the full list has two Hawlucha (XY-P 065) products
(`Hawlucha-V1`, `-V2`), so the match was not unique.

Each link is URL-only, as 142 links already were, with provenance
`verified-cardmarket-firstparty-crawl-exact-expansion-number-name-links5`.

## Build

| Item | Value |
|---|---|
| LINKS5 | `pokesingle_completion_20261116_links5`, `PS-CATALOGUE-EN-JA-LINKS5-20261116`, parent IMG1; `prepare_sql_fixes.py`, 800 cards, SQL sha256 `e89b42170675d6b9b3ab7f7e44f0e4d05e9150345cf5e2f5aba83cbc2ed4b7dc`; links 48,310 -> 49,110 |
| LINKS5B (served candidate) | `pokesingle_completion_20261116_links5b`, `PS-CATALOGUE-EN-JA-LINKS5B-20261116`, parent LINKS5; 128 cards (127 links, 1 cleared), SQL sha256 `f19e87b2eead99c3562bf8d3c4addb5c6a56b9ed80905faa5a7892da7c2f47f5`; links 49,110 -> 49,236 |
| Read back | both validated, inactive |
| Bundles | features `20261116-img1`, artwork `20261116-img1` (unchanged) |

Work files: `data/catalogue-gaps/ja-links-20261116/` (`matches.json`, `fixes.json`, `sql/`, `run_gate.sh`, `out/`).

## Still without a link (2,040 Japanese rows after LINKS5B)

Counts from the matcher's run with the full promo lists:

| Why | Rows |
|---|---:|
| The set has no linked row, so its expansion is unknown (`jr-miscellaneous-promos`, `SD`, the deck kits, energies, `EN*`) | 1,026 |
| No product with that number and name in the expansion | 697 |
| Name-only in an expansion shared by several of our sets (vending machine series, deck-kit halves) | 156 |
| Several products fit (Cardmarket versions `V1`..`V5` with the same number) | 121 |
| The set's rows link to several expansions | 41 |

Linking more needs the unmapped sets assigned to their Cardmarket expansions by hand. The rows with several
fitting versions need someone to tell the versions apart on Cardmarket.
