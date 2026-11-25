# Cardmarket numbered listings

Cardmarket names many listings of one card only by number: V1, V2, V3 in the
address (`151/Bulbasaur-V3-MEW001`). Without a name the version tile read
"Bulbasaur (V3-MEW001)", and an unnumbered listing showed its whole address,
"Professor Juniper (Professor-Juniper-BLW101)".
`api/app/cardmarket_listing_labels.csv` gives these listings a short name.
`variant_record` uses it before any other label. The reverse patterns in the
"-Additionals" expansions are covered separately, in
[cardmarket-pattern-products.md](cardmarket-pattern-products.md).

## Scope, 25 November 2026

These are the English cards in `pokesingle_completion_20261120_disp1` with two
or more matched listings outside the Additionals expansions: 1,273 cards and
2,796 listings in 137 expansions. One card's listings can span several
expansions.

| | Listings | Cards |
|---|---:|---:|
| Named before (tinsel Energy, SVP 225 Pikachu) | 18 | 9 |
| Named by rule on 25 November 2026 | 910 | 562 |
| Still numbered | 1,868 | — |

## The file

Columns: `url,label,card_id,product_id,rule`. The server reads only `url` and
`label`. `rule` records where a name came from:

- `reviewed`: read on Cardmarket earlier (tinsel Energy, SVP 225).
- `tcgdex <product id>`: TCGdex `variants_detailed` gives this Cardmarket
  product a stamp, a special foil or the jumbo size. Or it gives the product
  only plain finishes, which makes it the card's own listing: "Normal". When
  a card has several plain products, they are named "Non-holo", "Holo" or
  "Reverse holo". The product id is read from the listing photo address.
- `mcdonalds`: McDonald's Collection 25th Anniversary. V1 is the non-holo
  and V2 the holo; TCGdex agrees on all 25 pairs it has.
- `expansion`: the listing sits in a different expansion from the card itself:
  Professor Program, Southeast Asia promo, W stamp, Trainer Kit.
- `own listing`: the card's own listing, with no V number and alone in its
  expansion, is "Normal".

## Safeguards

A name is never guessed. A listing keeps its number when:

- TCGdex's stamp or foil is not in the vocabulary of
  `api/scripts/name_numbered_listings.py`. Player-name Worlds stamps, Horizons,
  Asia promo, 1st Edition (a condition on Cardmarket) and league foils without
  a stamp are all left out.
- A stamped, special-foil or jumbo product does not trend above the card's
  plain listing in Cardmarket's price guide.
- TCGdex contradicts itself for the card: one product is both plain and
  special, or the plain product is not the card's own listing. Froakie
  (Obsidian Flames 056) and Terapagos (Surging Sparks 161) are examples.
- Two listings of one card would get the same name, for example two Southeast
  Asia promos, or the two Trainer Kit decks.

## Regenerating

`api/scripts/name_numbered_listings.py` writes candidate rows. It skips URLs
that are already in the file. It needs three inputs:

- `--rows`: a JSON list of listings, read-only from the catalogue. Run this in
  the staging API container, which holds the catalogue credentials:

  ```sql
  WITH p AS (SELECT * FROM <schema>.cardmarket_products
             WHERE matched=1 AND card_id LIKE 'en:%' AND expansion NOT ILIKE '%-Additionals'),
       c AS (SELECT card_id FROM p GROUP BY card_id HAVING count(*)>=2)
  SELECT p.card_id, p.url, p.expansion, p.name, p.listing_image_url AS image, k.cardmarket_url AS card_url
  FROM p JOIN c USING(card_id) JOIN <schema>.cards k ON k.id=p.card_id
  ```

- `--tcgdex`: `https://api.tcgdex.net/v2/en/cards/<id>` for each card,
  stored as `{id: {"variants_detailed": [...]}}`.
- `--guide`: Cardmarket's public `price_guide_6.json`.

Review the output before merging it into the file. `api/tests/test_cardmarket_listing_labels.py`
checks each rule, and checks that no card has two identical names.

## Still numbered, and why

| Listings | Cards | Why | Next step |
|---:|---:|---|---|
| 872 | 462 | Nothing names them without a photo: older main-set duplicates, SV Energy 001–008 V1–V5, the "Promos" expansion | Photo reading. 305 of these cards already have a photo for every listing |
| 498 | 249 | Prize Pack V1/V2: TCGdex has no Prize Pack data, and V2 costs more in only 179 of 248 pairs | Read a few pairs on Cardmarket, then one rule if they agree |
| 278 | 136 | Black Star Promos: TCGdex names the stamps by product id, but these listings have no photo address to give their id | Read product ids from Cardmarket's list view, then name them by TCGdex |
| 105 | 82 | TCGdex named them, but the price, an unknown stamp or a contradiction failed the check | Photo reading |
| 78 | 78 | Japanese XY-era sets (Phantom Gate, Rising Fist, Wild Blaze, Emerald Break, Rage of the Broken Heavens) linked to English cards. These are wrong links, not versions | Owner's decision: hide them, not name them |
| 33 | 14 | The same expansion name would apply twice on one card | Photo reading |
| 4 | 4 | The card's own listing sits beside a same-expansion sibling | Photo reading |
