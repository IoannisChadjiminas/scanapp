# Cardmarket pattern products

`api/app/cardmarket_pattern_products.csv` lists the reverse holo patterns
(Poké Ball, Master Ball, Energy, Love/Dusk/Quick/Friend Ball, Team Rocket)
that Cardmarket sells as their own products, one row per listing:
`card_id, pattern, product_id, url, image`. 1,746 listings on 873 cards.

## Where it comes from

Cardmarket keeps the patterns in "Additionals" expansions, named only V1, V2,
V3 (for example `Prismatic-Evolutions-Additionals/Exeggcute-V2-xPRE001`).
On 24 November 2026 all nine of them were read in the owner's Chrome, in list
view, where each row carries its product id (`productRow<id>`):

Prismatic Evolutions, Black Bolt, White Flare, Ascended Heroes (English);
Pokémon Card 151, MEGA Dream ex, Terastal Festival ex, White Flare JP and
Black Bolt JP (Japanese). 1,900 listings.

## How patterns are named

Cardmarket numbers the versions the same way in every set read:

| Sets | V1 | V2 |
| --- | --- | --- |
| Ball sets (Prismatic Evolutions, Black Bolt, White Flare, JP 151, Terastal Festival, White Flare JP, Black Bolt JP) | Poké Ball | Master Ball |
| Ascended Heroes, MEGA Dream ex | Energy | the card's other pattern, from TCGdex |

Checks: in the four ball sets TCGdex covers, the V2 product sells above V1 in
363 of 364 pairs (Cardmarket price file of 24 November 2026); in White Flare
JP, Black Bolt JP and Terastal Festival in 244 of 245. Every picture checked
agreed, including the one price exception (Black Bolt 010).

TCGdex's own pattern labels are swapped for 94 of these cards (36 White
Flare, 56 JP 151, 2 Ascended Heroes), and it has no product id for 530
listings, so it is not used to name Poké Ball or Master Ball. 28 MEGA Dream ex
V2 listings have no pattern TCGdex knows; they are left unnamed.

Only number pairs with both V1 and V2 are kept: V3+ listings are other
versions (Cosmos holo, stamps), not reverse patterns.

## Pictures

`image` is the listing photo on Cardmarket's image host, which answers only
requests sent with Cardmarket as the referrer.

## MEGA Dream ex V2 listings named from photos

TCGdex gives no pattern for 28 MEGA Dream ex V2 listings. 26 were named on
24 November 2026 by comparing Cardmarket's photo with a known listing of each
pattern (Poké, Quick, Friend and Dusk Ball, Team Rocket). Cards owned by a
named trainer (Ethan's, Cynthia's, Hop's, N's) use the Poké Ball in 19 of 20
known cases; Ethan's Pinsir, whose photo is missing, follows that. Charcadet
(030) and Bouffalant (140) have no photo yet and show as "Ball pattern".

## Other numbered listings

`api/app/cardmarket_listing_labels.csv` names listings Cardmarket only numbers
(V1, V2) where the version is known: the tinsel copies of Scarlet & Violet
basic Energy 017–024, and SVP 225 Pikachu's Worlds 2025 and League winner
stamps. Those cards have no plain reverse; the tinsel copy and the winner stamp
are their own products.

## Checked, no change needed

- Shiny Treasure ex, VMAX Climax and VSTAR Universe (JP): the mirror reverse is
  sold under the card's own product, with reverse holo figures; Normal/Reverse
  is right.
- 30th Celebration (EN): no reverses; Cardmarket records no reverse holo sales,
  and its Additionals expansion holds code cards only.
- EX-era Darkness and Metal Energy (ex11–ex16) are special Energy Rares with a
  reverse holo; they now offer one. Holon Phantoms and Power Keepers holo basic
  Energy do not.

## Found on staging after the first deploy

- Pattern photos returned 404: Cardmarket's photo host labels its files
  `multerS3.AUTO_CONTENT_TYPE` instead of `image/jpeg`. The server now checks
  the file's first bytes.
- Japanese Terastal Festival, Black Bolt, White Flare and 28 MEGA Dream ex
  cards still offered a plain Reverse. Japanese sets with patterns print no
  plain mirror, so every Japanese card with pattern products now offers none.
