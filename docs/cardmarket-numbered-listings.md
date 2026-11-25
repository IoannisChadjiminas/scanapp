# Cardmarket numbered listings

Cardmarket names many listings of one card only by number: V1, V2, V3 in the
address (`151/Bulbasaur-V3-MEW001`). Without a name, the version tile read
"Bulbasaur (V3-MEW001)", and an unnumbered listing showed its whole address,
"Professor Juniper (Professor-Juniper-BLW101)".
`api/app/cardmarket_listing_labels.csv` gives these listings a short name.
`variant_record` uses it before any other label. The reverse patterns in the
"-Additionals" expansions are covered separately, in
[cardmarket-pattern-products.md](cardmarket-pattern-products.md).

## Scope and result, 25 November 2026

These are the English cards in `pokesingle_completion_20261120_disp1` with two
or more matched listings outside the Additionals expansions: 1,273 cards and
2,796 listings in 137 expansions.

**1,740 listings are named and 978 are still numbered.** The other 78 were
Japanese XY listings wrongly linked to English cards; they were unlinked from
the catalogue on 25 November 2026 (see [planetscale-staging.md](planetscale-staging.md)).

| Source (`rule` column) | Listings |
|---|---:|
| Cardmarket photo caption, read in the owner's browser (`photo …`) | 709 |
| TCGdex by Cardmarket product id, each one checked against the listing photo (`tcgdex …`) | 587 |
| Product id from Cardmarket's list view, TCGdex for that id, confirmed on the photo (`photo+tcgdex …`) | 123 |
| The card's own unnumbered listing, alone in its expansion (`own listing`) | 145 |
| The listing sits in another expansion: Professor Program, Southeast Asia promo, W stamp, Trainer Kit (`expansion`) | 108 |
| McDonald's 25th Anniversary: V1 non-holo, V2 holo, which TCGdex confirms for every pair (`mcdonalds`) | 50 |
| Named before 25 November: tinsel Energy, SVP 225 Pikachu (`reviewed`) | 18 |

## How a name is decided

A name is never guessed. Each name needs either Cardmarket's own words, or
two sources that agree.

- **Cardmarket's caption.** Cardmarket burns a caption into many listing
  photos: "Staff Version", "Holo Version", "Attention: Oversized Card",
  "Prerelease Promo", "Non-Holo Lucario ex Battle Deck", "Cosmo Holo
  Knock Out Collection". The caption names that listing directly, and the
  label keeps its words ("Non-holo, Lucario ex Battle Deck"; "Jumbo" for an
  oversized card).
- **Prize Pack.** All nine series were read pair by pair. Cardmarket
  captions every V2 "Holo Version", so V1 is the non-holo copy (400
  listings). Basic Energy pairs carry no caption and keep their numbers.
- **TCGdex.** `variants_detailed` names a product by its Cardmarket product
  id. Every one of these names was compared with the listing photo, and 18
  were corrected (below).
- **"Normal".** A card's own listing with no caption is named "Normal" only
  when every other listing of that card already has a name.
- **No name.** A listing keeps its number when:
  - its photo has no caption and no second source names it;
  - two listings of one card would get the same name, as with the two Nest
    Ball "Staff Version" listings (PRSVI 181);
  - the caption does not name a version, such as "Not Tournament Legal".

Photos come from the addresses already stored in the catalogue, or from
Cardmarket's list view (30 products per page, each row with its product id
and photo). No product pages were opened. The list view was read for SV
Black Star Promos and all nine Prize Pack series: 49 pages, with two browser
checks passed by the owner.

## TCGdex corrections found on the photos

| Listing | TCGdex | Photo |
|---|---|---|
| Black Kyurem ex SSP 048 V3 / V4 | V3 jumbo | V4 is the oversized one |
| Hearthflame Mask Ogerpon ex TWM 040 V4 / V5 | V4 jumbo | V5 is the oversized one |
| Hisuian Decidueye VSTAR ASR 084 V3 | set logo | oversized, with the set logo |
| Deino LTR 97 V2–V5 | Play! Pokémon 1st–4th place | Pokémon League 1st–4th place |
| Skeledirge SSP 031 V2, Togekiss SSP 072 V2 | plain (Normal) | cosmos holo, Premium Checklane Blister |
| Scream Tail TEF 077 V2, Iron Valiant TEF 079 V2 | cosmos | holo, Back to School |
| Flutter Mane TEF 078 V2 | cosmos | non-holo |
| Pikachu PGO 027 V2 | cosmos | holo, Pokémon GO Gift Tin |
| Pikachu EVS 049 V2 | reverse | League stamp |
| Snorlax CL 000 V2, Palafin OBF 062 V3, Espeon OBF 086 V2, Umbreon OBF 130 V4 | stamp only | Cardmarket's more precise caption |

13 SV Black Star Promo jumbo cards are listed by TCGdex as standard size.
Cardmarket's "Oversized Card" caption names them.

## Regenerating

`api/scripts/name_numbered_listings.py` writes the rule-based candidate rows
(TCGdex, expansions, McDonald's, own listing). It skips URLs that are
already in the file. Its inputs:

- `--rows`: a JSON list of listings, read-only from the catalogue. Run this
  in the staging API container, which holds the catalogue credentials:

  ```sql
  WITH p AS (SELECT * FROM <schema>.cardmarket_products
             WHERE matched=1 AND card_id LIKE 'en:%' AND expansion NOT ILIKE '%-Additionals'),
       c AS (SELECT card_id FROM p GROUP BY card_id HAVING count(*)>=2)
  SELECT p.card_id, p.url, p.expansion, p.name, p.listing_image_url AS image, k.cardmarket_url AS card_url
  FROM p JOIN c USING(card_id) JOIN <schema>.cards k ON k.id=p.card_id
  ```

- `--tcgdex`: `https://api.tcgdex.net/v2/en/cards/<id>` for each card.
- `--guide`: Cardmarket's public `price_guide_6.json`.

**Check new TCGdex rows against their photos before shipping.** Three
corrections in the table above are size or stamp swaps that only the photo
shows. `api/tests/test_cardmarket_listing_labels.py` checks each rule, and
checks that no card has two identical names.

## Still numbered, and why

| Listings | Cards | Why | What would name them |
|---:|---:|---|---|
| 476 | 239 | The photo has no caption. Many show a printed stamp (League, Toys R Us, Build-A-Bear), but nothing else confirms it | A second source: TCGdex once it lists the product id, or the product page |
| 225 | 143 | No photo address in the catalogue | Cardmarket list-view pages for those expansions (about 5–12 pages per set), then the photos |
| 139 | 68 | Black Star Promos outside the SVP list: MEP 76, Best of Game 22, Nintendo 12, XY 10, SVP 7 (beyond the 300-row list), SM 6, Wizards 4, BW 2 | List view of each promo expansion (about 15 pages), then TCGdex and the photo |
| 98 | 49 | Prize Pack basic Energy (no caption) and Cheren's Care, which has no V2 in the list | Not resolvable from Cardmarket's photos |
| 40 | 16 | SV basic Energy 001–008, V1–V5, with no photo address | List view of Scarlet & Violet Energies (2 pages), then the photos |
