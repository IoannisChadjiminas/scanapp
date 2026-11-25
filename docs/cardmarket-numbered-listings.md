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

**2,332 listings are named and 376 are still numbered.** The other 88 were
foreign-language listings (78 Japanese XY, 10 others) wrongly linked to English cards; they were unlinked from
the catalogue on 25 November 2026 (see [planetscale-staging.md](planetscale-staging.md)).

| Source (`rule` column) | Listings |
|---|---:|
| Cardmarket photo caption, read in the owner's browser (`photo …`) | 936 |
| TCGdex by Cardmarket product id, each one checked against the listing photo (`tcgdex …`) | 587 |
| Product id from Cardmarket's list view, TCGdex for that id, confirmed on the photo (`photo+tcgdex …`) | 255 |
| Stamp text printed on the card, read on the listing photo (`printed stamp …`) | 227 |
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
Black Star Promos and all nine Prize Pack series (49 pages, two browser
checks), then MEP, Best of Game, Nintendo and SV Energies in full and name
searches in the XY, SM, Wizards, BW and SV promo lists (30 pages, one check),
then Scarlet & Violet, Supreme Victors, Shrouded Fable, Kalos and Sun & Moon
starter sets in full plus name searches in about 60 other sets for the
listings with no photo address (about 118 pages, one check).

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

## Printed stamps (25 November 2026)

Where Cardmarket's photo has no caption, a listing was named from stamp text
printed on the card when it was legible on the zoomed photo: "Pokémon League"
(with "1st Place" … "4th Place", "League Cup", "League Challenge", "Judge"),
"Championships" / "Regional Championships", "Staff", "Pokémon TCG Gym",
"Build-A-Bear Workshop", "Toys R Us", "GameStop", "EB Games", "Pokémon Day",
"Professor Program", "Horizons", a set's logo, and "1st Edition". Bare logos
without readable text (the small red Play! Pokémon logo, snowflakes) were not
named. A card's own listing is "Normal" only when every other listing of the
card is named and its own photo carries no stamp.

Five listings were foreign-language prints linked to English cards (French
Electropower LOT 172 V3, Portuguese Nest Ball PRSVI 181 V1 and Buddy-Buddy
Poffin PRTEF 144 V2/V3, German Team Rocket's Giovanni PRDRI 174 V1). They were
unlinked from the catalogue like the Japanese XY links (see
[planetscale-staging.md](planetscale-staging.md)).

The list-view pass also turned up more non-English prints linked to English
cards: Italian Ho-Oh (EX Unseen Forces 27 V2), German Deoxys (EX Deoxys 16
V3) and Rayquaza (EX Deoxys 22 V2), and Japanese Rowlet and Dartrix (Sun &
Moon Starter Set, on Hidden Fates SV2 and SV3). They were unlinked from the
catalogue too (see [planetscale-staging.md](planetscale-staging.md)).

The last seven listings without a product in the list view were opened on
their Cardmarket product page (25 November 2026): Charizard LC 3 V3 ("Non-Holo
Lava Theme Deck"), Arboliva SVI 023 V3 ("Non-Holo Kangaskhan ex Battle Deck"),
Lechonk SVI 155 V2 ("Pokémon Center SV ETB Holo"), Mew ex MEW 151 V1 and Team
Rocket's Mewtwo ex DRI 081 V1 (no caption; Normal, since their only other
listing is the Southeast Asia promo). Charizard ex SVP 196 V1 and V2 are dead
addresses.

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
| 277 | 188 | The photo has no caption and no legible stamp text: plain reverse holos, bare logos (the small Play! Pokémon logo, snowflakes), Best of Game and Nintendo "Winner" prints without a caption, and listings that would share a name | A second source |
| 2 | 1 | Charizard ex SVP 196 V1 and V2: Cardmarket redirects both addresses to the expansion page (no such product) | A catalogue fix: the card's working listing is V3 |
| 98 | 49 | Prize Pack basic Energy (no caption) and Cheren's Care, which has no V2 in the list | Not resolvable from Cardmarket's photos |
