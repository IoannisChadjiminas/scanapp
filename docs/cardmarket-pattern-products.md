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
